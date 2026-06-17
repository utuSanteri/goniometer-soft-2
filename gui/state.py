"""
Shared mutable container for connected hardware objects.

Every tab receives the same ``HardwareState`` instance so that
hardware connected on the Connect tab is immediately visible
to all other tabs — no signal wiring needed.
"""


class HardwareState:
    def __init__(self):
        self.motor = None
        self.spec = None
        self.source = None