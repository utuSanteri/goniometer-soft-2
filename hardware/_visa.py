"""
Shared VISA resource-manager loader.

Used by any instrument that communicates over NI-VISA (e.g. Keithley 2461).
"""

import logging
import pyvisa

log = logging.getLogger(__name__)


def get_resource_manager() -> pyvisa.ResourceManager:
    """
    Use NI-VISA (system install).  User needs NI drivers:
    https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html
    """
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        log.debug("NI-VISA resources: %s", resources)

        usb_resources = [r for r in resources if r.startswith("USB")]
        if usb_resources:
            log.info("NI-VISA found USB devices: %s", usb_resources)
        else:
            log.warning(
                "NI-VISA running but no USB devices found yet. "
                "Is the instrument powered on and plugged in?")

        return rm

    except Exception as e:
        raise RuntimeError(
            f"NI-VISA not found or failed: {e}\n\n"
            "Install NI-VISA from:\n"
            "https://www.ni.com/en/support/downloads/drivers/"
            "download.ni-visa.html"
        )