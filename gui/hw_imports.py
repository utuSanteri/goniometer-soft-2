"""
Hardware Abstraction Layer (HAL) Import Module.

This module provides a centralized entry point for all hardware components
and error types used throughout the GUI application.

HOW TO SWITCH:
Real hardware is the default. To run on the mock instruments instead
(no hardware or drivers needed), start the app with --mock:

    python launcher.py --mock
    python -m gui --mock

or set the environment variable GONIO_MOCK=1.

Components exported:
    - MotorController, Spectrometer, SourceMeter, KeysightSourceMeter
    - find_source_meter, make_source_meter
    - HardwareError, HardwareDisconnectedError, SourceMeterError
    - MOCK (True when the mock instruments are in use)
"""

import os
import sys

MOCK = ("--mock" in sys.argv or
        os.environ.get("GONIO_MOCK", "").strip().lower()
        in ("1", "true", "yes", "on"))

if MOCK:
    # ── Mock hardware for testing ──────────────────────────────────
    from hardware_mock import (
        MotorController, Spectrometer, SourceMeter, KeysightSourceMeter,
        find_source_meter, make_source_meter,
        HardwareError, HardwareDisconnectedError, SourceMeterError,
    )
else:
    # ── Real hardware ──────────────────────────────────────────────
    from hardware import (
        MotorController, Spectrometer, SourceMeter, KeysightSourceMeter,
        find_source_meter, make_source_meter,
    )
    from hardware.exceptions import (
        HardwareError, HardwareDisconnectedError, SourceMeterError,
    )

__all__ = ["MotorController", "Spectrometer", "SourceMeter", "KeysightSourceMeter",
           "find_source_meter", "make_source_meter", "HardwareError",
           "HardwareDisconnectedError", "SourceMeterError", "MOCK"]
