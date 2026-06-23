"""Typed data models used by Workflow 4."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TargetRecord:
    """One measured suspicious-HOM input row.

    Frequencies are stored in Hz, bandwidth in Hz, and suggested span in MHz.
    The measured ``q`` is never treated as a simulated eigenmode Q.
    """

    source_row_id: str
    source_row_number: int
    condition: str
    freq_hz: float
    freq_ghz: float
    q_measurement: float
    residual_prominence_db: float
    raw_peak_db: float
    baseline_db: float
    bandwidth_hz: float
    rank_source: str
    propagation_background: bool
    suggested_span_mhz: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TargetCluster:
    """Cross-condition collection of measurements for one candidate mode."""

    target_cluster_id: str
    records: tuple[TargetRecord, ...]
    target_freq_hz: float
    freq_min_hz: float
    freq_max_hz: float
    suggested_span_max_mhz: float
    required_min_hz: float
    required_max_hz: float
    propagation_background: bool

    @property
    def source_row_ids(self) -> tuple[str, ...]:
        return tuple(record.source_row_id for record in self.records)

    @property
    def conditions(self) -> tuple[str, ...]:
        return tuple(record.condition for record in self.records)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data


@dataclass(frozen=True)
class SolverWindow:
    """One CST solve centered on ``f_hom_mhz`` with a fixed half width."""

    solver_window_id: str
    cluster_ids: tuple[str, ...]
    f_hom_mhz: float
    search_min_hz: float
    search_max_hz: float
    coverage_min_hz: float
    coverage_max_hz: float
    kind: str = "initial"
    parent_window_id: str = ""
    probe_offset_mhz: float = 0.0

    @property
    def is_merged(self) -> bool:
        return len(self.cluster_ids) > 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NativeModeResult:
    """CST-native scalar results for one mode."""

    mode_number: int
    frequency_hz: float
    r_over_q_ohm: float | None = None
    voltage_v: float | None = None
    total_energy_j: float | None = None
    total_loss_w: float | None = None
    residual: float | None = None
    q_loaded: float | None = None
    q0: float | None = None
    regional_q: dict[str, float] = field(default_factory=dict)
    source_treepaths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NativeModeResult":
        return cls(**data)


@dataclass
class ComplexLineField:
    """Complex longitudinal electric field sampled along one beam trajectory."""

    z_m: Any
    ez_v_per_m: Any
    source_path: str = ""


@dataclass
class EigenmodeCandidate:
    """One post-processed simulated mode before or after deduplication."""

    mode_id: str
    solver_window_id: str
    attempt_id: str
    mode_number: int
    frequency_hz: float
    r_over_q_ohm: float | None = None
    voltage_v: float | None = None
    total_energy_j: float | None = None
    total_loss_w: float | None = None
    residual: float | None = None
    q_loaded: float | None = None
    q0: float | None = None
    regional_q: dict[str, float] = field(default_factory=dict)
    field_paths: dict[str, str] = field(default_factory=dict)
    voltages: dict[str, complex] = field(default_factory=dict)
    dipole_a_x_ohm_per_m2: float | None = None
    dipole_a_y_ohm_per_m2: float | None = None
    dipole_a_total_ohm_per_m2: float | None = None
    transverse_r_over_q_ohm_per_m: float | None = None
    circuit_transverse_r_over_q_ohm: float | None = None
    transverse_kick_factor_v_per_c_per_m: float | None = None
    gradient_x_v_per_m: complex | None = None
    gradient_y_v_per_m: complex | None = None
    polarization_deg: float | None = None
    derived_valid: bool = False
    data_availability_reason: str = ""
    voltage_relative_error: float | None = None
    r_over_q_relative_error: float | None = None
    duplicate_member_ids: list[str] = field(default_factory=list)
    dedup_confidence: str = "not_deduplicated"
    warning_codes: list[str] = field(default_factory=list)
    boundary_sensitive: bool = False
    mode_count_censored: bool = False
    template_revision_id: str = ""
    template_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["voltages"] = {
            key: {"real": value.real, "imag": value.imag}
            for key, value in self.voltages.items()
        }
        for name in ("gradient_x_v_per_m", "gradient_y_v_per_m"):
            value = getattr(self, name)
            data[name] = (
                {"real": value.real, "imag": value.imag}
                if value is not None
                else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EigenmodeCandidate":
        converted = dict(data)
        converted["voltages"] = {
            key: complex(value["real"], value["imag"])
            for key, value in converted.get("voltages", {}).items()
        }
        for name in ("gradient_x_v_per_m", "gradient_y_v_per_m"):
            value = converted.get(name)
            if isinstance(value, dict):
                converted[name] = complex(value["real"], value["imag"])
        return cls(**converted)
