"""Launcher — keeps the top-level directory clean."""

import os
import sys
import logging
import traceback
import faulthandler

# Run from the program's own folder so config.yaml and relative save
# paths work the same from source and from the PyInstaller .exe
BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

# ── Startup log ───────────────────────────────────────────────────
# The .exe has no console, so errors would otherwise be invisible.
LOG_PATH = os.path.join(BASE_DIR, "goniometer.log")
_log_file = open(LOG_PATH, "w", buffering=1, encoding="utf-8")
logging.basicConfig(
    level=logging.DEBUG, stream=_log_file,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("matplotlib").setLevel(logging.INFO)
log = logging.getLogger("launcher")

# Native crashes (e.g. in a driver DLL) and hangs: dump Python stacks
faulthandler.enable(_log_file)
faulthandler.dump_traceback_later(90, exit=False, file=_log_file)


def _excepthook(exc_type, exc, tb):
    msg = "".join(traceback.format_exception(exc_type, exc, tb))
    log.critical("Unhandled exception:\n%s", msg)
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        _app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Error", f"{msg}\n\nLog: {LOG_PATH}")
    except Exception:
        pass


sys.excepthook = _excepthook

log.info("Starting from %s (frozen=%s)", BASE_DIR,
         getattr(sys, "frozen", False))

from PyQt5.QtWidgets import QApplication  # noqa: E402

log.info("Importing GUI (first run builds the matplotlib font cache, "
         "which can take a minute)")
from gui import MainWindow, load_config  # noqa: E402

log.info("Loading config.yaml")
cfg = load_config("config.yaml")
app = QApplication(sys.argv)
app.setStyle("Fusion")
log.info("Building main window")
win = MainWindow(cfg)
win.show()
faulthandler.cancel_dump_traceback_later()
log.info("Main window shown")
sys.exit(app.exec_())
