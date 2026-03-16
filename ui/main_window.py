"""
ui/main_window.py
─────────────────
Top-level application window.  Wires all UI panels to all core services.

Responsibilities
────────────────
• Start / stop DiscoveryService, MessagingService, FileTransferService.
• Route network signals to the correct UI updates.
• Maintain per-peer chat history so switching conversations is instant.
• Persist and restore the username via QSettings.
• Provide a username-setup dialog on first launch.
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.discovery    import DiscoveryService
from core.messaging    import MessagingService
from core.file_transfer import FileTransferService

from ui.device_sidebar  import DeviceSidebar
from ui.chat_area       import ChatArea
from ui.input_bar       import InputBar


# ── Utility ────────────────────────────────────────────────────────────────────

def get_local_ip() -> str:
    """Best-effort local IP detection (works on Windows and Linux)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# ── Per-peer history entry ─────────────────────────────────────────────────────

class _HistoryEntry:
    """All messages for a single peer conversation."""

    __slots__ = ("messages",)

    def __init__(self) -> None:
        # list of dicts with keys: outgoing, text, sender, timestamp,
        # type ("msg"|"file"), filename, size_str, transfer_id
        self.messages: list[dict[str, Any]] = []

    def add_msg(self, *, outgoing: bool, text: str, sender: str, ts: float) -> None:
        self.messages.append(
            dict(outgoing=outgoing, text=text, sender=sender, ts=ts, type="msg")
        )

    def add_file(
        self, *, outgoing: bool, sender: str, ts: float,
        filename: str, size_str: str, transfer_id: str,
    ) -> None:
        self.messages.append(
            dict(
                outgoing=outgoing, sender=sender, ts=ts, type="file",
                filename=filename, size_str=size_str, transfer_id=transfer_id,
            )
        )


# ── Main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Root application window.

    Layout
    ──────
    ┌─ QMainWindow ────────────────────────────────────────────────┐
    │  ToolBar (username · settings button)                        │
    ├──────────────────────────────────────────────────────────────┤
    │  QSplitter                                                   │
    │  ┌─ DeviceSidebar ──┐ ┌─ Right Panel ──────────────────────┐ │
    │  │  [Search]        │ │  ChatArea (header + bubbles)        │ │
    │  │  peer 1          │ │                                     │ │
    │  │  peer 2          │ │                                     │ │
    │  │  …               │ ├─────────────────────────────────────┤ │
    │  └──────────────────┘ │  InputBar                           │ │
    │                       └─────────────────────────────────────┘ │
    ├──────────────────────────────────────────────────────────────┤
    │  QStatusBar                                                  │
    └──────────────────────────────────────────────────────────────┘
    """

    _SETTINGS_KEY_NAME = "username"

    def __init__(self) -> None:
        super().__init__()

        self._local_ip   = get_local_ip()
        self._local_name = self._load_or_ask_name()

        # ip -> _HistoryEntry
        self._history: dict[str, _HistoryEntry] = {}
        # Flat transfer_id -> local_path, populated when file_received fires
        self._transfer_paths: dict[str, str] = {}
        self._active_ip: str | None = None

        self._build_services()
        self._build_ui()
        self._connect_signals()
        self._apply_stylesheet()

        self.setWindowTitle("LAN Chat")
        self.resize(1000, 680)
        self.setMinimumSize(700, 480)

        # Start networking
        self._discovery.start()
        self._messaging.start()
        self._files.start()
        self._status("Ready  ·  {}  ·  {}".format(self._local_name, self._local_ip))

    # ── Service setup ──────────────────────────────────────────────────────────

    def _build_services(self) -> None:
        self._discovery = DiscoveryService(self._local_name, self._local_ip, self)
        self._messaging = MessagingService(self._local_name, self._local_ip, self)
        self._files     = FileTransferService(self._local_name, self._local_ip, self)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Toolbar ────────────────────────────────────────────────────────────
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar { background: #161616; border-bottom: 1px solid #2d2d2d; "
            "padding: 4px 10px; spacing: 8px; }"
        )
        toolbar.setFloatable(False)

        title_lbl = QLabel("LAN Chat")
        title_lbl.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 700; background: transparent;"
        )
        toolbar.addWidget(title_lbl)

        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy(),
            spacer.sizePolicy().verticalPolicy(),
        )
        from PySide6.QtWidgets import QSizePolicy as SP
        spacer.setSizePolicy(SP.Expanding, SP.Preferred)
        toolbar.addWidget(spacer)

        self._name_lbl = QLabel(f"👤  {self._local_name}")
        self._name_lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 12px; background: transparent; padding-right: 8px;"
        )
        toolbar.addWidget(self._name_lbl)

        from PySide6.QtWidgets import QToolButton
        rename_btn = QToolButton()
        rename_btn.setText("✏️")
        rename_btn.setToolTip("Change display name")
        rename_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; font-size: 16px; }"
            "QToolButton:hover { background: #2a2a2a; border-radius: 4px; }"
        )
        rename_btn.clicked.connect(self._rename_self)
        toolbar.addWidget(rename_btn)

        self.addToolBar(toolbar)

        # ── Central widget ─────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Splitter ───────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #2d2d2d; }")
        root.addWidget(splitter)

        # Left: sidebar
        self._sidebar = DeviceSidebar(self._local_name, self._local_ip, splitter)
        splitter.addWidget(self._sidebar)

        # Right: chat panel
        right_panel = QWidget()
        right_panel.setStyleSheet("background: #181818;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._chat_area = ChatArea(right_panel)
        right_layout.addWidget(self._chat_area)

        self._input_bar = InputBar(right_panel)
        right_layout.addWidget(self._input_bar)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 740])

        # ── Status bar ─────────────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(
            "QStatusBar { background: #111; color: #555; font-size: 11px; "
            "border-top: 1px solid #222; }"
        )
        self.setStatusBar(self._status_bar)

    # ── Signal connections ─────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Discovery
        self._discovery.peer_found.connect(self._on_peer_found)
        self._discovery.peer_lost.connect(self._on_peer_lost)
        self._discovery.peer_updated.connect(self._on_peer_updated)

        # Messaging
        self._messaging.message_received.connect(self._on_message_received)
        self._messaging.peer_typing.connect(self._on_typing_changed)
        self._messaging.send_failed.connect(self._on_send_failed)

        # File transfers
        self._files.incoming_file.connect(self._on_incoming_file)
        self._files.transfer_progress.connect(self._on_transfer_progress)
        self._files.transfer_complete.connect(self._on_transfer_complete)
        self._files.file_received.connect(self._on_file_received)

        # UI
        self._sidebar.device_selected.connect(self._on_device_selected)
        self._input_bar.message_ready.connect(self._on_send_message)
        self._input_bar.file_chosen.connect(self._on_send_file)
        self._input_bar.typing_changed.connect(self._on_local_typing)

    # ── Discovery handlers ─────────────────────────────────────────────────────

    def _on_peer_found(self, ip: str, name: str) -> None:
        self._sidebar.add_peer(ip, name)
        if ip not in self._history:
            self._history[ip] = _HistoryEntry()
        self._status(f"  {name}  ({ip}) joined the network")

    def _on_peer_lost(self, ip: str) -> None:
        name = self._sidebar.get_peer_name(ip)
        self._sidebar.remove_peer(ip)
        if self._active_ip == ip:
            self._active_ip = None
            self._chat_area.show_placeholder()
            self._input_bar.set_enabled(False)
        self._status(f"  {name}  ({ip}) left the network")

    def _on_peer_updated(self, ip: str, name: str) -> None:
        self._sidebar.update_peer_name(ip, name)
        if self._active_ip == ip:
            self._chat_area.set_peer(name, ip)

    # ── Messaging handlers ─────────────────────────────────────────────────────

    def _on_message_received(
        self, sender_ip: str, sender_name: str, text: str, ts: float
    ) -> None:
        # Ensure history entry exists (peer may have come online mid-session)
        if sender_ip not in self._history:
            self._history[sender_ip] = _HistoryEntry()
            self._sidebar.add_peer(sender_ip, sender_name)

        entry = self._history[sender_ip]
        entry.add_msg(outgoing=False, text=text, sender=sender_name, ts=ts)

        if self._active_ip == sender_ip:
            self._chat_area.add_message(
                text=text, sender=sender_name, timestamp=ts, outgoing=False
            )
        else:
            self._sidebar.mark_unread(sender_ip)

    def _on_typing_changed(self, sender_ip: str, is_typing: bool) -> None:
        if self._active_ip == sender_ip:
            name = self._sidebar.get_peer_name(sender_ip)
            self._chat_area.set_typing(name, is_typing)

    def _on_send_failed(self, ip: str, reason: str) -> None:
        self._status(f"⚠ Send to {ip} failed: {reason}")

    # ── File transfer handlers ─────────────────────────────────────────────────

    def _on_incoming_file(
        self,
        sender_ip: str,
        sender_name: str,
        filename: str,
        size_str: str,
        transfer_id: str,
    ) -> None:
        if sender_ip not in self._history:
            self._history[sender_ip] = _HistoryEntry()
            self._sidebar.add_peer(sender_ip, sender_name)

        ts = time.time()
        entry = self._history[sender_ip]
        entry.add_file(
            outgoing=False, sender=sender_name, ts=ts,
            filename=filename, size_str=size_str, transfer_id=transfer_id,
        )

        if self._active_ip == sender_ip:
            self._chat_area.add_file_bubble(
                filename=filename, size_str=size_str, outgoing=False,
                sender=sender_name, timestamp=ts, transfer_id=transfer_id,
            )
        else:
            self._sidebar.mark_unread(sender_ip)

    def _on_transfer_progress(
        self, transfer_id: str, done: int, total: int
    ) -> None:
        self._chat_area.update_transfer(transfer_id, done, total)

    def _on_transfer_complete(
        self, transfer_id: str, success: bool, message: str
    ) -> None:
        # Retrieve the local save path (set by _on_file_received for incoming files)
        local_path = self._transfer_paths.get(transfer_id)
        self._chat_area.finish_transfer(transfer_id, success, local_path)
        icon = "✓" if success else "✗"
        self._status(f"{icon} {message}")

    def _on_file_received(
        self, sender_ip: str, filename: str, local_path: str, transfer_id: str
    ) -> None:
        # Store the local save path keyed by transfer_id so that when
        # transfer_complete fires next, the bubble's "Open folder" button
        # gets the correct path.
        self._transfer_paths[transfer_id] = local_path

    # ── UI action handlers ─────────────────────────────────────────────────────

    def _on_device_selected(self, ip: str, name: str) -> None:
        self._active_ip = ip
        self._chat_area.set_peer(name, ip)
        self._chat_area.clear()
        self._input_bar.set_enabled(True)
        self._input_bar.focus()

        # Replay history
        entry = self._history.get(ip, _HistoryEntry())
        for msg in entry.messages:
            if msg["type"] == "msg":
                self._chat_area.add_message(
                    text=msg["text"],
                    sender=msg["sender"],
                    timestamp=msg["ts"],
                    outgoing=msg["outgoing"],
                )
            elif msg["type"] == "file":
                self._chat_area.add_file_bubble(
                    filename=msg["filename"],
                    size_str=msg["size_str"],
                    outgoing=msg["outgoing"],
                    sender=msg["sender"],
                    timestamp=msg["ts"],
                    transfer_id=msg["transfer_id"],
                )

    def _on_send_message(self, text: str) -> None:
        if not self._active_ip:
            return

        ts = time.time()
        entry = self._history.setdefault(self._active_ip, _HistoryEntry())
        entry.add_msg(
            outgoing=True, text=text,
            sender=self._local_name, ts=ts,
        )
        self._chat_area.add_message(
            text=text, sender=self._local_name,
            timestamp=ts, outgoing=True,
        )

        # Deliver in a background thread to keep the UI snappy
        import threading
        threading.Thread(
            target=self._messaging.send_message,
            args=(self._active_ip, text),
            daemon=True,
        ).start()

    def _on_send_file(self, path: str) -> None:
        if not self._active_ip:
            return

        from core.file_transfer import fmt_size
        size_str    = fmt_size(Path(path).stat().st_size)
        filename    = Path(path).name
        ts          = time.time()
        transfer_id = self._files.send_file(self._active_ip, path)

        entry = self._history.setdefault(self._active_ip, _HistoryEntry())
        entry.add_file(
            outgoing=True, sender=self._local_name, ts=ts,
            filename=filename, size_str=size_str, transfer_id=transfer_id,
        )
        self._chat_area.add_file_bubble(
            filename=filename, size_str=size_str, outgoing=True,
            sender=self._local_name, timestamp=ts, transfer_id=transfer_id,
        )

    def _on_local_typing(self, is_typing: bool) -> None:
        if self._active_ip:
            self._messaging.send_typing(self._active_ip, is_typing)

    # ── Username management ────────────────────────────────────────────────────

    def _rename_self(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Change Display Name",
            "Enter your new display name:",
            QLineEdit.Normal,
            self._local_name,
        )
        if ok and name.strip():
            name = name.strip()[:32]
            self._local_name = name
            self._discovery.set_name(name)
            self._messaging.set_name(name)
            self._files.set_name(name)
            self._sidebar.update_local_name(name)
            self._name_lbl.setText(f"👤  {name}")
            self._save_name(name)
            self._status(f"Display name changed to '{name}'")

    def _load_or_ask_name(self) -> str:
        settings = QSettings("LanChat", "LanChat")
        saved = settings.value(self._SETTINGS_KEY_NAME, "")
        if saved:
            return str(saved)
        # Default: machine hostname (sanitised)
        default = socket.gethostname().split(".")[0][:20] or "User"
        return default

    def _save_name(self, name: str) -> None:
        QSettings("LanChat", "LanChat").setValue(self._SETTINGS_KEY_NAME, name)

    # ── Status bar helper ──────────────────────────────────────────────────────

    def _status(self, msg: str) -> None:
        self._status_bar.showMessage(msg, 8_000)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_name(self._local_name)
        self._discovery.stop()
        self._messaging.stop()
        self._files.stop()
        event.accept()

    # ── Global stylesheet ──────────────────────────────────────────────────────

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            /* ── Base ───────────────────────────────────────────────────── */
            QMainWindow, QWidget {
                background-color: #111111;
                color: #ffffff;
                font-family: 'Segoe UI', 'Ubuntu', 'Helvetica Neue', sans-serif;
                font-size: 13px;
            }

            /* ── Scroll bars (global) ───────────────────────────────────── */
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 6px;
                border-radius: 3px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical { background: none; }

            /* ── QDialog ────────────────────────────────────────────────── */
            QDialog {
                background-color: #1c1c1c;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QDialogButtonBox QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 16px;
                color: #fff;
                min-width: 70px;
            }
            QDialogButtonBox QPushButton:hover  { background: #333; }
            QDialogButtonBox QPushButton:pressed { background: #444; }

            /* ── QInputDialog ───────────────────────────────────────────── */
            QInputDialog QLineEdit {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 10px;
                color: #fff;
            }

            /* ── QMessageBox ────────────────────────────────────────────── */
            QMessageBox { background: #1c1c1c; }
            QMessageBox QLabel { color: #fff; }

            /* ── Splitter handle ────────────────────────────────────────── */
            QSplitter::handle { background: #2d2d2d; width: 1px; }

            /* ── Status bar ─────────────────────────────────────────────── */
            QStatusBar { background: #111; color: #555; font-size: 11px; }
            """
        )
