"""Launcher — keeps the top-level directory clean."""

import sys
import logging
import os

from PyQt5.QtWidgets import QApplication

from gui import MainWindow, load_config

# Change the current working directory to the script's directory
# This ensures that relative paths in the application are resolved correctly
os.chdir(os.path.dirname(os.path.abspath(__file__)))

logging.getLogger().setLevel(logging.DEBUG)

cfg = load_config("config.yaml")
app = QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow(cfg)
win.show()
sys.exit(app.exec_())