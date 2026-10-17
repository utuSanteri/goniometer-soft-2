"""
hardware __init__.py
───────────────────────────────────────────────────────────────────────
Abstraction layer for all instrument hardware.

Consumers should continue to import from here:

    from hardware import MotorController, Spectrometer, SourceMeter, keysight_sourcemeter
    from hardware.exceptions import HardwareDisconnectedError, SourceMeterError
"""

from hardware._base import (
    BaseMotorController,
    BaseSpectrometer,
    BaseSourceMeter,
)
from hardware.motor import MotorController
from hardware.spectrometer import Spectrometer
from hardware.sourcemeter import SourceMeter
from hardware.keysight_sourcemeter import KeysightSourceMeter
from hardware.sourcemeter_registry import find_source_meter, make_source_meter
from hardware.exceptions import HardwareDisconnectedError, SourceMeterError
__all__ = [
    # Abstract bases (for mocks / alternative implementations)
    "BaseMotorController",
    "BaseSpectrometer",
    "BaseSourceMeter",
    # Concrete implementations
    "MotorController",
    "Spectrometer",
    "SourceMeter",
    "KeysightSourceMeter",
    "find_source_meter",
    "make_source_meter",
    "SourceMeterError",
    "HardwareDisconnectedError",
]