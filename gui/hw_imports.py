"""
Hardware Abstraction Layer (HAL) Import Module.

This module provides a centralized entry point for all hardware components 
and error types used throughout the GUI application.

DESIGN PATTERN:
To facilitate testing without physical hardware, this module implements a 
simple toggle between real hardware implementations and mock implementations.

HOW TO SWITCH:
1. For Real Hardware: 
   Uncomment the imports from the `hardware` module and 
   comment out the imports from the `hardware_mock` module.
2. For Mock/Testing: 
   Ensure the `hardware_mock` imports are active (default state).

Components exported:
    - MotorController, Spectrometer, SourceMeter, KeysightSourceMeter
    - HardwareError, HardwareDisconnectedError, SourceMeterError
"""

# ── Real hardware ──────────────────────────────────────────────────
from hardware import MotorController, Spectrometer, SourceMeter, KeysightSourceMeter
from hardware.exceptions import HardwareError, HardwareDisconnectedError, SourceMeterError

# ── Mock hardware for testing ──────────────────────────────────────
#from hardware_mock import MotorController, Spectrometer, SourceMeter, KeysightSourceMeter, SourceMeterError

__all__ = ["MotorController", "Spectrometer", "SourceMeter", "KeysightSourceMeter", "HardwareError", "HardwareDisconnectedError", "SourceMeterError"]