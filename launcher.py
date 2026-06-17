"""Launcher — keeps the top-level directory clean."""

import sys
import logging

from PyQt5.QtWidgets import QApplication

from gui import MainWindow, load_config

logging.getLogger().setLevel(logging.DEBUG)

cfg = load_config("config.yaml")
app = QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow(cfg)
win.show()
sys.exit(app.exec_())