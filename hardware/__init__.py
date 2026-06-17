"""
hardware
───────────────────────────────────────────────────────────────────────
Abstraction layer for all instrument hardware.

Consumers should continue to import from here:

    from hardware import MotorController, Spectrometer, SourceMeter, SourceMeterError
"""

from hardware._base import (
    BaseMotorController,
    BaseSpectrometer,
    BaseSourceMeter,
)
from hardware.motor import MotorController
from hardware.spectrometer import Spectrometer
from hardware.sourcemeter import SourceMeter, SourceMeterError

__all__ = [
    # Abstract bases (for mocks / alternative implementations)
    "BaseMotorController",
    "BaseSpectrometer",
    "BaseSourceMeter",
    # Concrete implementations
    "MotorController",
    "Spectrometer",
    "SourceMeter",
    "SourceMeterError",
]