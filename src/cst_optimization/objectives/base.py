"""Abstract base class for optimisation objectives.

``ObjectiveFunction`` is split into two concerns:

1. **``raw_value()``** — read CST results and compute the physical quantity
   (e.g. resonant frequency in GHz, Q0, peak field in V/m).
2. **``OptimizationMode``** — maps the raw value to a scalar penalty
   (e.g. "maximize", "tolerance", "greater_than").

This decoupling lets you change the optimisation strategy for a quantity
without modifying the objective class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, ClassVar, Optional

from ..core.results import ResultReader
from .modes import OptimizationMode, Minimize


class ObjectiveFunction(ABC):
    """Abstract base for an optimisation objective.

    Subclasses implement ``raw_value()`` to extract a physical quantity
    from CST results.  The ``mode`` (injected at construction) transforms
    that raw value into a penalty scalar.

    Parameters
    ----------
    reader_factory : callable
        Zero-argument callable returning a fresh ``ResultReader``.
    mode : OptimizationMode
        Penalty function.  Defaults to ``Minimize()``.
    """

    name: ClassVar[str] = ""
    unit: ClassVar[str] = ""

    def __init__(
        self,
        reader_factory: Callable[[], ResultReader],
        mode: OptimizationMode | None = None,
        **kwargs,
    ) -> None:
        self._reader_factory = reader_factory
        self._mode: OptimizationMode = mode if mode is not None else Minimize()
        # Subclasses may consume extra kwargs; the base silently ignores them.

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abstractmethod
    def raw_value(self) -> float:
        """Compute the raw physical quantity from CST results.

        Returns the value in its native unit (e.g. GHz for frequency,
        dimensionless for Q, V/m for fields).
        """
        ...

    def evaluate(self) -> float:
        """Return the penalty scalar (delegates to ``self.mode.compute``).

        The return value is **always** in a minimisation sense, regardless
        of whether the user wants to maximise Q0 or minimise peak field.
        """
        return self._mode.compute(self.raw_value())

    def normalized(self, value: float | None = None) -> float:
        """Convenience alias for ``evaluate()``.

        Since ``OptimizationMode.compute`` already returns a penalty
        where lower = better, no sign-flip is needed.
        """
        return value if value is not None else self.evaluate()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> OptimizationMode:
        """The penalty mode applied to ``raw_value()``."""
        return self._mode

    @property
    def reader_factory(self) -> Callable[[], ResultReader]:
        """Return the reader factory callable."""
        return self._reader_factory

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(mode={self._mode})"


class CompositeObjective:
    """Weighted linear combination of multiple ``ObjectiveFunction`` instances.

    All component objectives are evaluated normally (their mode already
    returns a penalty), so no additional normalisation is needed.

    Parameters
    ----------
    objectives : list[ObjectiveFunction]
        Component objectives.
    weights : list[float] or None
        Relative weights.  If ``None``, equal weights are used.
    """

    def __init__(
        self,
        objectives: list[ObjectiveFunction],
        weights: list[float] | None = None,
    ) -> None:
        self._objectives = list(objectives)
        n = len(objectives)
        if weights is None:
            self._weights = [1.0 / n] * n
        else:
            total = sum(weights)
            self._weights = [w / total for w in weights]

    def evaluate(self) -> float:
        """Return the weighted sum of component penalty values."""
        total = 0.0
        for obj, w in zip(self._objectives, self._weights):
            total += w * obj.evaluate()
        return total

    @property
    def n_objectives(self) -> int:
        """Number of component objectives."""
        return len(self._objectives)

    @property
    def objective_names(self) -> list[str]:
        """Names of component objectives."""
        return [o.name for o in self._objectives]
