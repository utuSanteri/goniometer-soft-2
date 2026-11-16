"""
Read-only QTextEdit that receives Python log records.
"""

import logging
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QObject, pyqtSignal, Qt


class _LogSignaller(QObject):
    sig_message = pyqtSignal(str)


class QTextEditHandler(logging.Handler):
    """Routes ``logging`` records into a QTextEdit widget.

    Log records can come from any thread (e.g. the scan worker), but Qt
    widgets may only be touched from the GUI thread — doing otherwise
    crashes the whole process at random.  So records are forwarded via a
    queued signal and the widget is only updated in the GUI thread.
    """

    def __init__(self, widget: QTextEdit):
        super().__init__()
        self._w = widget
        self._signaller = _LogSignaller()
        self._signaller.sig_message.connect(
            self._append, Qt.QueuedConnection)

    def emit(self, record):
        try:
            self._signaller.sig_message.emit(self.format(record))
        except Exception:
            self.handleError(record)

    def _append(self, msg: str):
        self._w.append(msg)
        self._w.verticalScrollBar().setValue(
            self._w.verticalScrollBar().maximum())


def create_log_panel() -> QTextEdit:
    """Factory for the standard log text box."""
    box = QTextEdit()
    box.setReadOnly(True)
    box.setFont(QFont("Courier", 8))
    box.setMaximumHeight(180)
    box.document().setMaximumBlockCount(5000)
    return box
