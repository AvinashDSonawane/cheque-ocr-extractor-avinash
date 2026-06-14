"""
license_guard.py
----------------
MAC-address-based license protection for PayeeExtract Pro.
Organization : MJIT Solution
Contact      : 9168045353

Usage (in main_app.py, before anything else):
    from license_guard import check_license
    check_license()   # exits the process if unauthorized
"""

import sys
import hashlib
import uuid
from typing import List

# ---------------------------------------------------------------------------
# PyQt5 imports — only loaded when needed for the dialog
# ---------------------------------------------------------------------------
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy
)
from PyQt5.QtCore  import Qt
from PyQt5.QtGui   import QIcon

# ---------------------------------------------------------------------------
# AUTHORIZED MAC ADDRESSES
# Hash each MAC so they are never stored as plain text in the binary.
# ---------------------------------------------------------------------------

def _hash_mac(mac: str) -> str:
    """SHA-256 hash of a normalised MAC string."""
    normalised = mac.strip().upper().replace(":", "-")
    return hashlib.sha256(normalised.encode()).hexdigest()

AUTHORIZED_MAC_HASHES: List[str] = [
    _hash_mac("A0-8C-FD-C5-3E-83"),
    _hash_mac("88-A4-C2-40-95-BE"),
    _hash_mac("E0-D5-5E-14-4E-10"),
    _hash_mac("F8-BC-12-8E-30-20"),
    _hash_mac("18-60-24-DD-A9-3D"),
    _hash_mac("40-B0-34-1D-DA-90"),
    _hash_mac("38-D5-7A-02-ED-1B")
]

# ---------------------------------------------------------------------------
# MAC DETECTION
# ---------------------------------------------------------------------------

def _get_system_mac_hashes() -> List[str]:
    """Collect all MAC addresses present on this machine and return their hashes."""
    macs = set()

    # Method 1 — uuid
    try:
        raw = uuid.getnode()
        mac_str = "-".join(f"{(raw >> (8 * i)) & 0xFF:02X}" for i in reversed(range(6)))
        macs.add(mac_str)
    except Exception:
        pass

    # Method 2 — netifaces
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            link  = addrs.get(netifaces.AF_LINK, [])
            for entry in link:
                addr = entry.get("addr", "")
                if addr and addr != "00-00-00-00-00-00":
                    macs.add(addr.upper().replace(":", "-"))
    except Exception:
        pass

    # Method 3 — getmac
    try:
        import getmac
        mac = getmac.get_mac_address()
        if mac:
            macs.add(mac.upper().replace(":", "-"))
    except Exception:
        pass

    return [_hash_mac(m) for m in macs]


def is_authorized() -> bool:
    system_hashes = _get_system_mac_hashes()
    authorized    = set(AUTHORIZED_MAC_HASHES)
    return any(h in authorized for h in system_hashes)

# ---------------------------------------------------------------------------
# STYLED UNAUTHORIZED DIALOG
# ---------------------------------------------------------------------------

class _UnauthorizedDialog(QDialog):
    """Sleek dark dialog shown when the device is not licensed."""

    _BG_DARK    = "#0D0D0D"
    _BG_CARD    = "#141414"
    _GOLD       = "#C9A84C"
    _GOLD_LIGHT = "#E8C97A"
    _WHITE      = "#F5F5F5"
    _MUTED      = "#888888"
    _RED        = "#C0392B"

    def __init__(self):
        if QApplication.instance() is None:
            self._app = QApplication(sys.argv)
        else:
            self._app = None

        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # [FIX]: Replaced setFixedSize with setMinimumSize. 
        # Hardcoded setFixedSize causes elements to clip and compress when OS text scaling/DPI is non-default.
        self.setMinimumSize(540, 480)
        self.resize(540, 480)
        self.setWindowTitle("PayeeExtract Pro — Unauthorized")
        self._center_on_screen()
        self._build_ui()
        self._apply_styles()

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        x = (screen.width()  - self.width())  // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Gold top accent bar ───────────────────────────────────────
        accent_bar = QFrame()
        accent_bar.setFixedHeight(4)
        accent_bar.setStyleSheet(f"background: qlineargradient("
                                 f"x1:0, y1:0, x2:1, y2:0, "
                                 f"stop:0 {self._GOLD}, stop:0.5 {self._GOLD_LIGHT}, "
                                 f"stop:1 {self._GOLD});")
        root.addWidget(accent_bar)

        # ── Main card ────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        
        # [FIX]: Increased layout margins internally to give more breathing room
        card_layout.setContentsMargins(48, 48, 48, 40)
        # [FIX]: Use standard layout spacing instead of hardcoded `addSpacing(x)`, letting PyQt adapt.
        card_layout.setSpacing(24)

        # Lock icon
        lock_lbl = QLabel("🔒")
        lock_lbl.setAlignment(Qt.AlignCenter)
        lock_lbl.setStyleSheet("font-size: 46px; background: transparent;")
        card_layout.addWidget(lock_lbl)

        # App & Org Grouped properly
        title_group = QFrame()
        title_layout = QVBoxLayout(title_group)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        app_name = QLabel("PayeeExtract Pro")
        app_name.setAlignment(Qt.AlignCenter)
        app_name.setObjectName("appName")
        title_layout.addWidget(app_name)

        org_lbl = QLabel("MJIT SOLUTION")
        org_lbl.setAlignment(Qt.AlignCenter)
        org_lbl.setObjectName("orgName")
        title_layout.addWidget(org_lbl)
        
        card_layout.addWidget(title_group)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setObjectName("divider")
        card_layout.addWidget(div)

        # Unauthorized message
        msg = QLabel("This device is not authorized\nto run this software.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setObjectName("mainMsg")
        card_layout.addWidget(msg)

        # Contact block
        contact_frame = QFrame()
        contact_frame.setObjectName("contactFrame")
        contact_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        contact_layout = QVBoxLayout(contact_frame)
        # [FIX]: Apply spacing using `setContentsMargins` instead of CSS `padding: Xpx;` 
        # to guarantee the text does not get clipped vertically.
        contact_layout.setContentsMargins(20, 20, 20, 20)
        contact_layout.setSpacing(8)

        contact_title = QLabel("TO ACTIVATE YOUR LICENSE")
        contact_title.setAlignment(Qt.AlignCenter)
        contact_title.setObjectName("contactTitle")
        contact_layout.addWidget(contact_title)

        contact_no = QLabel("CALL:  +91  9168045353")
        contact_no.setAlignment(Qt.AlignCenter)
        contact_no.setObjectName("contactNo")
        contact_layout.addWidget(contact_no)

        card_layout.addWidget(contact_frame)

        # Extends main spacing dynamically instead of compressing it
        card_layout.addStretch()

        # Exit button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        exit_btn = QPushButton("Exit Application")
        exit_btn.setObjectName("exitBtn")
        exit_btn.setFixedSize(180, 42)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.clicked.connect(self._on_exit)
        btn_row.addWidget(exit_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        root.addWidget(card)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._BG_DARK};
                border: 1px solid {self._GOLD};
                border-radius: 2px;
            }}
            QFrame#card {{
                background-color: {self._BG_CARD};
            }}
            QLabel#appName {{
                font-family: 'Georgia', 'Times New Roman', serif;
                font-size: 26px;
                font-weight: bold;
                color: {self._GOLD_LIGHT};
                background: transparent;
                letter-spacing: 2px;
            }}
            QLabel#orgName {{
                font-family: 'Georgia', 'Times New Roman', serif;
                font-size: 16px;
                font-weight: bold;
                color: {self._GOLD};
                background: transparent;
                letter-spacing: 6px;
            }}
            QFrame#divider {{
                color: #2a2a2a;
                background-color: #2a2a2a;
                max-height: 1px;
            }}
            QLabel#mainMsg {{
                font-family: 'Segoe UI', sans-serif;
                font-size: 15px;
                color: {self._WHITE};
                background: transparent;
                line-height: 1.6;
            }}
            QFrame#contactFrame {{
                background-color: #222222;
                border: 2px solid {self._GOLD};
                border-left: 5px solid {self._GOLD_LIGHT};
                border-radius: 6px;
            }}
            QLabel#contactTitle {{
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                color: #bbbbbb;
                background: transparent;
                letter-spacing: 2px;
            }}
            QLabel#contactNo {{
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: 18px;
                font-weight: bold;
                color: #FFFFFF;
                background: transparent;
                letter-spacing: 1px;
                min-height: 28px;
                padding-bottom: 6px;
            }}
            QPushButton#exitBtn {{
                background-color: transparent;
                color: {self._MUTED};
                border: 1px solid #333333;
                border-radius: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                font-weight: 500;
                letter-spacing: 1px;
            }}
            QPushButton#exitBtn:hover {{
                background-color: {self._RED};
                color: #ffffff;
                border-color: {self._RED};
            }}
            QPushButton#exitBtn:pressed {{
                background-color: #922b21;
            }}
        """)

    def _on_exit(self):
        self.reject()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPos() - self._drag_pos)

    def run_and_exit(self):
        self.exec_()
        sys.exit(1)


def check_license():
    if not is_authorized():
        app = QApplication.instance() or QApplication(sys.argv)
        dialog = _UnauthorizedDialog()
        dialog.run_and_exit()


if __name__ == "__main__":
    print("System MAC hashes detected:")
    for h in _get_system_mac_hashes():
        print(f"  {h}")

    print("\\nAuthorized:", is_authorized())

    app = QApplication.instance() or QApplication(sys.argv)
    dlg = _UnauthorizedDialog()
    dlg.run_and_exit()
