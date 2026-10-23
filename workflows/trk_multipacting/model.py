"""TRK source/RF task identity; phase degrees, voltage label kV."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any

@dataclass(frozen=True)
class Task:
    """One source and external RF excitation (phase in degrees)."""

    source: str
    factor1: float
    phase: int

    @property
    def key(self) -> str:
        return f"s{int(self.source[8:]):02d}_f{round(self.factor1 * 100):03d}_p{self.phase:03d}"

    def record(self) -> dict[str, Any]:
        """The voltage label assumes the user's factor1=1 -> 500 kV calibration."""
        return dict(asdict(self), key=self.key, voltage_kV=500 * self.factor1)
