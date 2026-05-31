"""Global registries for objectives and optimisation modes.

Add a new objective::

    from cst_optimization.objectives.registry import register_objective

    @register_objective
    class MyNewObjective(ObjectiveFunction):
        name = "my_metric"
        unit = "W"

        def raw_value(self) -> float:
            ...

Add a new mode::

    from cst_optimization.objectives.registry import register_mode

    @register_mode("my_mode")
    class MyMode(OptimizationMode):
        name = "my_mode"
        def compute(self, raw_value: float) -> float: ...
"""

from __future__ import annotations

from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ObjectiveFunction
    from .modes import OptimizationMode

# ── Objective registry ─────────────────────────────────────────────────

_objective_registry: dict[str, Type[ObjectiveFunction]] = {}


def register_objective(
    cls: Type[ObjectiveFunction],
) -> Type[ObjectiveFunction]:
    """Decorator that registers an ``ObjectiveFunction`` subclass."""
    if not cls.name:
        raise ValueError(f"{cls.__name__}.name must be non-empty")
    if cls.name in _objective_registry:
        raise KeyError(f"Objective '{cls.name}' is already registered")
    _objective_registry[cls.name] = cls
    return cls


def get_objective(name: str) -> Type[ObjectiveFunction]:
    """Look up a registered objective class by name."""
    if name not in _objective_registry:
        available = list(_objective_registry.keys())
        raise KeyError(
            f"Unknown objective '{name}'. Registered: {available}"
        )
    return _objective_registry[name]


def list_objectives() -> list[str]:
    """Return all registered objective names."""
    return list(_objective_registry.keys())


def clear_objective_registry() -> None:
    """Clear the objective registry (useful in tests)."""
    _objective_registry.clear()


# ── Mode registry ──────────────────────────────────────────────────────

_mode_registry: dict[str, Type[OptimizationMode]] = {}


def register_mode(name: str):
    """Decorator factory that registers an ``OptimizationMode`` subclass.

    Usage::

        @register_mode("tolerance")
        class GaussianTolerance(OptimizationMode):
            ...

    Parameters
    ----------
    name : str
        Unique name used in YAML config (e.g. ``"tolerance"``).
    """

    def _decorator(cls: Type[OptimizationMode]) -> Type[OptimizationMode]:
        if not name:
            raise ValueError("Mode name must be non-empty")
        if name in _mode_registry:
            raise KeyError(f"Mode '{name}' is already registered")
        _mode_registry[name] = cls
        return cls

    return _decorator


def get_mode(name: str) -> Type[OptimizationMode]:
    """Look up a registered mode class by name.

    Raises ``KeyError`` if not found.
    """
    if name not in _mode_registry:
        available = list(_mode_registry.keys())
        raise KeyError(
            f"Unknown mode '{name}'. Registered: {available}"
        )
    return _mode_registry[name]


def list_modes() -> list[str]:
    """Return all registered mode names."""
    return list(_mode_registry.keys())


def clear_mode_registry() -> None:
    """Clear the mode registry (useful in tests)."""
    _mode_registry.clear()
