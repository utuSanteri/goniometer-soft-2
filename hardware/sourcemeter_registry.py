"""
Source-meter registry and auto-detection.

To support a new instrument: subclass BaseSourceMeter, give it an
IDN_MATCH string (a substring of its *IDN? reply) and add it to DRIVERS.
Nothing else in the app names a specific model.
"""

import inspect
import logging

from hardware._visa import get_resource_manager
from hardware.sourcemeter import SourceMeter
from hardware.keysight_sourcemeter import KeysightSourceMeter

log = logging.getLogger(__name__)

DRIVERS = [SourceMeter, KeysightSourceMeter]

AUTO = "auto"


def _driver_by_name(name: str):
    for cls in DRIVERS:
        if cls.__name__ == name:
            return cls
    raise ValueError(
        f"Unknown source-meter driver {name!r}. "
        f"Known: {[c.__name__ for c in DRIVERS]}")


def find_source_meter(resource: str = AUTO, driver: str = AUTO):
    """
    Returns (driver_class, resource, idn). idn is "" when detection was
    skipped (both resource and driver given).

    Serial (ASRL) ports are never opened: opening the Arduino's port
    resets it and loses the angle zero.
    """
    if resource != AUTO and driver != AUTO:
        return _driver_by_name(driver), resource, ""

    candidates = DRIVERS if driver == AUTO else [_driver_by_name(driver)]
    rm = get_resource_manager()
    if resource != AUTO:
        addresses = [resource]
    else:
        addresses = [r for r in rm.list_resources()
                     if not r.upper().startswith("ASRL")]

    seen = []
    for addr in addresses:
        try:
            inst = rm.open_resource(addr)
            try:
                inst.timeout = 2000
                idn = inst.query("*IDN?").strip()
            finally:
                inst.close()
        except Exception as e:
            log.debug("No *IDN? reply from %s: %s", addr, e)
            continue
        seen.append(f"{addr}: {idn}")
        for cls in candidates:
            if cls.IDN_MATCH in idn:
                log.info("Found %s at %s (%s)", cls.__name__, addr, idn)
                return cls, addr, idn

    raise RuntimeError(
        "No supported source meter found.\n"
        f"Tried: {addresses or 'no VISA resources'}\n"
        f"Replies: {seen or 'none'}\n"
        f"Drivers: {[c.__name__ for c in candidates]}")


def make_source_meter(cls, **options):
    """Builds a driver, passing only the options its constructor
    accepts (e.g. 'channel' only goes to multi-channel drivers)."""
    accepted = inspect.signature(cls).parameters
    return cls(**{k: v for k, v in options.items() if k in accepted})
