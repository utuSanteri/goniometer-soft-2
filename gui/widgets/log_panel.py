"""
Read-only QTextEdit that receives Python log records.
"""

import logging
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtGui import QFont


class QTextEditHandler(logging.Handler):
    """Routes ``logging`` records into a QTextEdit widget."""

    def __init__(self, widget: QTextEdit):
        super().__init__()
        self._w = widget

    def emit(self, record):
        msg = self.format(record)
        self._w.append(msg)
        self._w.verticalScrollBar().setValue(
            self._w.verticalScrollBar().maximum())


def create_log_panel() -> QTextEdit:
    """Factory for the standard log text box."""
    box = QTextEdit()
    box.setReadOnly(True)
    box.setFont(QFont("Courier", 8))
    box.setMaximumHeight(180)
    return box