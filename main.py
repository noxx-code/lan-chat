"""
main.py
───────
LAN Chat – entry point.

Responsibilities
────────────────
• Bootstrap the QApplication with the global grayscale theme.
• Show a first-launch "Set your name" dialog when no username is saved.
• Launch the MainWindow.
• Handle top-level exceptions gracefully.

Usage
─────
    python main.py

Requirements
────────────
    pip install PySide6
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("lan_chat.main")


# ── First-launch dialog ────────────────────────────────────────────────────────

class WelcomeDialog(QDialog):
    """
    Shown once on first launch to capture the user's display name.
    Dismissed automatically if a name is already stored in QSettings.
    """

    def __init__(self, default_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to LAN Chat")
        self.setFixedSize(360, 170)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        greeting = QLabel("👋  Welcome!  Choose a display name:")
        greeting.setStyleSheet("color: #ffffff; font-size: 14px;")
        layout.addWidget(greeting)

        hint = QLabel("Other devices on the network will see this name.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._edit = QLineEdit(default_name)
        self._edit.setMaxLength(32)
        self._edit.setStyleSheet(
            "QLineEdit {"
            "  background: #2a2a2a; border: 1px solid #444; border-radius: 8px;"
            "  padding: 8px 12px; color: #fff; font-size: 13px;"
            "}"
            "QLineEdit:focus { border-color: #7eb8f7; }"
        )
        self._edit.selectAll()
        layout.addWidget(self._edit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.setStyleSheet(
            "QPushButton {"
            "  background: #7eb8f7; border: none; border-radius: 8px;"
            "  padding: 8px 24px; color: #111; font-weight: 700;"
            "}"
            "QPushButton:hover { background: #9ecaff; }"
        )
        btns.accepted.connect(self._validate)
        layout.addWidget(btns)

        self._edit.returnPressed.connect(self._validate)

    def _validate(self) -> None:
        name = self._edit.text().strip()
        if name:
            self.accept()
        else:
            self._edit.setStyleSheet(
                self._edit.styleSheet()
                + " QLineEdit { border-color: #d9534f; }"
            )

    @property
    def chosen_name(self) -> str:
        return self._edit.text().strip()


# ── Application setup ──────────────────────────────────────────────────────────

def _configure_app(app: QApplication) -> None:
    """Set application-level font and base palette."""
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    # Dark base palette so Qt-drawn widgets (scroll arrows, etc.) are dark
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor("#111111"))
    palette.setColor(QPalette.WindowText,      QColor("#ffffff"))
    palette.setColor(QPalette.Base,            QColor("#1c1c1c"))
    palette.setColor(QPalette.AlternateBase,   QColor("#222222"))
    palette.setColor(QPalette.Text,            QColor("#ffffff"))
    palette.setColor(QPalette.Button,          QColor("#2a2a2a"))
    palette.setColor(QPalette.ButtonText,      QColor("#ffffff"))
    palette.setColor(QPalette.Highlight,       QColor("#7eb8f7"))
    palette.setColor(QPalette.HighlightedText, QColor("#111111"))
    palette.setColor(QPalette.ToolTipBase,     QColor("#2a2a2a"))
    palette.setColor(QPalette.ToolTipText,     QColor("#ffffff"))
    app.setPalette(palette)


def _maybe_show_welcome(app: QApplication) -> str | None:
    """
    Return a display name to use:
      - The stored name (if any) → no dialog shown.
      - The name the user typed in the welcome dialog.
      - None if the dialog was cancelled (app should quit).
    """
    import socket
    settings = QSettings("LanChat", "LanChat")
    saved = settings.value("username", "")
    if saved:
        return str(saved)

    default = socket.gethostname().split(".")[0][:20] or "User"
    dlg = WelcomeDialog(default)
    if dlg.exec() == QDialog.Accepted:
        name = dlg.chosen_name
        settings.setValue("username", name)
        return name
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LAN Chat")
    app.setOrganizationName("LanChat")
    app.setApplicationVersion("1.0.0")

    _configure_app(app)

    name = _maybe_show_welcome(app)
    if name is None:
        log.info("Welcome dialog cancelled – exiting.")
        return 0

    try:
        # Import deferred so the QApplication exists before any Qt objects
        from ui.main_window import MainWindow

        window = MainWindow()
        window.show()
        return app.exec()

    except Exception as exc:  # pragma: no cover
        log.exception("Fatal error: %s", exc)
        QMessageBox.critical(
            None,
            "LAN Chat – Fatal Error",
            f"An unexpected error occurred:\n\n{exc}\n\n"
            "Check the console for details.",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
