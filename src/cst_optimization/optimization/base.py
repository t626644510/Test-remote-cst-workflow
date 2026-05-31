"""Abstract base class for optimisation algorithms and result container."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ..parameters.base import ParameterSet
from ..objectives.base import ObjectiveFunction


@dataclass
class OptimizationResult:
    """Container for all data produced by an optimisation run.

    Attributes
    ----------
    x_opt : np.ndarray
        Optimal parameter vector(s) — shape ``(n_parameters,)`` for
        single-objective or ``(n_pareto, n_parameters)`` for multi-objective.
    f_opt : np.ndarray
        Objective value(s) at optimum.
    pareto_front : np.ndarray or None
        Pareto front points, shape ``(n_front, n_objectives)``.
    pareto_params : np.ndarray or None
        Parameter vectors for each Pareto-front point.
    history_x : list[np.ndarray]
        All evaluated parameter vectors in order.
    history_f : list[np.ndarray]
        All evaluated objective values in order.
    n_evaluations : int
        Total number of true (CST) evaluations.
    metadata : dict
        Additional algorithm-specific data (convergence, timings, etc.).
    """

    x_opt: np.ndarray
    f_opt: np.ndarray
    pareto_front: np.ndarray | None = None
    pareto_params: np.ndarray | None = None
    history_x: list[np.ndarray] = field(default_factory=list)
    history_f: list[np.ndarray] = field(default_factory=list)
    n_evaluations: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseOptimizer(ABC):
    """Abstract base for all optimisation algorithms.

    Parameters
    ----------
    parameter_set : ParameterSet
    objectives : list[ObjectiveFunction]
    seed : int or None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        parameter_set: ParameterSet,
        objectives: list[ObjectiveFunction],
        seed: int | None = 42,
        logger: Any | None = None,
    ) -> None:
        if not objectives:
            raise ValueError("At least one objective is required")
        self._parameter_set = parameter_set
        self._objectives = list(objectives)
        self._seed = seed
        self._rng = np.random.RandomState(seed)
        self._logger = logger

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def parameter_set(self) -> ParameterSet:
        """The design-space definition."""
        return self._parameter_set

    @property
    def objectives(self) -> list[ObjectiveFunction]:
        """The list of active objective functions."""
        return self._objectives

    @property
    def n_objectives(self) -> int:
        """Number of objectives."""
        return len(self._objectives)

    @property
    def n_parameters(self) -> int:
        """Dimensionality of the design space."""
        return self._parameter_set.n_parameters

    @property
    def rng(self) -> np.random.RandomState:
        """Seeded random-number generator."""
        return self._rng

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Logger helpers
    # ------------------------------------------------------------------

    def _log_eval(
        self, iteration: int, x: np.ndarray, f: np.ndarray,
        physics: dict | None = None, solver_ok: bool = True,
        error: str = "", elapsed_s: float = 0.0,
    ) -> None:
        """Record one evaluation to the logger (if attached)."""
        if self._logger is None:
            return
        # Build objective name → value mapping
        obj_vals = {}
        for idx, obj in enumerate(self._objectives):
            if idx < len(f):
                obj_vals[obj.name] = float(f[idx])
        self._logger.log_evaluation(
            iteration=iteration,
            x=x,
            param_names=self._parameter_set.names,
            physics=physics or {},
            objective_values=obj_vals,
            solver_ok=solver_ok,
            error=error,
            elapsed_s=elapsed_s,
        )

    def _log_decision(
        self, iteration: int, x_proposed: np.ndarray,
        acquisition_value: float, y_best: float,
        gp_params: dict | None = None,
    ) -> None:
        """Record one optimizer decision to the logger (if attached)."""
        if self._logger is None:
            return
        self._logger.log_decision(
            iteration=iteration,
            x_proposed=x_proposed,
            param_names=self._parameter_set.names,
            acquisition_value=acquisition_value,
            y_best_so_far=y_best,
            gp_params=gp_params,
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def optimize(self) -> OptimizationResult:
        """Execute the optimisation and return results."""
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _evaluate_objectives(self) -> np.ndarray:
        """Evaluate all objectives and return as a 1-D array.

        Returns
        -------
        np.ndarray
            Objective values, shape ``(n_objectives,)``.
        """
        vals = [obj.evaluate() for obj in self._objectives]
        return np.array(vals, dtype=float)

    def _evaluate_normalized(self) -> np.ndarray:
        """Evaluate all objectives, normalised to minimisation sense.

        Returns
        -------
        np.ndarray
        """
        return np.array(
            [obj.normalized() for obj in self._objectives],
            dtype=float,
        )
