"""
gui/styles.py
-------------
Qt stylesheet constants for light mode, dark mode, and the
always-red Stop button.  Import these into main_window.py so
the set_dark_mode() method stays concise and easy to tweak.
"""

DARK_STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #2d2d2d;
        color: #ffffff;
    }
    QGroupBox {
        background-color: #3a3a3a;
        border: 1px solid #555555;
        border-radius: 8px;
        margin-top: 8px;
        font-weight: bold;
        color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
    QPushButton {
        background-color: #ffffff;
        color: #000000;
        border: none;
        border-radius: 6px;
        padding: 4px 14px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #e0e0e0;
    }
    QPushButton:pressed {
        background-color: #c0c0c0;
    }
    QPushButton:disabled {
        background-color: #444444;
        color: #888888;
    }
    QTableWidget {
        background-color: #3a3a3a;
        alternate-background-color: #444444;
        gridline-color: #888888;
        color: #ffffff;
        selection-background-color: #5a6e7a;
    }
    QHeaderView::section {
        background-color: #ffffff;
        color: #000000;
        border: none;
        padding: 5px;
        font-weight: bold;
    }
    QTextEdit, QLineEdit, QComboBox {
        background-color: #444444;
        color: #ffffff;
        border: 1px solid #555555;
        border-radius: 5px;
    }
    QProgressBar {
        background-color: #444444;
        border: 1px solid #555555;
        border-radius: 5px;
        text-align: center;
        color: #ffffff;
    }
    QProgressBar::chunk {
        background-color: #ffffff;
        border-radius: 4px;
    }
    QSplitter::handle { background-color: #555555; }
    QScrollBar:vertical { background: #2d2d2d; width: 10px; }
    QScrollBar::handle:vertical { background: #666666; border-radius: 5px; }
    QStatusBar { background-color: #2d2d2d; color: #aaaaaa; }
"""

LIGHT_STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #ffffff;
        color: #000000;
    }
    QGroupBox {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 8px;
        margin-top: 8px;
        font-weight: bold;
        color: #000000;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
    QPushButton {
        background-color: #000000;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 4px 14px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #222222;
    }
    QPushButton:pressed {
        background-color: #444444;
    }
    QPushButton:disabled {
        background-color: #cccccc;
        color: #888888;
    }
    QTableWidget {
        background-color: #ffffff;
        alternate-background-color: #f5f5f5;
        gridline-color: #999999;
        color: #000000;
        selection-background-color: #b0c4de;
    }
    QHeaderView::section {
        background-color: #000000;
        color: #ffffff;
        border: none;
        padding: 5px;
        font-weight: bold;
    }
    QTextEdit, QLineEdit, QComboBox {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 5px;
        color: #000000;
    }
    QProgressBar {
        background-color: #eeeeee;
        border: 1px solid #cccccc;
        border-radius: 5px;
        text-align: center;
        color: #000000;
    }
    QProgressBar::chunk {
        background-color: #000000;
        border-radius: 4px;
    }
    QSplitter::handle { background-color: #cccccc; }
    QScrollBar:vertical { background: #f5f5f5; width: 10px; }
    QScrollBar::handle:vertical { background: #aaaaaa; border-radius: 5px; }
    QStatusBar { background-color: #f5f5f5; color: #555555; }
"""

STOP_BTN_STYLESHEET = """
    QPushButton {
        background-color: #cc0000;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 4px 14px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #e60000;
    }
    QPushButton:pressed {
        background-color: #990000;
    }
    QPushButton:disabled {
        background-color: #7f0000;
        color: #cccccc;
    }
"""

CELL_INFO_DARK  = "padding: 4px; background-color: #3a3a3a; border-radius: 4px; color: #ffffff;"
CELL_INFO_LIGHT = "padding: 4px; background-color: #f0f0f0; border-radius: 4px; color: #000000;"
