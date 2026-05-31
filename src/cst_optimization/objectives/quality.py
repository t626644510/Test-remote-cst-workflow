"""Q-value, coupling, and power-related optimisation objectives.

Each class only defines ``raw_value()``.  The optimisation strategy
is injected via a ``mode`` at construction time.

Example YAML usage::

    objectives:
      - name: q0
        mode: maximize
      - name: coupling_beta
        mode: tolerance
        mode_params: {target: 3.0, sigma: 1.0}
      - name: p_input
        mode: less_than
        mode_params: {threshold: 5.0, sigma: 1.0}
"""

from __future__ import annotations

from typing import ClassVar

from .base import ObjectiveFunction
from .registry import register_objective
from ..core.results import ResultBundle
from ..physics.cavity import IntrinsicQ, LoadedQ, CouplingBeta, InputPower


@register_objective
class Q0Objective(ObjectiveFunction):
    """Intrinsic (unloaded) quality factor Q0.

    Raw value: dimensionless.
    Typical mode: ``maximize``.
    """

    name: ClassVar[str] = "q0"
    unit: ClassVar[str] = "dimensionless"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        s11 = reader.get_s_parameter()
        bundle = ResultBundle(s_parameters={"S1,1": s11})
        return IntrinsicQ().compute(bundle)


@register_objective
class QLObjective(ObjectiveFunction):
    """Loaded quality factor QL.

    Raw value: dimensionless.
    Typical mode: ``maximize``.
    """

    name: ClassVar[str] = "q_loaded"
    unit: ClassVar[str] = "dimensionless"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        s11 = reader.get_s_parameter()
        bundle = ResultBundle(s_parameters={"S1,1": s11})
        return LoadedQ().compute(bundle)


@register_objective
class CouplingBetaObjective(ObjectiveFunction):
    """Input coupling parameter Beta.

    Raw value: dimensionless.
    Typical modes:

    - ``tolerance`` — target a specific Beta (e.g. 3.0).
    - ``greater_than`` — Beta must exceed a minimum (e.g. > 2.0).
    """

    name: ClassVar[str] = "coupling_beta"
    unit: ClassVar[str] = "dimensionless"

    def raw_value(self) -> float:
        reader = self._reader_factory()
        s11 = reader.get_s_parameter()
        bundle = ResultBundle(s_parameters={"S1,1": s11})
        return CouplingBeta().compute(bundle)


@register_objective
class InputPowerObjective(ObjectiveFunction):
    """Required input power to reach the target accelerating gradient.

    Derivation
    ----------
    E ∝ √P  ⇒  P_in_target = P_in_sim · (E_target / E_sim)²

    Raw value: **W** (at the specified target gradient).
    Typical mode: ``less_than`` or ``minimize``.

    Parameters
    ----------
    reader_factory : callable
    mode : OptimizationMode
    target_e_acc_vm : float
        Target accelerating gradient in V/m (default 200 MV/m).
    """

    name: ClassVar[str] = "p_input"
    unit: ClassVar[str] = "W"

    def __init__(self, reader_factory, mode=None, target_e_acc_vm: float = 200e6) -> None:
        super().__init__(reader_factory, mode)
        self._input_power = InputPower(target_e_acc_vm=target_e_acc_vm)

    def raw_value(self) -> float:
        reader = self._reader_factory()
        s11 = reader.get_s_parameter()
        try:
            raw_e = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
        except Exception:
            raw_e = None

        scalars = {}
        if raw_e is not None:
            scalars["MaxE_Z0"] = raw_e
        bundle = ResultBundle(s_parameters={"S1,1": s11}, scalars=scalars)
        return self._input_power.compute(bundle)
