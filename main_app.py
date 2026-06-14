# ============================================================
#  Cheque OCR Extractor — Entry Point
# ============================================================
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import warnings
warnings.filterwarnings('ignore')

import os
import sys

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"

# ------------------------------------------------------------------
# Hardcoded API key — no .env file needed
# ------------------------------------------------------------------
os.environ["GEMINI_API_KEY"] = "AIzaSXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
os.environ["GOOGLE_API_KEY"] = "AIzaSXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

# ------------------------------------------------------------------
# Launch the application
# ------------------------------------------------------------------
from PyQt5.QtWidgets import QApplication
from gui.main_window import ChequeOCRGUI

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ChequeOCRGUI()
    window.show()
    sys.exit(app.exec_())