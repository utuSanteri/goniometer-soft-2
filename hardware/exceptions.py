# hardware/exceptions.py
"""
Shared hardware exception hierarchy.

Both hardware/sourcemeter.py and hardware/keysight_sourcemeter.py import
from here. This avoids a cross-module dependency between two sibling modules
and gives ScanWorker a single, stable set of types to catch.
"""


class HardwareError(Exception):
    """Base class for all hardware-related errors in this project."""


class SourceMeterError(HardwareError):
    """
    Raised when the source meter encounters a fault condition,
    a compliance trip, an HTTP 500 from the microservice, or a
    communication timeout.

    ScanWorker catches this type to halt a scan gracefully and
    attempt a safe motor stop.
    """


class HardwareDisconnectedError(HardwareError):
    """
    Raised when the underlying hardware service or physical device
    cannot be reached (e.g. microservice is not running, VISA
    resource not found, serial port absent).

    Distinct from SourceMeterError so the UI can distinguish
    "instrument faulted" from "instrument not reachable".
    """