"""
ui/input_bar.py
───────────────
Bottom input area for composing and sending messages / attaching files.

InputBar
  • Multi-line QTextEdit that grows up to ~5 lines.
  • Send button (and Enter key) to dispatch text messages.
  • Shift+Enter inserts a newline instead of sending.
  • Paperclip button opens a file picker.
  • Emits typing_changed whenever the user starts or stops typing,
    with a 2-second debounce to avoid flooding the peer.
  • Disabled when no peer is selected.

Signals emitted by InputBar:
  message_ready(text)      → user wants to send a text message
  file_chosen(path)        → user picked a file to send
  typing_changed(active)   → user started / stopped typing
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _GrowingTextEdit(QTextEdit):
    """
    A QTextEdit that reports when Enter is pressed (for send-on-Enter),
    while Shift+Enter still inserts a newline.  Also starts compact and
    grows up to a maximum height.
    """

    enter_pressed = Signal()

    _MIN_H = 38
    _MAX_H = 120

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(self._MIN_H)
        self.setMaximumHeight(self._MAX_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.document().contentsChanged.connect(self._adjust_height)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and not (event.modifiers() & Qt.ShiftModifier)
        ):
            self.enter_pressed.emit()
            return
        super().keyPressEvent(event)

    def _adjust_height(self) -> None:
        doc_h = int(self.document().size().height()) + 12
        new_h = max(self._MIN_H, min(doc_h, self._MAX_H))
        if self.height() != new_h:
            self.setFixedHeight(new_h)


class InputBar(QWidget):
    """
    Composed input bar at the bottom of the chat window.

    Signals
    -------
    message_ready(text)     User wants to send *text*.
    file_chosen(path)       User picked *path* for file transfer.
    typing_changed(active)  Debounced typing state changes.
    """

    message_ready  = Signal(str)   # text
    file_chosen    = Signal(str)   # file path
    typing_changed = Signal(bool)  # is_typing

    _TYPING_DEBOUNCE_MS = 2_000   # emit typing=False after 2 s of silence

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_typing   = False
        self._active_peer = False   # whether a peer is currently selected

        # Debounce timer: fires when user stops typing
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._on_typing_stopped)

        self._build_ui()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "background-color: #1a1a1a; border-top: 1px solid #2d2d2d;"
        )
        self.setFixedHeight(62)    # will expand slightly with the text edit

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # ── Attachment button ──────────────────────────────────────────────────
        self._attach_btn = QToolButton()
        self._attach_btn.setText("📎")
        self._attach_btn.setFixedSize(36, 36)
        self._attach_btn.setToolTip("Attach a file")
        self._attach_btn.setStyleSheet(
            """
            QToolButton {
                background-color: #2a2a2a;
                border: none;
                border-radius: 18px;
                font-size: 16px;
                color: #aaaaaa;
            }
            QToolButton:hover { background-color: #333; color: #fff; }
            QToolButton:disabled { color: #444; }
            """
        )
        self._attach_btn.clicked.connect(self._pick_file)
        outer.addWidget(self._attach_btn, 0, Qt.AlignBottom)

        # ── Text input ─────────────────────────────────────────────────────────
        self._input = _GrowingTextEdit()
        self._input.setPlaceholderText("Message…")
        self._input.setStyleSheet(
            """
            QTextEdit {
                background-color: #2a2a2a;
                border: 1px solid #383838;
                border-radius: 18px;
                padding: 8px 14px;
                color: #ffffff;
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #555; }
            QTextEdit:disabled {
                color: #444; border-color: #2a2a2a; background: #222;
            }
            """
        )
        self._input.enter_pressed.connect(self._on_send)
        self._input.textChanged.connect(self._on_text_changed)
        outer.addWidget(self._input)

        # ── Send button ────────────────────────────────────────────────────────
        self._send_btn = QToolButton()
        self._send_btn.setText("➤")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.setStyleSheet(
            """
            QToolButton {
                background-color: #7eb8f7;
                border: none;
                border-radius: 18px;
                font-size: 15px;
                color: #111111;
                font-weight: 700;
            }
            QToolButton:hover { background-color: #9ecaff; }
            QToolButton:pressed { background-color: #5a9be8; }
            QToolButton:disabled { background-color: #2a2a2a; color: #444; }
            """
        )
        self._send_btn.clicked.connect(self._on_send)
        outer.addWidget(self._send_btn, 0, Qt.AlignBottom)

        self.set_enabled(False)   # disabled until a peer is selected

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        """Enable / disable all interactive elements."""
        self._active_peer = enabled
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        self._attach_btn.setEnabled(enabled)
        placeholder = "Message…" if enabled else "Select a device to start chatting"
        self._input.setPlaceholderText(placeholder)

    def clear(self) -> None:
        self._input.clear()

    def focus(self) -> None:
        self._input.setFocus()

    # ── Private handlers ───────────────────────────────────────────────────────

    def _on_send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or not self._active_peer:
            return
        # Stop typing indicator before sending
        self._stop_typing()
        self._input.clear()
        self.message_ready.emit(text)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select a file to send")
        if path:
            self.file_chosen.emit(path)

    def _on_text_changed(self) -> None:
        if not self._active_peer:
            return
        has_text = bool(self._input.toPlainText().strip())
        if has_text and not self._is_typing:
            self._is_typing = True
            self.typing_changed.emit(True)
        elif not has_text and self._is_typing:
            self._stop_typing()
            return

        if has_text:
            # Reset the debounce timer on every keystroke
            self._typing_timer.start(self._TYPING_DEBOUNCE_MS)

    def _on_typing_stopped(self) -> None:
        if self._is_typing:
            self._stop_typing()

    def _stop_typing(self) -> None:
        self._typing_timer.stop()
        if self._is_typing:
            self._is_typing = False
            self.typing_changed.emit(False)
