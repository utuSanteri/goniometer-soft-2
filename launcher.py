"""Launcher — keeps the top-level directory clean."""

import os
import sys
import logging

from PyQt5.QtWidgets import QApplication

from gui import MainWindow, load_config

logging.getLogger().setLevel(logging.DEBUG)

# Run from the program's own folder so config.yaml and relative save
# paths work the same from source and from the PyInstaller .exe
BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

cfg = load_config("config.yaml")
app = QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow(cfg)
win.show()
sys.exit(app.exec_())