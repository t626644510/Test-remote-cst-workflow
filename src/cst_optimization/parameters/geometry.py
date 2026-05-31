"""Geometry parameter definitions mapping to CST named parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .base import OptimizationParameter, ParamRange
from ..core.project import CSTProject


class GeometryParameter(OptimizationParameter):
    """A named CST geometry parameter (e.g. cavity radius, gap length).

    Mapped directly to a CST ``StoreParameter`` / ``StoreParameterVBA`` call.
    """

    def __init__(
        self,
        cst_name: str,
        range: ParamRange,
        display_name: str = "",
        unit: str = "mm",
    ) -> None:
        self.name = cst_name
        self.display_name = display_name or cst_name
        self.unit = unit
        self.range = range

    def get_value(self, project: CSTProject) -> float:
        """Read from CST is not directly supported; returns NaN.

        Use ``to_dict`` on the optimizer state to track current values.
        """
        return float("nan")

    def set_value(self, project: CSTProject, value: float) -> None:
        """Set the parameter in the CST project (single parameter)."""
        project.update_parameters({self.name: float(value)})
