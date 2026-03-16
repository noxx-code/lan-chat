"""
ui/message_bubble.py
────────────────────
Individual message bubble widgets rendered inside ChatArea.

BubbleWidget
  Draws a single message: sender name (incoming only), text body,
  and a timestamp.  Outgoing bubbles are aligned to the right;
  incoming ones to the left.  Colours and radii come from the
  application-wide QSS colour palette.

FileBubbleWidget
  Variant for file-transfer events: shows filename, size, and a
  progress bar that can be updated later via set_progress().
  When complete, an "Open folder" button appears.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _ts_label(timestamp: float) -> str:
    """Format a Unix timestamp as 'HH:MM'."""
    return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M")


# ── Colour constants (kept in sync with the global stylesheet) ─────────────────

_BUBBLE_OUT  = "#3a3a3a"
_BUBBLE_IN   = "#2b2b2b"
_TEXT_PRI    = "#ffffff"
_TEXT_SEC    = "#aaaaaa"
_BORDER      = "#444444"
_BUBBLE_R    = 14        # corner radius in pixels


class BubbleWidget(QWidget):
    """
    A single text-message bubble.

    Parameters
    ----------
    text      : message body
    sender    : display name (shown above incoming bubbles only)
    timestamp : Unix float used to render the time string
    outgoing  : True → right-aligned dark bubble; False → left-aligned
    """

    def __init__(
        self,
        text: str,
        sender: str,
        timestamp: float,
        outgoing: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._build(text, sender, timestamp, outgoing)

    def _build(
        self, text: str, sender: str, timestamp: float, outgoing: bool
    ) -> None:
        colour = _BUBBLE_OUT if outgoing else _BUBBLE_IN
        align  = Qt.AlignRight if outgoing else Qt.AlignLeft

        # ── Outer row: spacer on one side to push bubble left/right ──────────
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 2, 6, 2)
        outer.setSpacing(0)

        bubble = QWidget()
        bubble.setObjectName("Bubble")
        bubble.setStyleSheet(
            f"""
            QWidget#Bubble {{
                background-color: {colour};
                border-radius: {_BUBBLE_R}px;
            }}
            """
        )
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        bubble.setMaximumWidth(480)

        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(12, 8, 12, 8)
        inner.setSpacing(3)

        # Sender name – only for incoming messages
        if not outgoing and sender:
            name_lbl = QLabel(sender)
            name_lbl.setStyleSheet(
                f"color: #7eb8f7; font-size: 11px; font-weight: 600;"
            )
            inner.addWidget(name_lbl)

        # Message text
        body_lbl = QLabel(text)
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        body_lbl.setStyleSheet(
            f"color: {_TEXT_PRI}; font-size: 13px; background: transparent;"
        )
        inner.addWidget(body_lbl)

        # Timestamp
        time_lbl = QLabel(_ts_label(timestamp))
        time_lbl.setAlignment(Qt.AlignRight)
        time_lbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: 10px; background: transparent;"
        )
        inner.addWidget(time_lbl)

        # Assemble: spacer on the opposite side to the bubble
        if outgoing:
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()


class FileBubbleWidget(QWidget):
    """
    A bubble that represents a file transfer in progress or completed.

    Call set_progress(done, total) to update the progress bar.
    Call mark_complete(success, local_path) to finalise the display.
    """

    def __init__(
        self,
        filename: str,
        size_str: str,
        outgoing: bool,
        sender: str,
        timestamp: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._local_path: str | None = None
        self._build(filename, size_str, outgoing, sender, timestamp)

    def _build(
        self,
        filename: str,
        size_str: str,
        outgoing: bool,
        sender: str,
        timestamp: float,
    ) -> None:
        colour = _BUBBLE_OUT if outgoing else _BUBBLE_IN

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 2, 6, 2)
        outer.setSpacing(0)

        bubble = QWidget()
        bubble.setObjectName("FileBubble")
        bubble.setStyleSheet(
            f"""
            QWidget#FileBubble {{
                background-color: {colour};
                border-radius: {_BUBBLE_R}px;
                border: 1px solid {_BORDER};
            }}
            """
        )
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        bubble.setMinimumWidth(260)
        bubble.setMaximumWidth(380)

        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(6)

        # Sender
        if not outgoing and sender:
            name_lbl = QLabel(sender)
            name_lbl.setStyleSheet(
                "color: #7eb8f7; font-size: 11px; font-weight: 600;"
            )
            inner.addWidget(name_lbl)

        # Icon + filename row
        file_lbl = QLabel(f"📎  {filename}")
        file_lbl.setStyleSheet(
            f"color: {_TEXT_PRI}; font-size: 13px; font-weight: 500; background: transparent;"
        )
        file_lbl.setWordWrap(True)
        inner.addWidget(file_lbl)

        # Size
        size_lbl = QLabel(size_str)
        size_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent;")
        inner.addWidget(size_lbl)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setStyleSheet(
            """
            QProgressBar {
                background-color: #555;
                border-radius: 2px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #7eb8f7;
                border-radius: 2px;
            }
            """
        )
        inner.addWidget(self._progress)

        # Status label (replaces bar when done)
        self._status = QLabel("Transferring…")
        self._status.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: 11px; background: transparent;"
        )
        inner.addWidget(self._status)

        # Open-folder button (hidden until complete)
        self._open_btn = QPushButton("📂  Open folder")
        self._open_btn.setVisible(False)
        self._open_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: #7eb8f7;
                border: 1px solid #7eb8f7;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #2a4060; }}
            """
        )
        self._open_btn.clicked.connect(self._open_folder)
        inner.addWidget(self._open_btn)

        # Timestamp
        time_lbl = QLabel(_ts_label(timestamp))
        time_lbl.setAlignment(Qt.AlignRight)
        time_lbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: 10px; background: transparent;"
        )
        inner.addWidget(time_lbl)

        if outgoing:
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()

    # ── Public update methods ──────────────────────────────────────────────────

    def set_progress(self, done: int, total: int) -> None:
        """Update the progress bar (call from the main thread)."""
        if total > 0:
            pct = int(done * 100 / total)
            self._progress.setValue(pct)
            self._status.setText(f"{pct}%  ({_fmt(done)} / {_fmt(total)})")

    def mark_complete(self, success: bool, local_path: str | None = None) -> None:
        """Hide the progress bar and show the result."""
        self._progress.setVisible(False)
        if success:
            self._status.setText("✓ Transfer complete")
            self._status.setStyleSheet(
                "color: #5cb85c; font-size: 11px; background: transparent;"
            )
            if local_path:
                self._local_path = local_path
                self._open_btn.setVisible(True)
        else:
            self._status.setText("✗ Transfer failed")
            self._status.setStyleSheet(
                "color: #d9534f; font-size: 11px; background: transparent;"
            )

    def _open_folder(self) -> None:
        if self._local_path:
            folder = str(Path(self._local_path).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def _fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n //= 1024
    return f"{n} GB"
