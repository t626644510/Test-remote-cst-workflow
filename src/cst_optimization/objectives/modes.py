"""Optimization modes: reusable penalty and utility functions.

Each mode maps a raw physical value to a scalar penalty where lower is better.
This decouples the optimization strategy from the physics computation, so the
same quantity can be reused with different optimization semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from .registry import register_mode


class OptimizationMode(ABC):
    """Abstract base for a penalty function."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def compute(self, raw_value: float) -> float:
        """Map a raw physical value to a penalty (lower is better)."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


def _soft_saturating_penalty(z: float, power: float = 1.0) -> float:
    """Map a scaled non-negative deviation to a bounded soft penalty."""
    z = max(float(z), 0.0)
    power = max(float(power), 1e-12)
    zp = z ** power
    return float(zp / (1.0 + zp))


@register_mode("minimize")
class Minimize(OptimizationMode):
    """Raw value as penalty: smaller values are better."""

    name: ClassVar[str] = "minimize"
    description: ClassVar[str] = "Smaller raw value is better"

    def compute(self, raw_value: float) -> float:
        return float(raw_value)


@register_mode("maximize")
class Maximize(OptimizationMode):
    """Negated raw value: larger values are better."""

    name: ClassVar[str] = "maximize"
    description: ClassVar[str] = "Larger raw value is better"

    def compute(self, raw_value: float) -> float:
        return -float(raw_value)


@register_mode("greater_than")
class GreaterThan(OptimizationMode):
    """Bounded exponential penalty when the value falls below a threshold."""

    name: ClassVar[str] = "greater_than"
    description: ClassVar[str] = "Bounded penalty below a minimum threshold"

    def __init__(self, threshold: float, sigma: float = 0.5) -> None:
        self._threshold = float(threshold)
        self._sigma = float(sigma)

    def compute(self, raw_value: float) -> float:
        x = float(raw_value)
        if x >= self._threshold:
            return 0.0
        return float(1.0 - np.exp(-(self._threshold - x) / self._sigma))

    def __repr__(self) -> str:
        return f"GreaterThan(t={self._threshold}, sigma={self._sigma})"


@register_mode("less_than")
class LessThan(OptimizationMode):
    """Bounded exponential penalty when the value exceeds a threshold."""

    name: ClassVar[str] = "less_than"
    description: ClassVar[str] = "Bounded penalty above a maximum threshold"

    def __init__(self, threshold: float, sigma: float = 0.5) -> None:
        self._threshold = float(threshold)
        self._sigma = float(sigma)

    def compute(self, raw_value: float) -> float:
        x = float(raw_value)
        if x <= self._threshold:
            return 0.0
        return float(1.0 - np.exp(-(x - self._threshold) / self._sigma))

    def __repr__(self) -> str:
        return f"LessThan(t={self._threshold}, sigma={self._sigma})"


@register_mode("tolerance")
class GaussianTolerance(OptimizationMode):
    """Gaussian penalty centered on a target value."""

    name: ClassVar[str] = "tolerance"
    description: ClassVar[str] = "Gaussian penalty around a target"

    def __init__(self, target: float, sigma: float) -> None:
        self._target = float(target)
        self._sigma = float(sigma)

    def compute(self, raw_value: float) -> float:
        z = (float(raw_value) - self._target) / self._sigma
        return float(1.0 - np.exp(-0.5 * z * z))

    def __repr__(self) -> str:
        return f"GaussianTolerance(target={self._target}, sigma={self._sigma})"


@register_mode("tolerance_soft")
class SoftTolerance(OptimizationMode):
    """Soft target penalty with a zero-penalty deadband."""

    name: ClassVar[str] = "tolerance_soft"
    description: ClassVar[str] = "Soft bounded target penalty with a deadband"

    def __init__(
        self,
        target: float,
        tolerance: float = 0.0,
        scale: float = 1.0,
        power: float = 1.0,
    ) -> None:
        self._target = float(target)
        self._tolerance = max(float(tolerance), 0.0)
        self._scale = max(float(scale), 1e-12)
        self._power = max(float(power), 1e-12)

    def compute(self, raw_value: float) -> float:
        delta = abs(float(raw_value) - self._target)
        if delta <= self._tolerance:
            return 0.0
        z = (delta - self._tolerance) / self._scale
        return _soft_saturating_penalty(z, self._power)

    def __repr__(self) -> str:
        return (
            "SoftTolerance("
            f"target={self._target}, tol={self._tolerance}, "
            f"scale={self._scale}, p={self._power})"
        )


@register_mode("less_than_soft")
class SoftLessThan(OptimizationMode):
    """Soft bounded penalty above a maximum threshold."""

    name: ClassVar[str] = "less_than_soft"
    description: ClassVar[str] = "Soft bounded penalty above a maximum threshold"

    def __init__(
        self,
        threshold: float,
        tolerance: float = 0.0,
        scale: float = 1.0,
        power: float = 1.0,
    ) -> None:
        self._threshold = float(threshold)
        self._tolerance = max(float(tolerance), 0.0)
        self._scale = max(float(scale), 1e-12)
        self._power = max(float(power), 1e-12)

    def compute(self, raw_value: float) -> float:
        limit = self._threshold + self._tolerance
        x = float(raw_value)
        if x <= limit:
            return 0.0
        z = (x - limit) / self._scale
        return _soft_saturating_penalty(z, self._power)

    def __repr__(self) -> str:
        return (
            "SoftLessThan("
            f"t={self._threshold}, tol={self._tolerance}, "
            f"scale={self._scale}, p={self._power})"
        )


@register_mode("greater_than_soft")
class SoftGreaterThan(OptimizationMode):
    """Soft bounded penalty below a minimum threshold."""

    name: ClassVar[str] = "greater_than_soft"
    description: ClassVar[str] = "Soft bounded penalty below a minimum threshold"

    def __init__(
        self,
        threshold: float,
        tolerance: float = 0.0,
        scale: float = 1.0,
        power: float = 1.0,
    ) -> None:
        self._threshold = float(threshold)
        self._tolerance = max(float(tolerance), 0.0)
        self._scale = max(float(scale), 1e-12)
        self._power = max(float(power), 1e-12)

    def compute(self, raw_value: float) -> float:
        limit = self._threshold - self._tolerance
        x = float(raw_value)
        if x >= limit:
            return 0.0
        z = (limit - x) / self._scale
        return _soft_saturating_penalty(z, self._power)

    def __repr__(self) -> str:
        return (
            "SoftGreaterThan("
            f"t={self._threshold}, tol={self._tolerance}, "
            f"scale={self._scale}, p={self._power})"
        )
