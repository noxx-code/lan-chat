"""
core/discovery.py
─────────────────
UDP-based LAN peer discovery.

How it works
────────────
1. On startup, this service binds a UDP socket to DISCOVERY_PORT.
2. A background thread broadcasts a HELLO packet every BROADCAST_INTERVAL
   seconds so new peers learn about us.
3. When a HELLO arrives from an unknown IP, we record the peer and reply
   with a targeted HELLO_ACK – so the broadcaster discovers us immediately
   without waiting for the next interval.
4. A reaper thread removes peers that haven't been heard from for
   PEER_TIMEOUT seconds (they crashed or left without sending BYE).
5. On clean shutdown, a BYE broadcast lets peers remove us instantly.

Thread safety
─────────────
_peers is protected by _peers_lock.  All Qt signals are emitted from
worker threads but PySide6 automatically queues cross-thread signals.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

from PySide6.QtCore import QObject, Signal

from .protocol import (
    BROADCAST_INTERVAL,
    DISCOVERY_PORT,
    MsgType,
    PEER_TIMEOUT,
    Packet,
)

log = logging.getLogger(__name__)


class DiscoveryService(QObject):
    """
    Manages automatic LAN peer discovery via UDP broadcast.

    Signals
    -------
    peer_found(ip, name)    – A previously-unknown peer is online.
    peer_lost(ip)           – A peer went offline or timed out.
    peer_updated(ip, name)  – A peer changed their display name.
    """

    peer_found   = Signal(str, str)  # ip, display_name
    peer_lost    = Signal(str)       # ip
    peer_updated = Signal(str, str)  # ip, new_display_name

    def __init__(self, local_name: str, local_ip: str, parent=None) -> None:
        super().__init__(parent)
        self._name = local_name
        self._ip   = local_ip

        # ip -> {"name": str, "last_seen": float}
        self._peers: dict[str, dict] = {}
        self._peers_lock = threading.Lock()

        self._sock: socket.socket | None = None
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_name(self, name: str) -> None:
        """Update the display name broadcast to peers."""
        self._name = name

    def start(self) -> None:
        """Open the socket and launch all background threads."""
        self._running = True
        self._sock = self._make_socket()
        threading.Thread(target=self._listen_loop,    daemon=True, name="disc-listen").start()
        threading.Thread(target=self._broadcast_loop, daemon=True, name="disc-bcast").start()
        threading.Thread(target=self._reaper_loop,    daemon=True, name="disc-reap").start()

    def stop(self) -> None:
        """Send BYE to peers and release resources."""
        self._running = False
        if self._sock:
            self._broadcast(MsgType.BYE)
            try:
                self._sock.close()
            except OSError:
                pass

    def get_peers(self) -> dict[str, dict]:
        """Return a snapshot of the current peer dict (thread-safe copy)."""
        with self._peers_lock:
            return dict(self._peers)

    # ── Socket setup ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)
        sock.bind(("", DISCOVERY_PORT))
        return sock

    # ── Sending helpers ────────────────────────────────────────────────────────

    def _broadcast(self, msg_type: MsgType) -> None:
        """Send a discovery packet to the whole subnet broadcast address."""
        pkt = Packet(msg_type, self._name, self._ip)
        try:
            self._sock.sendto(pkt.to_json(), ("<broadcast>", DISCOVERY_PORT))
        except OSError as exc:
            log.debug("Broadcast failed: %s", exc)

    def _send_ack(self, target_ip: str) -> None:
        """Reply directly to a HELLO sender so they learn about us fast."""
        pkt = Packet(MsgType.HELLO_ACK, self._name, self._ip)
        try:
            self._sock.sendto(pkt.to_json(), (target_ip, DISCOVERY_PORT))
        except OSError as exc:
            log.debug("HELLO_ACK failed to %s: %s", target_ip, exc)

    # ── Background threads ─────────────────────────────────────────────────────

    def _broadcast_loop(self) -> None:
        """Periodically announce ourselves to the subnet."""
        while self._running:
            self._broadcast(MsgType.HELLO)
            time.sleep(BROADCAST_INTERVAL)

    def _listen_loop(self) -> None:
        """Receive and dispatch incoming discovery packets."""
        while self._running:
            try:
                data, (src_ip, _) = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            # Skip our own broadcasts
            if src_ip == self._ip:
                continue

            try:
                pkt = Packet.from_json(data)
            except Exception:
                continue  # malformed packet

            self._dispatch(pkt, src_ip)

    def _reaper_loop(self) -> None:
        """Remove peers that haven't broadcast in PEER_TIMEOUT seconds."""
        while self._running:
            time.sleep(PEER_TIMEOUT / 3)
            cutoff = time.time() - PEER_TIMEOUT
            with self._peers_lock:
                stale = [ip for ip, info in self._peers.items()
                         if info["last_seen"] < cutoff]
            for ip in stale:
                log.debug("Peer timed out: %s", ip)
                self._remove_peer(ip)

    # ── Packet dispatch ────────────────────────────────────────────────────────

    def _dispatch(self, pkt: Packet, src_ip: str) -> None:
        if pkt.type == MsgType.BYE:
            self._remove_peer(src_ip)

        elif pkt.type in (MsgType.HELLO, MsgType.HELLO_ACK):
            self._upsert_peer(src_ip, pkt.sender_name)
            if pkt.type == MsgType.HELLO:
                # Direct reply so sender learns about us without waiting
                self._send_ack(src_ip)

    # ── Peer state management ──────────────────────────────────────────────────

    def _upsert_peer(self, ip: str, name: str) -> None:
        with self._peers_lock:
            existing = self._peers.get(ip)
            self._peers[ip] = {"name": name, "last_seen": time.time()}

        if existing is None:
            log.debug("New peer: %s (%s)", name, ip)
            self.peer_found.emit(ip, name)
        elif existing["name"] != name:
            log.debug("Peer renamed: %s -> %s (%s)", existing["name"], name, ip)
            self.peer_updated.emit(ip, name)

    def _remove_peer(self, ip: str) -> None:
        with self._peers_lock:
            if ip not in self._peers:
                return
            del self._peers[ip]
        log.debug("Peer left: %s", ip)
        self.peer_lost.emit(ip)
