"""
Centralised hardware import — swap mock / real in this one place.
"""

# ── Real hardware ──────────────────────────────────────────────────
#from hardware import MotorController, Spectrometer, SourceMeter, SourceMeterError

# ── Mock hardware for testing ──────────────────────────────────────
from hardware_mock import MotorController, Spectrometer, SourceMeter, SourceMeterError

__all__ = ["MotorController", "Spectrometer", "SourceMeter", "SourceMeterError"]