"""
core/protocol.py
────────────────
Central protocol definition for LAN Chat.

All network packets are JSON-encoded:
  • UDP (discovery)  → raw JSON bytes
  • TCP (messages/files) → 4-byte big-endian length prefix + JSON bytes

Packet schema:
{
  "type":        str,    # MsgType value
  "sender_name": str,    # Display name
  "sender_ip":   str,    # Source IP
  "timestamp":   float,  # Unix epoch
  "payload":     dict    # Type-specific data (see below)
}

Payload schemas by type:
  HELLO / HELLO_ACK / BYE  → {}
  MESSAGE                  → {"text": str}
  TYPING                   → {"is_typing": bool}
  FILE_OFFER               → {"filename": str, "size": int, "transfer_id": str}
"""

from __future__ import annotations

import json
import struct
import time
from enum import Enum


# ── Network constants ──────────────────────────────────────────────────────────

DISCOVERY_PORT     = 5555   # UDP broadcast / unicast
MSG_PORT           = 5001   # TCP – text messages & typing indicators
FILE_PORT          = 5002   # TCP – file transfers
CHUNK_SIZE         = 65536  # 64 KB per file read/write
BROADCAST_INTERVAL = 5      # seconds between HELLO broadcasts
PEER_TIMEOUT       = 15     # seconds of silence before peer is considered gone


# ── Message types ──────────────────────────────────────────────────────────────

class MsgType(str, Enum):
    HELLO      = "HELLO"       # UDP: announce presence on network
    HELLO_ACK  = "HELLO_ACK"   # UDP: direct reply to a HELLO
    BYE        = "BYE"         # UDP: clean shutdown notification
    MESSAGE    = "MESSAGE"     # TCP: plain-text chat message
    TYPING     = "TYPING"      # TCP: typing-indicator update
    FILE_OFFER = "FILE_OFFER"  # TCP: file-transfer offer (metadata header)


# ── Packet ─────────────────────────────────────────────────────────────────────

class Packet:
    """
    Immutable-ish representation of a single LAN Chat protocol packet.

    Instantiate directly for outgoing packets; use the class-method
    constructors (from_json / from_dict) for incoming data.
    """

    __slots__ = ("type", "sender_name", "sender_ip", "payload", "timestamp")

    def __init__(
        self,
        msg_type: MsgType | str,
        sender_name: str,
        sender_ip: str,
        payload: dict | None = None,
        timestamp: float | None = None,
    ) -> None:
        self.type        = MsgType(msg_type)
        self.sender_name = sender_name
        self.sender_ip   = sender_ip
        self.payload     = payload or {}
        self.timestamp   = timestamp if timestamp is not None else time.time()

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":        self.type.value,
            "sender_name": self.sender_name,
            "sender_ip":   self.sender_ip,
            "timestamp":   self.timestamp,
            "payload":     self.payload,
        }

    def to_json(self) -> bytes:
        """Raw JSON bytes – used for UDP datagrams."""
        return json.dumps(self.to_dict()).encode("utf-8")

    def to_framed(self) -> bytes:
        """4-byte length prefix + JSON – used for TCP streams."""
        body = self.to_json()
        return struct.pack("!I", len(body)) + body

    @classmethod
    def from_dict(cls, d: dict) -> "Packet":
        return cls(
            msg_type    = MsgType(d["type"]),
            sender_name = d["sender_name"],
            sender_ip   = d["sender_ip"],
            payload     = d.get("payload", {}),
            timestamp   = d.get("timestamp", time.time()),
        )

    @classmethod
    def from_json(cls, data: bytes) -> "Packet":
        return cls.from_dict(json.loads(data.decode("utf-8")))

    def __repr__(self) -> str:
        return (
            f"<Packet {self.type.value} "
            f"from {self.sender_name}@{self.sender_ip}>"
        )


# ── TCP framing helpers ────────────────────────────────────────────────────────

def recv_framed(sock) -> bytes | None:
    """
    Read one complete length-prefixed message from a TCP socket.

    Returns the raw JSON body as bytes, or None if the connection closed
    or the payload exceeds a sanity limit (16 MB).
    """
    header = _recv_exact(sock, 4)
    if header is None:
        return None

    length = struct.unpack("!I", header)[0]
    if length == 0 or length > 16 * 1024 * 1024:
        return None  # malformed or oversized

    return _recv_exact(sock, length)


def _recv_exact(sock, n: int) -> bytes | None:
    """Receive exactly *n* bytes from *sock*, returning None on EOF/error."""
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)
