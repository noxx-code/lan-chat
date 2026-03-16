"""
ui/device_sidebar.py
────────────────────
Left-panel sidebar showing discovered LAN peers.

DeviceSidebar
  • Search bar at the top that filters the list in real-time.
  • A scrollable list of DeviceRow widgets, one per peer.
  • Emits device_selected(ip, name) when a row is clicked.
  • Supports adding, removing, and updating rows without rebuilding
    the whole list.

DeviceRow
  • Circular "online" dot (green).
  • Device display name (bold) and IP address below it.
  • Highlighted when selected.
  • Shows an unread-count badge when there are unseen messages.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── Individual device row ──────────────────────────────────────────────────────

class DeviceRow(QWidget):
    """
    A single clickable row in the peer list.

    Parameters
    ----------
    name : Display name of the peer.
    ip   : IP address string (also used as a unique key).
    """

    clicked = Signal(str, str)  # ip, name

    _NORMAL_STYLE = """
        QWidget#DeviceRow {{
            background-color: {bg};
            border-radius: 8px;
        }}
        QWidget#DeviceRow:hover {{
            background-color: #252525;
        }}
    """
    _BG_DEFAULT  = "#1c1c1c"
    _BG_SELECTED = "#2a2a2a"

    def __init__(self, name: str, ip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ip   = ip
        self._name = name
        self._selected  = False
        self._unread    = 0
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.setObjectName("DeviceRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(60)
        self._apply_style(False)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)

        # Online dot
        dot = QLabel("●")
        dot.setFixedSize(10, 10)
        dot.setStyleSheet("color: #4caf50; font-size: 8px; background: transparent;")
        row.addWidget(dot)

        # Text block
        text_block = QVBoxLayout()
        text_block.setSpacing(2)

        self._name_lbl = QLabel(self._name)
        self._name_lbl.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 600; background: transparent;"
        )
        self._name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_block.addWidget(self._name_lbl)

        self._ip_lbl = QLabel(self._ip)
        self._ip_lbl.setStyleSheet(
            "color: #888888; font-size: 11px; background: transparent;"
        )
        text_block.addWidget(self._ip_lbl)
        row.addLayout(text_block)

        # Unread badge
        self._badge = QLabel()
        self._badge.setFixedSize(20, 20)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setStyleSheet(
            """
            QLabel {
                background-color: #7eb8f7;
                color: #111111;
                border-radius: 10px;
                font-size: 10px;
                font-weight: 700;
            }
            """
        )
        self._badge.setVisible(False)
        row.addWidget(self._badge)

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._ip, self._name)
        super().mousePressEvent(event)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def name(self) -> str:
        return self._name

    def set_name(self, name: str) -> None:
        self._name = name
        self._name_lbl.setText(name)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style(selected)
        if selected:
            self.clear_unread()

    def add_unread(self) -> None:
        self._unread += 1
        self._badge.setText(str(self._unread) if self._unread < 100 else "99+")
        self._badge.setVisible(True)

    def clear_unread(self) -> None:
        self._unread = 0
        self._badge.setVisible(False)

    # ── Private ────────────────────────────────────────────────────────────────

    def _apply_style(self, selected: bool) -> None:
        bg = self._BG_SELECTED if selected else self._BG_DEFAULT
        self.setStyleSheet(self._NORMAL_STYLE.format(bg=bg))


# ── Sidebar container ──────────────────────────────────────────────────────────

class DeviceSidebar(QWidget):
    """
    Left-panel peer list.

    Signals
    -------
    device_selected(ip, name)  Emitted when the user clicks a row.
    """

    device_selected = Signal(str, str)  # ip, name

    def __init__(self, local_name: str, local_ip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._local_ip = local_ip
        self._rows: dict[str, DeviceRow] = {}    # ip -> DeviceRow
        self._selected_ip: str | None = None
        self._build(local_name, local_ip)

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build(self, local_name: str, local_ip: str) -> None:
        self.setFixedWidth(260)
        self.setStyleSheet("background-color: #1c1c1c;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── "Me" header ────────────────────────────────────────────────────────
        me_widget = QWidget()
        me_widget.setFixedHeight(64)
        me_widget.setStyleSheet(
            "background-color: #161616; border-bottom: 1px solid #2d2d2d;"
        )
        me_layout = QVBoxLayout(me_widget)
        me_layout.setContentsMargins(14, 8, 14, 8)
        me_layout.setSpacing(2)

        self._me_name = QLabel(local_name)
        self._me_name.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 700; background: transparent;"
        )
        me_layout.addWidget(self._me_name)

        me_ip = QLabel(local_ip)
        me_ip.setStyleSheet(
            "color: #666; font-size: 10px; background: transparent;"
        )
        me_layout.addWidget(me_ip)
        root.addWidget(me_widget)

        # ── Search bar ─────────────────────────────────────────────────────────
        search_container = QWidget()
        search_container.setFixedHeight(48)
        search_container.setStyleSheet("background: #1c1c1c; padding: 8px 10px;")
        sc_layout = QHBoxLayout(search_container)
        sc_layout.setContentsMargins(8, 6, 8, 6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search devices…")
        self._search.setStyleSheet(
            """
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #383838;
                border-radius: 14px;
                padding: 4px 12px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #555; }
            """
        )
        self._search.textChanged.connect(self._filter_rows)
        sc_layout.addWidget(self._search)
        root.addWidget(search_container)

        # ── Devices label ──────────────────────────────────────────────────────
        lbl = QLabel("DEVICES ON THIS NETWORK")
        lbl.setContentsMargins(14, 8, 0, 4)
        lbl.setStyleSheet(
            "color: #555; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            "background: #1c1c1c;"
        )
        root.addWidget(lbl)

        # ── Scrollable row list ────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            """
            QScrollArea { border: none; background: #1c1c1c; }
            QScrollBar:vertical {
                background: #1c1c1c; width: 4px;
            }
            QScrollBar::handle:vertical {
                background: #333; border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: #1c1c1c;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 4, 8, 4)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll)

        # ── Empty state label ──────────────────────────────────────────────────
        self._empty_lbl = QLabel("No devices found.\nWaiting for peers…")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(
            "color: #444; font-size: 12px; background: #1c1c1c;"
        )
        self._empty_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._empty_lbl)
        self._empty_lbl.setVisible(True)
        self._scroll.setVisible(False)

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_local_name(self, name: str) -> None:
        self._me_name.setText(name)

    def add_peer(self, ip: str, name: str) -> None:
        """Add a new peer row (or update if already present)."""
        if ip in self._rows:
            self._rows[ip].set_name(name)
            return
        row = DeviceRow(name, ip, self._list_widget)
        row.clicked.connect(self._on_row_clicked)
        self._rows[ip] = row
        # Insert before the trailing stretch
        layout = self._list_layout
        layout.insertWidget(layout.count() - 1, row)
        self._refresh_empty_state()

    def remove_peer(self, ip: str) -> None:
        row = self._rows.pop(ip, None)
        if row:
            row.deleteLater()
        if self._selected_ip == ip:
            self._selected_ip = None
        self._refresh_empty_state()

    def update_peer_name(self, ip: str, name: str) -> None:
        if ip in self._rows:
            self._rows[ip].set_name(name)

    def mark_unread(self, ip: str) -> None:
        """Increment the unread badge for a peer (if not currently selected)."""
        if ip != self._selected_ip and ip in self._rows:
            self._rows[ip].add_unread()

    def get_peer_name(self, ip: str) -> str:
        row = self._rows.get(ip)
        return row.name if row else ip

    # ── Private ────────────────────────────────────────────────────────────────

    def _on_row_clicked(self, ip: str, name: str) -> None:
        # Deselect previous
        if self._selected_ip and self._selected_ip in self._rows:
            self._rows[self._selected_ip].set_selected(False)
        self._selected_ip = ip
        self._rows[ip].set_selected(True)
        self.device_selected.emit(ip, name)

    def _filter_rows(self, query: str) -> None:
        q = query.lower()
        for row in self._rows.values():
            visible = (not q) or q in row.name.lower() or q in row.ip
            row.setVisible(visible)

    def _refresh_empty_state(self) -> None:
        has_peers = bool(self._rows)
        self._empty_lbl.setVisible(not has_peers)
        self._scroll.setVisible(has_peers)
