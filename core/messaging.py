"""
core/messaging.py
─────────────────
TCP-based text messaging and typing indicators.

Design
──────
• A persistent TCP server accepts short-lived connections, one per packet.
  This avoids managing long-lived connections (reconnect logic, keepalives)
  at the cost of a little overhead per message – fine for LAN chat.
• Outgoing packets are sent in a new connection each time via
  socket.create_connection(), which handles IPv4/IPv6 transparently.
• MESSAGE and TYPING packets share the same port and server; the type
  field in the Packet distinguishes them.

Thread safety
─────────────
The server runs in a daemon thread.  Each incoming connection is dispatched
to its own short-lived thread.  Signals are emitted from those threads and
queued automatically by Qt for the main-thread UI.
"""

from __future__ import annotations

import logging
import socket
import threading

from PySide6.QtCore import QObject, Signal

from .protocol import MSG_PORT, MsgType, Packet, recv_framed

log = logging.getLogger(__name__)


class MessagingService(QObject):
    """
    Sends and receives text messages (and typing indicators) over TCP.

    Signals
    -------
    message_received(sender_ip, sender_name, text, timestamp)
    peer_typing(sender_ip, is_typing)
    send_failed(target_ip, reason)
    """

    message_received = Signal(str, str, str, float)  # ip, name, text, ts
    peer_typing   = Signal(str, bool)              # ip, is_typing
    send_failed      = Signal(str, str)               # ip, reason

    def __init__(self, local_name: str, local_ip: str, parent=None) -> None:
        super().__init__(parent)
        self._name = local_name
        self._ip   = local_ip
        self._server: socket.socket | None = None
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_name(self, name: str) -> None:
        self._name = name

    def start(self) -> None:
        """Bind the server socket and begin accepting connections."""
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("", MSG_PORT))
        self._server.listen(20)
        self._server.settimeout(2.0)
        threading.Thread(
            target=self._accept_loop, daemon=True, name="msg-server"
        ).start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass

    def send_message(self, target_ip: str, text: str) -> bool:
        """
        Deliver a text message to *target_ip*.

        Runs synchronously (call from a background thread if needed).
        Returns True on success, False on network error.
        """
        pkt = Packet(MsgType.MESSAGE, self._name, self._ip, {"text": text})
        return self._deliver(target_ip, pkt)

    def send_typing(self, target_ip: str, is_typing: bool) -> None:
        """
        Notify *target_ip* of our current typing state.
        Fire-and-forget; errors are silently dropped.
        """
        pkt = Packet(MsgType.TYPING, self._name, self._ip, {"is_typing": is_typing})
        threading.Thread(
            target=self._deliver,
            args=(target_ip, pkt),
            daemon=True,
            name="msg-typing",
        ).start()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _deliver(self, ip: str, pkt: Packet) -> bool:
        """Open a TCP connection, send the framed packet, close."""
        try:
            with socket.create_connection((ip, MSG_PORT), timeout=5) as conn:
                conn.sendall(pkt.to_framed())
            return True
        except OSError as exc:
            log.warning("Delivery to %s failed: %s", ip, exc)
            self.send_failed.emit(ip, str(exc))
            return False

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, (src_ip, _) = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle,
                args=(conn, src_ip),
                daemon=True,
                name=f"msg-rx-{src_ip}",
            ).start()

    def _handle(self, conn: socket.socket, src_ip: str) -> None:
        """Read and dispatch a single packet from an accepted connection."""
        try:
            data = recv_framed(conn)
            if not data:
                return

            pkt = Packet.from_json(data)

            if pkt.type == MsgType.MESSAGE:
                text = pkt.payload.get("text", "").strip()
                if text:
                    self.message_received.emit(
                        src_ip, pkt.sender_name, text, pkt.timestamp
                    )

            elif pkt.type == MsgType.TYPING:
                is_typing = bool(pkt.payload.get("is_typing", False))
                self.peer_typing.emit(src_ip, is_typing)

        except Exception:
            log.exception("Error handling message from %s", src_ip)
        finally:
            conn.close()
