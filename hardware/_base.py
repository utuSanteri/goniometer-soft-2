"""
Abstract base classes for every instrument category.

Mock implementations and alternative hardware drivers should subclass
these so that type-checking and interface compliance are enforced.
"""

from abc import ABC, abstractmethod


class BaseMotorController(ABC):
    """Interface that every motor controller must implement."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def move_steps(self, motor: int, steps: int, direction: int): ...

    @abstractmethod
    def move_degrees(self, motor: int, degrees: float): ...

    @abstractmethod
    def stop(self): ...

    @abstractmethod
    def zero(self): ...

    @abstractmethod
    def home(self): ...

    @abstractmethod
    def get_position(self) -> tuple: ...

    @abstractmethod
    def ping(self) -> bool: ...

    @abstractmethod
    def set_speed(self, steps_per_sec: int): ...


class BaseSpectrometer(ABC):
    """Interface that every spectrometer must implement."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_integration_time(self, ms: float): ...

    @abstractmethod
    def set_scans_to_average(self, n: int): ...

    @abstractmethod
    def set_boxcar_width(self, w: int): ...

    @abstractmethod
    def collect_dark(self): ...

    @abstractmethod
    def clear_dark(self): ...

    @abstractmethod
    def acquire(self, subtract_dark: bool = True) -> tuple: ...

    @abstractmethod
    def has_dark(self) -> bool: ...


class BaseSourceMeter(ABC):
    """Interface that every source-meter must implement."""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_voltage(self, v: float): ...

    @abstractmethod
    def set_current_limit(self, a: float): ...

    @abstractmethod
    def set_source_mode(self, mode: str): ...

    @abstractmethod
    def output_on(self): ...

    @abstractmethod
    def output_off(self): ...

    @abstractmethod
    def verify_operation(self) -> dict: ...

    @abstractmethod
    def measure(self) -> float: ...

    @abstractmethod
    def get_output_state(self) -> bool: ...