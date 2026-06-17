"""
Entry point:  python -m gui
"""

import sys
import logging

from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.util import load_config

log = logging.getLogger()
log.setLevel(logging.DEBUG)

if __name__ == "__main__":
    cfg = load_config("config.yaml")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(cfg)
    win.show()
    sys.exit(app.exec_())