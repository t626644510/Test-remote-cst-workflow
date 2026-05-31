"""Abstract base class and set container for optimization parameters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from ..core.project import CSTProject


@dataclass
class ParamRange:
    """Bounds and sampling preference for a continuous parameter.

    Attributes
    ----------
    low : float
        Lower bound.
    high : float
        Upper bound.
    log_scale : bool
        If ``True``, sampling should be performed in log space.
    """

    low: float
    high: float
    log_scale: bool = False

    def __post_init__(self) -> None:
        if self.low >= self.high:
            raise ValueError(f"ParamRange low ({self.low}) must be < high ({self.high})")

    @property
    def span(self) -> float:
        """Return ``high - low``."""
        return self.high - self.low


class OptimizationParameter(ABC):
    """Abstract base for a single optimisation parameter.

    Subclasses define how to read and write the parameter in a CST model.
    Each parameter carries metadata (name, display name, unit, range)
    for use by optimisers and reporting.

    Class Attributes
    ----------------
    name : str
        Internal identifier (also used as the CST parameter name).
    display_name : str
        Human-readable label.
    unit : str
        Unit string (e.g. ``"mm"``, ``"deg"``).
    range : ParamRange
        Allowed range for the parameter.
    """

    name: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    unit: ClassVar[str] = ""
    range: ClassVar[ParamRange] = ParamRange(0.0, 1.0)

    @abstractmethod
    def get_value(self, project: CSTProject) -> float:
        """Read the current value from the CST project."""
        ...

    @abstractmethod
    def set_value(self, project: CSTProject, value: float) -> None:
        """Set the parameter value in the CST project."""
        ...

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"range=[{self.range.low}, {self.range.high}])"
        )


class ParameterSet:
    """An ordered collection of ``OptimizationParameter`` instances.

    Provides normalisation, bounds extraction, and dict conversion used
    by the optimisation pipeline.

    Parameters
    ----------
    parameters : list[OptimizationParameter]
        The parameters that define the design space.
    """

    def __init__(self, parameters: list[OptimizationParameter]) -> None:
        if not parameters:
            raise ValueError("ParameterSet must contain at least one parameter")
        self._params = list(parameters)
        self._original_bounds: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_parameters(self) -> int:
        """Number of parameters."""
        return len(self._params)

    @property
    def bounds(self) -> np.ndarray:
        """``(N, 2)`` array of ``[low, high]`` bounds."""
        return np.array([(p.range.low, p.range.high) for p in self._params])

    @property
    def names(self) -> list[str]:
        """List of parameter names."""
        return [p.name for p in self._params]

    @property
    def parameters(self) -> list[OptimizationParameter]:
        """The underlying parameter list (copy)."""
        return list(self._params)

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_dict(self, values: np.ndarray) -> dict[str, float]:
        """Convert an array of values to a ``{name: value}`` dict for CST.

        Parameters
        ----------
        values : np.ndarray
            1-D array, one value per parameter in order.

        Returns
        -------
        dict[str, float]
        """
        if len(values) != self.n_parameters:
            raise ValueError(
                f"Expected {self.n_parameters} values, got {len(values)}"
            )
        return {p.name: float(v) for p, v in zip(self._params, values)}

    def from_dict(self, d: dict[str, float]) -> np.ndarray:
        """Convert a ``{name: value}`` dict to an ordered array."""
        name_to_idx = {p.name: i for i, p in enumerate(self._params)}
        out = np.empty(self.n_parameters)
        for name, val in d.items():
            out[name_to_idx[name]] = val
        return out

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def normalize(self, values: np.ndarray) -> np.ndarray:
        """Map values from physical space to [0, 1].

        For log-scale parameters, log-transform before normalising.
        """
        values = np.asarray(values, dtype=float)
        normed = np.empty_like(values)
        for i, p in enumerate(self._params):
            lo, hi = p.range.low, p.range.high
            v = values[i]
            if p.range.log_scale:
                v = np.log(v)
                lo = np.log(lo)
                hi = np.log(hi)
            normed[i] = (v - lo) / (hi - lo)
        return normed

    def denormalize(self, normalized: np.ndarray) -> np.ndarray:
        """Map values from [0, 1] back to physical space."""
        normalized = np.asarray(normalized, dtype=float)
        physical = np.empty_like(normalized)
        for i, p in enumerate(self._params):
            lo, hi = p.range.low, p.range.high
            t = normalized[i]
            if p.range.log_scale:
                lo = np.log(lo)
                hi = np.log(hi)
                physical[i] = np.exp(lo + t * (hi - lo))
            else:
                physical[i] = lo + t * (hi - lo)
        return physical

    def validate(self, values: np.ndarray) -> np.ndarray:
        """Clamp *values* to the parameter bounds."""
        values = np.asarray(values, dtype=float)
        return np.clip(values, self.bounds[:, 0], self.bounds[:, 1])

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self):
        return iter(self._params)

    def __len__(self) -> int:
        return self.n_parameters

    def __getitem__(self, idx: int) -> OptimizationParameter:
        return self._params[idx]

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @property
    def constraints(self) -> ConstraintSet | None:
        """The constraint set for this parameter space (or ``None``)."""
        return getattr(self, "_constraints", None)

    @constraints.setter
    def constraints(self, cs: ConstraintSet | None) -> None:
        self._constraints = cs

    def is_feasible(self, x_phys: np.ndarray) -> bool:
        """Return ``True`` if *x_phys* satisfies all constraints.

        Always returns ``True`` when no constraint set is attached.
        """
        cs = self.constraints
        if cs is None:
            return True
        return cs.all_satisfied(x_phys)

    # ------------------------------------------------------------------
    # Bound manipulation
    # ------------------------------------------------------------------

    @property
    def original_bounds(self) -> np.ndarray | None:
        """The bounds at construction time (or first time ``capture_original_bounds`` was called)."""
        return self._original_bounds

    def capture_original_bounds(self) -> np.ndarray:
        """Store the current bounds as the reference *original* bounds.

        Returns the stored ``(N, 2)`` array.
        """
        self._original_bounds = self.bounds.copy()
        return self._original_bounds

    def update_bounds(self, new_bounds: np.ndarray) -> None:
        """Replace all parameter bounds from an ``(N, 2)`` array."""
        new_bounds = np.asarray(new_bounds, dtype=float)
        if new_bounds.shape != (self.n_parameters, 2):
            raise ValueError(
                f"Expected bounds shape ({self.n_parameters}, 2), got {new_bounds.shape}"
            )
        for i, p in enumerate(self._params):
            p.range.low = float(new_bounds[i, 0])
            p.range.high = float(new_bounds[i, 1])

    def get_bound(self, index: int) -> tuple[float, float]:
        """Return ``(low, high)`` for the parameter at *index*."""
        p = self._params[index]
        return (p.range.low, p.range.high)

    def set_bound(self, index: int, low: float, high: float) -> None:
        """Set the bounds for a single parameter."""
        p = self._params[index]
        p.range.low = float(low)
        p.range.high = float(high)

    def shrink_toward(
        self,
        center: np.ndarray,
        factor: float,
        min_span_ratio: float = 0.1,
    ) -> np.ndarray:
        """Shrink every parameter's bounds toward *center* by *factor*.

        The new span for parameter *i* is ``factor * old_span``, clipped
        below by ``min_span_ratio * original_span`` (if original bounds were
        captured).

        Returns the new bounds as an ``(N, 2)`` array.
        """
        center = np.asarray(center, dtype=float)
        orig = self._original_bounds
        new_bounds = np.empty((self.n_parameters, 2))
        for i, p in enumerate(self._params):
            old_lo, old_hi = p.range.low, p.range.high
            c = center[i]
            new_lo = c + (old_lo - c) * factor
            new_hi = c + (old_hi - c) * factor
            # Enforce minimum span
            if orig is not None and min_span_ratio > 0:
                min_span = (orig[i, 1] - orig[i, 0]) * min_span_ratio
                if new_hi - new_lo < min_span:
                    mid = (new_lo + new_hi) / 2.0
                    new_lo = mid - min_span / 2.0
                    new_hi = mid + min_span / 2.0
            # Enforce monotonicity
            if new_lo >= new_hi:
                new_lo, new_hi = new_hi, new_lo + 1e-12
            p.range.low = float(new_lo)
            p.range.high = float(new_hi)
            new_bounds[i] = (p.range.low, p.range.high)
        return new_bounds

    def expand_bound(
        self,
        index: int,
        factor: float,
        max_span_ratio: float = 2.0,
    ) -> tuple[float, float]:
        """Expand a single parameter's bounds outward by *factor*.

        The span is multiplied by *factor*, centered on the current midpoint.
        Clipped above by ``max_span_ratio * original_span``.

        Returns the new ``(low, high)`` tuple.
        """
        p = self._params[index]
        mid = (p.range.low + p.range.high) / 2.0
        half_span = (p.range.high - p.range.low) / 2.0 * factor
        new_lo = mid - half_span
        new_hi = mid + half_span
        orig = self._original_bounds
        if orig is not None and max_span_ratio > 0:
            max_span = (orig[index, 1] - orig[index, 0]) * max_span_ratio
            if new_hi - new_lo > max_span:
                new_lo = mid - max_span / 2.0
                new_hi = mid + max_span / 2.0
        p.range.low = float(new_lo)
        p.range.high = float(new_hi)
        return (p.range.low, p.range.high)

    def __repr__(self) -> str:
        return f"ParameterSet({self.n_parameters} params: {self.names})"


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


class ParameterConstraint:
    """A geometric constraint on a physical-space parameter vector.

    Parameters
    ----------
    func : callable
        ``f(x_phys: np.ndarray) -> bool``.  Returns ``True`` when satisfied.
    description : str
        Human-readable description (e.g. ``"Lin > DownHeight1"``).
    """

    def __init__(
        self, func: callable, description: str = "",
    ) -> None:
        self._func = func
        self._desc = str(description)

    def is_satisfied(self, x_phys: np.ndarray) -> bool:
        """Check if *x_phys* satisfies this constraint."""
        return bool(self._func(np.asarray(x_phys, dtype=float)))

    @property
    def description(self) -> str:
        """Human-readable description."""
        return self._desc

    def __repr__(self) -> str:
        return f"ParameterConstraint({self._desc})"


class ConstraintSet:
    """An ordered collection of ``ParameterConstraint`` instances.

    Parameters
    ----------
    constraints : list[ParameterConstraint]
    """

    def __init__(self, constraints: list[ParameterConstraint]) -> None:
        self._constraints = list(constraints)

    def all_satisfied(self, x_phys: np.ndarray) -> bool:
        """Return ``True`` if **all** constraints are satisfied."""
        for c in self._constraints:
            if not c.is_satisfied(x_phys):
                return False
        return True

    def which_violated(self, x_phys: np.ndarray) -> list[str]:
        """Return descriptions of any violated constraints."""
        violated: list[str] = []
        for c in self._constraints:
            if not c.is_satisfied(x_phys):
                violated.append(c.description)
        return violated

    @property
    def n_constraints(self) -> int:
        """Number of constraints."""
        return len(self._constraints)

    def __iter__(self):
        return iter(self._constraints)

    def __len__(self) -> int:
        return self.n_constraints

    def __repr__(self) -> str:
        return f"ConstraintSet({self.n_constraints} constraints)"


# ---------------------------------------------------------------------------
# Constraint builders (from YAML config entries)
# ---------------------------------------------------------------------------


def _build_trig_constraint(
    entry: dict,
    name_to_idx: dict[str, int],
    desc: str,
    sign: int,  # -1 for lt, +1 for gt
) -> ParameterConstraint:
    """Build a constraint of the form ``f(angle) * radius {<|>} threshold``.

    *formula* selects the angular function:
    - ``"sin"`` (default):  sin(angle_deg) × radius
    - ``"1-cos"``:          (1 − cos(angle_deg)) × radius
    """
    angle_name = entry["angle"]
    radius_name = entry["radius"]
    threshold = float(entry["threshold"])
    formula = entry.get("formula", "sin")

    if angle_name not in name_to_idx:
        raise KeyError(
            f"Constraint references unknown param '{angle_name}'"
        )
    if radius_name not in name_to_idx:
        raise KeyError(
            f"Constraint references unknown param '{radius_name}'"
        )

    idx_angle = name_to_idx[angle_name]
    idx_radius = name_to_idx[radius_name]
    op = "<" if sign < 0 else ">"
    negate = bool(entry.get("negate_radius", False))

    if formula == "1-cos":
        fn_label = "1−cos"
        def _fn(deg: float) -> float:
            return float(1.0 - np.cos(np.deg2rad(deg)))
    else:
        fn_label = "sin"
        def _fn(deg: float) -> float:
            return float(np.sin(np.deg2rad(deg)))

    if not desc or desc == entry.get("type", ""):
        sign_str = "-" if negate else ""
        desc = f"{fn_label}({angle_name}) * {sign_str}{radius_name} {op} {threshold}"

    def _check(
        x_phys: np.ndarray,
        ia: int = idx_angle,
        ir: int = idx_radius,
        t: float = threshold,
    ) -> bool:
        r = float(x_phys[ir])
        if negate:
            r = -r
        val = _fn(float(x_phys[ia])) * r
        return bool(val < t) if sign < 0 else bool(val > t)

    return ParameterConstraint(_check, desc)


def build_constraint(
    entry: dict,
    param_names: list[str],
) -> ParameterConstraint:
    """Build a ``ParameterConstraint`` from a YAML constraint entry.

    Supported types
    ---------------
    ``gt``
        *param_a* > *param_b*.
        Keys: ``a``, ``b`` (parameter names).

    ``sin_times_r_lt``
        f(*angle_deg*) × *radius* < *threshold*.
        Keys: ``angle``, ``radius`` (parameter names), ``threshold`` (float).
        Optional ``formula``: ``"sin"`` (default) or ``"1-cos"``.

    Parameters
    ----------
    entry : dict
        Constraint definition from YAML.
    param_names : list[str]
        Ordered parameter names (for index lookup).

    Returns
    -------
    ParameterConstraint

    Raises
    ------
    ValueError
        If the constraint type is unknown or required keys are missing.
    """
    name_to_idx = {n: i for i, n in enumerate(param_names)}
    ctype = entry.get("type", "")
    desc = entry.get("description", ctype)

    if ctype == "gt":
        a_val = entry["a"]
        b_val = entry["b"]
        a_is_literal = isinstance(a_val, (int, float))
        b_is_literal = isinstance(b_val, (int, float))
        if a_is_literal and b_is_literal:
            raise ValueError("gt constraint: at least one of a, b must be a param name")

        a_lit = float(a_val) if a_is_literal else None
        b_lit = float(b_val) if b_is_literal else None
        idx_a = name_to_idx[str(a_val)] if not a_is_literal else -1
        idx_b = name_to_idx[str(b_val)] if not b_is_literal else -1

        if not a_is_literal and idx_a < 0:
            raise KeyError(f"Constraint 'gt' references unknown param '{a_val}'")
        if not b_is_literal and idx_b < 0:
            raise KeyError(f"Constraint 'gt' references unknown param '{b_val}'")

        if not desc or desc == ctype:
            a_label = str(a_val) if a_is_literal else str(a_val)
            b_label = str(b_val) if b_is_literal else str(b_val)
            desc = f"{a_label} > {b_label}"

        def _gt(x_phys: np.ndarray, ia=idx_a, ib=idx_b,
                al=a_lit, bl=b_lit) -> bool:
            left = x_phys[ia] if ia >= 0 else al
            right = x_phys[ib] if ib >= 0 else bl
            return bool(left > right)

        return ParameterConstraint(_gt, desc)

    elif ctype == "sin_times_r_lt":
        _check = _build_trig_constraint(entry, name_to_idx, desc, sign=-1)
        return _check

    elif ctype == "sin_times_r_gt":
        _check = _build_trig_constraint(entry, name_to_idx, desc, sign=+1)
        return _check

    else:
        raise ValueError(
            f"Unknown constraint type '{ctype}'.  "
            f"Supported: 'gt', 'sin_times_r_lt', 'sin_times_r_gt'"
        )
