"""
core/file_transfer.py
─────────────────────
TCP-based file transfer with progress callbacks.

Wire protocol
─────────────
1. Client connects to FILE_PORT on the receiver.
2. Client sends a framed FILE_OFFER packet:
       {"filename": str, "size": int, "transfer_id": str}
3. Client streams the raw file bytes (no additional framing).
4. Server reads exactly `size` bytes and saves to DOWNLOADS_DIR.
5. Both sides emit progress/completion signals throughout.

Each transfer is identified by a short UUID so concurrent transfers
from/to different peers don't collide in the UI.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .protocol import CHUNK_SIZE, FILE_PORT, MsgType, Packet, recv_framed

log = logging.getLogger(__name__)

# Where received files land
DOWNLOADS_DIR = Path.home() / "Downloads" / "LanChat"


def fmt_size(n: int) -> str:
    """Human-readable byte count: '1.4 MB', '342 KB', etc."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileTransferService(QObject):
    """
    Handles bidirectional file transfers over TCP.

    Signals
    -------
    file_received(sender_ip, filename, local_path)
        Emitted when a file has been fully received and saved.
    transfer_progress(transfer_id, bytes_done, total_bytes)
        Emitted periodically during both send and receive.
    transfer_complete(transfer_id, success, message)
        Emitted when a transfer finishes (success or failure).
    incoming_file(sender_ip, sender_name, filename, size_str, transfer_id)
        Emitted at the start of an incoming transfer so the UI can react.
    """

    file_received      = Signal(str, str, str, str)   # ip, filename, path, transfer_id
    transfer_progress  = Signal(str, int, int)         # id, done, total
    transfer_complete  = Signal(str, bool, str)        # id, ok, message
    incoming_file      = Signal(str, str, str, str, str) # ip,name,fname,size,tid

    def __init__(self, local_name: str, local_ip: str, parent=None) -> None:
        super().__init__(parent)
        self._name = local_name
        self._ip   = local_ip
        self._server: socket.socket | None = None
        self._running = False
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_name(self, name: str) -> None:
        self._name = name

    def start(self) -> None:
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("", FILE_PORT))
        self._server.listen(5)
        self._server.settimeout(2.0)
        threading.Thread(
            target=self._accept_loop, daemon=True, name="file-server"
        ).start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass

    def send_file(self, target_ip: str, file_path: str) -> str:
        """
        Begin an asynchronous file send to *target_ip*.

        Returns the transfer_id string immediately; progress is reported
        via Qt signals.
        """
        transfer_id = str(uuid.uuid4())[:8]
        threading.Thread(
            target=self._send_worker,
            args=(target_ip, file_path, transfer_id),
            daemon=True,
            name=f"file-tx-{transfer_id}",
        ).start()
        return transfer_id

    # ── Send side ──────────────────────────────────────────────────────────────

    def _send_worker(self, ip: str, file_path: str, tid: str) -> None:
        path = Path(file_path)
        if not path.is_file():
            self.transfer_complete.emit(tid, False, "File not found")
            return

        filename  = path.name
        file_size = path.stat().st_size

        try:
            conn = socket.create_connection((ip, FILE_PORT), timeout=10)

            # ① Send the metadata header
            offer = Packet(
                MsgType.FILE_OFFER,
                self._name,
                self._ip,
                {
                    "filename":    filename,
                    "size":        file_size,
                    "transfer_id": tid,
                },
            )
            conn.sendall(offer.to_framed())

            # ② Stream raw bytes
            sent = 0
            with open(path, "rb") as fh:
                while sent < file_size:
                    chunk = fh.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    conn.sendall(chunk)
                    sent += len(chunk)
                    self.transfer_progress.emit(tid, sent, file_size)

            conn.close()
            self.transfer_complete.emit(
                tid,
                True,
                f"Sent '{filename}' ({fmt_size(file_size)})",
            )

        except Exception as exc:
            log.exception("File send failed (tid=%s): %s", tid, exc)
            self.transfer_complete.emit(tid, False, str(exc))

    # ── Receive side ───────────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, (src_ip, _) = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._recv_worker,
                args=(conn, src_ip),
                daemon=True,
                name=f"file-rx-{src_ip}",
            ).start()

    def _recv_worker(self, conn: socket.socket, src_ip: str) -> None:
        try:
            # ① Read the metadata header
            data = recv_framed(conn)
            if not data:
                return

            pkt = Packet.from_json(data)
            if pkt.type != MsgType.FILE_OFFER:
                log.warning("Expected FILE_OFFER, got %s", pkt.type)
                return

            filename  = pkt.payload["filename"]
            file_size = int(pkt.payload["size"])
            tid       = pkt.payload.get("transfer_id", str(uuid.uuid4())[:8])

            self.incoming_file.emit(
                src_ip,
                pkt.sender_name,
                filename,
                fmt_size(file_size),
                tid,
            )

            # ② Receive raw bytes
            save_path = _unique_path(DOWNLOADS_DIR / filename)
            received  = 0

            with open(save_path, "wb") as fh:
                while received < file_size:
                    want  = min(CHUNK_SIZE, file_size - received)
                    chunk = conn.recv(want)
                    if not chunk:
                        break
                    fh.write(chunk)
                    received += len(chunk)
                    self.transfer_progress.emit(tid, received, file_size)

            if received == file_size:
                self.file_received.emit(src_ip, filename, str(save_path), tid)
                self.transfer_complete.emit(
                    tid,
                    True,
                    f"Received '{filename}' ({fmt_size(file_size)})",
                )
            else:
                self.transfer_complete.emit(tid, False, "Transfer truncated")

        except Exception:
            log.exception("File receive error from %s", src_ip)
        finally:
            conn.close()


# ── Utility ────────────────────────────────────────────────────────────────────

def _unique_path(path: Path) -> Path:
    """Return *path* unchanged, or add a numeric suffix if it already exists."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 10_000):
        candidate = path.parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    return path  # fallback – just overwrite
