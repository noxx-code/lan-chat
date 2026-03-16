"""
ui/chat_area.py
───────────────
Scrollable chat history panel.

ChatArea manages:
  • A vertical list of BubbleWidget / FileBubbleWidget entries.
  • A placeholder shown when no peer is selected.
  • A "typing…" bar at the bottom that auto-hides.
  • Auto-scroll to the latest message.
  • A lookup dict so transfer bubbles can be updated by transfer_id.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .message_bubble import BubbleWidget, FileBubbleWidget


class ChatArea(QWidget):
    """
    Container for message bubbles.

    Public methods
    ──────────────
    set_peer(name)              Switch to a different conversation.
    clear()                     Remove all bubbles.
    add_message(...)            Append a text bubble.
    add_file_bubble(...)        Append a file-transfer bubble.
    update_transfer(...)        Update an existing file bubble's progress.
    set_typing(name, active)    Show / hide the typing indicator.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._peer_name = ""
        # transfer_id -> FileBubbleWidget
        self._file_bubbles: dict[str, FileBubbleWidget] = {}

        self._build_ui()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Peer header bar ────────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(52)
        self._header.setStyleSheet(
            "background-color: #1c1c1c; border-bottom: 1px solid #2d2d2d;"
        )
        h_layout = QVBoxLayout(self._header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        self._peer_label = QLabel("Select a contact")
        self._peer_label.setStyleSheet(
            "color: #ffffff; font-size: 15px; font-weight: 600; background: transparent;"
        )
        h_layout.addWidget(self._peer_label)

        self._peer_status = QLabel("No device selected")
        self._peer_status.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; background: transparent;"
        )
        h_layout.addWidget(self._peer_status)
        root.addWidget(self._header)

        # ── Scroll area ────────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            """
            QScrollArea { border: none; background-color: #181818; }
            QScrollBar:vertical {
                background: #1a1a1a; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #444; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        # Inner widget that holds all bubbles
        self._inner = QWidget()
        self._inner.setStyleSheet("background-color: #181818;")
        self._bubbles_layout = QVBoxLayout(self._inner)
        self._bubbles_layout.setContentsMargins(0, 10, 0, 10)
        self._bubbles_layout.setSpacing(2)
        self._bubbles_layout.addStretch()   # pushes content to the top

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

        # ── Placeholder (shown when no peer selected) ──────────────────────────
        self._placeholder = QLabel("👆  Select a device from the sidebar\nto start chatting")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "color: #555; font-size: 14px; background: #181818;"
        )
        self._placeholder.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        root.addWidget(self._placeholder)
        self._placeholder.setVisible(True)
        self._scroll.setVisible(False)

        # ── Typing indicator ───────────────────────────────────────────────────
        self._typing_bar = QLabel()
        self._typing_bar.setFixedHeight(24)
        self._typing_bar.setContentsMargins(16, 0, 0, 0)
        self._typing_bar.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; font-style: italic;"
            "background: #181818; border-top: 1px solid #1e1e1e;"
        )
        self._typing_bar.setVisible(False)
        root.addWidget(self._typing_bar)

        # Timer to auto-hide the typing indicator
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(lambda: self._typing_bar.setVisible(False))

    # ── Public interface ───────────────────────────────────────────────────────

    def set_peer(self, name: str, ip: str) -> None:
        """Update the header and show the chat area."""
        self._peer_name = name
        self._peer_label.setText(name)
        self._peer_status.setText(ip)
        self._placeholder.setVisible(False)
        self._scroll.setVisible(True)

    def show_placeholder(self) -> None:
        self._peer_label.setText("Select a contact")
        self._peer_status.setText("No device selected")
        self._placeholder.setVisible(True)
        self._scroll.setVisible(False)

    def clear(self) -> None:
        """Remove all bubble widgets (called when switching conversations)."""
        self._file_bubbles.clear()
        layout = self._bubbles_layout
        # Remove all widgets except the trailing stretch
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_message(
        self,
        text: str,
        sender: str,
        timestamp: float,
        outgoing: bool,
    ) -> None:
        """Insert a text bubble and scroll to the bottom."""
        bubble = BubbleWidget(text, sender, timestamp, outgoing, self._inner)
        self._insert_bubble(bubble)

    def add_file_bubble(
        self,
        filename: str,
        size_str: str,
        outgoing: bool,
        sender: str,
        timestamp: float,
        transfer_id: str,
    ) -> FileBubbleWidget:
        """Insert a file-transfer bubble and return it for later updates."""
        bubble = FileBubbleWidget(
            filename, size_str, outgoing, sender, timestamp, self._inner
        )
        self._file_bubbles[transfer_id] = bubble
        self._insert_bubble(bubble)
        return bubble

    def update_transfer(
        self, transfer_id: str, done: int, total: int
    ) -> None:
        bubble = self._file_bubbles.get(transfer_id)
        if bubble:
            bubble.set_progress(done, total)

    def finish_transfer(
        self,
        transfer_id: str,
        success: bool,
        local_path: str | None = None,
    ) -> None:
        bubble = self._file_bubbles.get(transfer_id)
        if bubble:
            bubble.mark_complete(success, local_path)

    def set_typing(self, name: str, active: bool) -> None:
        """Show or hide the 'name is typing…' bar."""
        if active:
            self._typing_bar.setText(f"{name} is typing…")
            self._typing_bar.setVisible(True)
            self._typing_timer.start(5_000)  # auto-hide after 5 s
        else:
            self._typing_timer.stop()
            self._typing_bar.setVisible(False)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _insert_bubble(self, bubble: QWidget) -> None:
        """Add *bubble* before the trailing stretch, then scroll down."""
        layout = self._bubbles_layout
        # The last item is always the stretch → insert at count-1
        layout.insertWidget(layout.count() - 1, bubble)
        # Defer scroll so the layout has time to resize first
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
