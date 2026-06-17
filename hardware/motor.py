"""
Arduino-based motor controller.
"""

import time
import logging
import serial

from hardware._base import BaseMotorController

log = logging.getLogger(__name__)


class MotorController(BaseMotorController):
    """Wraps the Arduino serial protocol."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 10.0,
                 steps_per_degree: float = 88.89,
                 max_speed: int = 2000,
                 m1_invert: bool = False,
                 m2_invert: bool = False):
        self.steps_per_degree = steps_per_degree
        self.max_speed = max_speed
        self.m1_invert = m1_invert
        self.m2_invert = m2_invert
        self._ser = None
        self._port = port
        self._baud = baud
        self._timeout = timeout

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        self._ser = serial.Serial(self._port, self._baud,
                                  timeout=self._timeout)
        time.sleep(2.0)
        resp = self._ser.readline().decode().strip()
        if resp != "READY":
            raise ConnectionError(
                f"Arduino did not say READY, got: {resp!r}\n"
                "Check the COM port in config.yaml")
        self._send_speed(self.max_speed)
        log.info("Motor controller connected on %s", self._port)

    def disconnect(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            log.info("Motor controller disconnected")

    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── Low-level ─────────────────────────────────────────────────────
    def _cmd(self, msg: str) -> str:
        self._ser.write((msg + "\n").encode())
        resp = self._ser.readline().decode().strip()
        return resp

    def _send_speed(self, steps_per_sec: int):
        r = self._cmd(f"SPEED {steps_per_sec}")
        if r != "OK":
            raise RuntimeError(f"SPEED command failed: {r}")

    # ── Public API ────────────────────────────────────────────────────
    def move_steps(self, motor: int, steps: int, direction: int):
        if not self.is_connected():
            raise RuntimeError("Motor controller not connected")
        if (motor == 1 and self.m1_invert) or (motor == 2 and self.m2_invert):
            direction = 1 - direction
        r = self._cmd(f"MOVE {motor} {abs(steps)} {direction}")
        if r != "OK":
            raise RuntimeError(f"MOVE failed: {r}")

    def move_degrees(self, motor: int, degrees: float):
        steps = int(round(abs(degrees) * self.steps_per_degree))
        direction = 1 if degrees >= 0 else 0
        self.move_steps(motor, steps, direction)

    def stop(self):
        self._cmd("STOP")

    def zero(self):
        r = self._cmd("ZERO")
        if r != "OK":
            raise RuntimeError(f"ZERO failed: {r}")

    def home(self):
        r = self._cmd("HOME")
        if r != "OK":
            raise RuntimeError(f"HOME failed: {r}")

    def get_position(self) -> tuple:
        resp = self._cmd("STATUS")
        parts = resp.split()
        return int(parts[1]), int(parts[2])

    def ping(self) -> bool:
        try:
            return self._cmd("PING") == "PONG"
        except Exception:
            return False

    def set_speed(self, steps_per_sec: int):
        self._send_speed(steps_per_sec)