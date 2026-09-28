"""Portable, strictly validated configuration for the two-HOM campaign.

Loading configuration never imports CST or touches project contents. Lengths
are millimetres, angles degrees, frequencies MHz, and impedance ohm/metre.
"""
from __future__ import annotations

import math
import os
import string
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


PARAMETER_DEFAULTS = (
    ("selfangle2", 0.0, 180.0, "deg"),
    ("UpperHeight2", 0.0, 50.0, "mm"),
    ("DownHeight2", 0.0, 50.0, "mm"),
    ("Lin2", 1.0, 50.0, "mm"),
    ("inner_angle3", 5.0, 175.0, "deg"),
    ("inner_r2", 5.44, 25.0, "mm"),
)
PARAMETER_NAMES = tuple(item[0] for item in PARAMETER_DEFAULTS)


class ConfigurationError(ValueError):
    """Configuration is invalid or incomplete for the requested operation."""


@dataclass(frozen=True)
class PathsConfig:
    """Paths resolved relative to the configuration file, never the station."""

    template_path: Path
    output_dir: Path
    cst_library_path: str = ""


@dataclass(frozen=True)
class ParameterConfig:
    """A canonical optimizer coordinate and its configurable CST name."""

    name: str
    lower: float
    upper: float
    unit: str
    cst_name: str = ""


@dataclass(frozen=True)
class GeometryConfig:
    """Circular conductor and flange dimensions, all in millimetres."""

    conductor_radius_mm: float = 5.43
    flange_radius_mm: float = 25.0
    clearance_mm: float = 0.01
    fillet_radius_mm: float = 5.43


@dataclass(frozen=True)
class SolverConfig:
    """Eigenmode settings; inherited template mesh is preserved."""

    mesh: str = "inherit"
    target_frequency_mhz: float = 1030.0
    upper_frequency_mhz: float = 1070.0
    coverage_policy: str = "upper_sentinel"
    mode_count: int = 6
    max_mode_count: int = 24
    coverage_retries: int = 2
    timeout_s: float = 10800.0
    settle_s: float = 2.0
    postprocess_timeout_s: float = 180.0


@dataclass(frozen=True)
class PhysicsConfig:
    """Physical acceptance and field-integration conventions.

    Impedance is loaded transverse shunt impedance in ohm/metre. The
    integration range must be supplied explicitly for the chosen template.
    """

    z_range_mm: tuple[float, float]
    frequency_min_mhz: float = 1030.0
    frequency_max_mhz: float = 1060.0
    threshold_ohm_per_m: float = 100000.0
    z_samples: int = 1883
    offsets_mm: tuple[float, ...] = (2.0, 4.0, 6.0)
    beta: float = 1.0
    field_convention: str = "peak"
    gradient_tolerance: float = 0.02
    integration_tolerance: float = 0.01
    min_q: float = 10.0
    conductivity_layers: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchConfig:
    """Finite search budgets; the baseline consumes an initial point."""

    max_solves: int = 40
    initial_points: int = 12
    seed: int = 42
    candidate_pool: int = 512
    local_fraction: float = 0.8
    initial_radius: float = 0.25
    min_radius: float = 0.05
    max_radius: float = 0.5
    max_candidate_attempts: int = 120
    candidate_draws: int = 100000


@dataclass(frozen=True)
class ResultsConfig:
    """CST tree templates; ``{mode}`` is the one-based eigenmode number."""

    frequency: str = r"1D Results\Mode Frequencies\Mode {mode}"
    q_loaded: str = r"1D Results\Q Factors\Total-Q\Mode {mode}"
    efield: str = r"2D/3D Results\Modes\Mode {mode}\e"
    frequency_unit: str = "MHz"


@dataclass(frozen=True)
class WorkflowConfig:
    """Validated workflow settings with explicit machine-specific paths."""

    paths: PathsConfig
    parameters: tuple[ParameterConfig, ...]
    physics: PhysicsConfig
    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    results: ResultsConfig = field(default_factory=ResultsConfig)

    def validate_live(self) -> None:
        """Check live prerequisites without importing CST or starting a solver."""
        if not self.paths.template_path.is_file():
            raise ConfigurationError(f"Template does not exist: {self.paths.template_path}")
        if self.paths.template_path.suffix.lower() != ".cst":
            raise ConfigurationError("paths.template_path must name a .cst project")
        if not self.paths.template_path.with_suffix("").is_dir():
            raise ConfigurationError("Template requires its same-name companion directory")
        if not self.paths.cst_library_path or not Path(self.paths.cst_library_path).is_dir():
            raise ConfigurationError("Set paths.cst_library_path or CST_PYTHON_LIB to the CST Python library directory")

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible settings for provenance and offline inspection."""
        def convert(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [convert(item) for item in value]
            return value
        return convert(asdict(self))


def _mapping(value: Any, label: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ConfigurationError(f"Unknown {label} keys: {', '.join(sorted(map(str, unknown)))}")
    return dict(value)


def _number(value: Any, label: str, *, positive: bool = False, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{label} must be a number")
    if not math.isfinite(float(value)) or (positive and value <= 0):
        raise ConfigurationError(f"{label} must be finite{' and positive' if positive else ''}")
    if integer:
        if not isinstance(value, int):
            raise ConfigurationError(f"{label} must be an integer")
        return value
    return float(value)


def _path(value: Any, base: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be a nonempty path")
    path = Path(os.path.expandvars(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _section(root: dict[str, Any], name: str, cls: Any) -> dict[str, Any]:
    return _mapping(root.get(name, {}), name, set(cls.__dataclass_fields__))


def load_config(path: str | Path, *, live: bool = False) -> WorkflowConfig:
    """Load a ``workflow_5`` YAML document, rejecting unknown keys and NaNs."""
    source = Path(path).resolve()
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML: {exc}") from exc
    document = _mapping(document, "document", {"workflow_5"})
    if "workflow_5" not in document:
        raise ConfigurationError("Missing workflow_5 root")
    root = _mapping(document["workflow_5"], "workflow_5", set(WorkflowConfig.__dataclass_fields__))
    paths = _section(root, "paths", PathsConfig)
    if "template_path" not in paths:
        raise ConfigurationError("paths.template_path is required")
    template = _path(paths["template_path"], source.parent, "paths.template_path")
    output = _path(paths.get("output_dir", "runs/workflow_5"), source.parent, "paths.output_dir")
    configured_library = paths.get("cst_library_path", "")
    if configured_library is not None and not isinstance(configured_library, str):
        raise ConfigurationError("paths.cst_library_path must be a string")
    library = configured_library or os.environ.get("CST_PYTHON_LIB", "")
    library_path = str(_path(library, source.parent, "paths.cst_library_path")) if library else ""
    companion = template.with_suffix("")
    if output == template or output in template.parents or output == companion or companion in output.parents:
        raise ConfigurationError("paths.output_dir must not contain the source template")

    raw_parameters = root.get("parameters")
    if raw_parameters is None:
        raw_parameters = [dict(name=name, lower=low, upper=high, unit=unit) for name, low, high, unit in PARAMETER_DEFAULTS]
    if not isinstance(raw_parameters, list) or len(raw_parameters) != 6:
        raise ConfigurationError("parameters must contain exactly the six canonical coordinates")
    parameters: dict[str, ParameterConfig] = {}
    units = {item[0]: item[3] for item in PARAMETER_DEFAULTS}
    for raw in raw_parameters:
        entry = _mapping(raw, "parameter", set(ParameterConfig.__dataclass_fields__))
        name = entry.get("name")
        if not isinstance(name, str) or name not in units or name in parameters:
            raise ConfigurationError(f"Unknown or duplicate canonical parameter: {name}")
        lower = _number(entry.get("lower"), f"{name}.lower")
        upper = _number(entry.get("upper"), f"{name}.upper")
        if lower >= upper:
            raise ConfigurationError(f"{name}.lower must be smaller than upper")
        unit = entry.get("unit", units[name])
        if unit != units[name]:
            raise ConfigurationError(f"{name}.unit must be {units[name]}")
        cst_name = entry.get("cst_name", name)
        if not isinstance(cst_name, str) or not cst_name.strip() or any(char in cst_name for char in '\"\r\n'):
            raise ConfigurationError(f"{name}.cst_name must be a nonempty CST parameter name")
        parameters[name] = ParameterConfig(name, lower, upper, unit, cst_name)
    if len({p.cst_name for p in parameters.values()}) != 6:
        raise ConfigurationError("CST parameter names must be unique")

    geometry_values = _section(root, "geometry", GeometryConfig)
    geometry = GeometryConfig(**{key: _number(value, f"geometry.{key}", positive=True) for key, value in geometry_values.items()})
    if geometry.conductor_radius_mm + geometry.clearance_mm >= geometry.flange_radius_mm:
        raise ConfigurationError("Conductor radius plus clearance must fit inside flange radius")

    solver_values = _section(root, "solver", SolverConfig)
    for key, value in list(solver_values.items()):
        if key not in {"mesh", "coverage_policy"}:
            solver_values[key] = _number(value, f"solver.{key}", positive=key not in {"coverage_retries", "settle_s"}, integer=key in {"mode_count", "max_mode_count", "coverage_retries"})
    solver = SolverConfig(**solver_values)
    if solver.mesh != "inherit":
        raise ConfigurationError("solver.mesh must be inherit")
    if solver.coverage_policy not in ("upper_sentinel", "fixed_window"):
        raise ConfigurationError("solver.coverage_policy must be upper_sentinel or fixed_window")
    if solver.coverage_policy == "fixed_window" and (solver.coverage_retries != 0 or solver.max_mode_count != solver.mode_count):
        raise ConfigurationError("fixed_window requires coverage_retries=0 and max_mode_count=mode_count")
    if solver.mode_count > solver.max_mode_count or min(solver.coverage_retries, solver.settle_s) < 0:
        raise ConfigurationError("Invalid solver mode limits or negative retry/settle/guard setting")

    physics_values = _section(root, "physics", PhysicsConfig)
    z_range = physics_values.get("z_range_mm")
    if not isinstance(z_range, (list, tuple)) or len(z_range) != 2:
        raise ConfigurationError("physics.z_range_mm must explicitly specify [start_mm, end_mm]")
    physics_values["z_range_mm"] = tuple(_number(v, "physics.z_range_mm") for v in z_range)
    if physics_values["z_range_mm"][0] >= physics_values["z_range_mm"][1]:
        raise ConfigurationError("physics.z_range_mm must be increasing")
    offsets = physics_values.get("offsets_mm", (2., 4., 6.))
    if not isinstance(offsets, (list, tuple)) or len(offsets) != 3:
        raise ConfigurationError("physics.offsets_mm needs exactly three distinct positive offsets")
    physics_values["offsets_mm"] = tuple(_number(v, "physics.offsets_mm", positive=True) for v in offsets)
    if list(physics_values["offsets_mm"]) != sorted(set(physics_values["offsets_mm"])):
        raise ConfigurationError("physics.offsets_mm must be strictly increasing")
    for key, value in list(physics_values.items()):
        if key not in {"z_range_mm", "offsets_mm", "field_convention", "conductivity_layers"}:
            physics_values[key] = _number(value, f"physics.{key}", positive=True, integer=key == "z_samples")
    layers = physics_values.get("conductivity_layers", {})
    if not isinstance(layers, dict):
        raise ConfigurationError("physics.conductivity_layers must be a mapping")
    normalized_layers: dict[str, dict[str, Any]] = {}
    for material, layer in layers.items():
        if not isinstance(material, str) or not material.strip():
            raise ConfigurationError("conductivity layer material names must be nonempty strings")
        layer = _mapping(layer, f"conductivity_layers.{material}", {"conductivity", "mu"})
        conductivity = layer.get("conductivity")
        if isinstance(conductivity, bool):
            raise ConfigurationError(f"{material}.conductivity must be positive S/m or PEC")
        if conductivity != "PEC":
            try:
                conductivity = float(conductivity)
            except (ValueError, TypeError) as exc:
                raise ConfigurationError(f"{material}.conductivity must be positive S/m or PEC") from exc
            conductivity = _number(conductivity, f"{material}.conductivity", positive=True)
        normalized_layers[material] = {"conductivity": conductivity, "mu": _number(layer.get("mu", 1.0), f"{material}.mu", positive=True)}
    physics_values["conductivity_layers"] = normalized_layers
    physics = PhysicsConfig(**physics_values)
    if physics.frequency_min_mhz >= physics.frequency_max_mhz:
        raise ConfigurationError("physics frequency band must be increasing")
    if physics.z_samples < 5 or physics.z_samples % 2 != 1:
        raise ConfigurationError("physics.z_samples must be an odd integer of at least five")
    if physics.beta != 1.0 or physics.field_convention != "peak":
        raise ConfigurationError("physics currently supports only beta=1 and peak field convention")
    if max(physics.gradient_tolerance, physics.integration_tolerance) >= 1:
        raise ConfigurationError("physics relative tolerances must be below one")
    if solver.target_frequency_mhz > physics.frequency_min_mhz:
        raise ConfigurationError("solver target frequency must not exceed the target band's lower edge")
    if solver.upper_frequency_mhz < physics.frequency_max_mhz:
        raise ConfigurationError("solver.upper_frequency_mhz must include the objective band's upper edge")
    if solver.coverage_policy == "upper_sentinel" and solver.upper_frequency_mhz == physics.frequency_max_mhz:
        raise ConfigurationError("solver.upper_frequency_mhz must exceed the objective band's upper edge to establish coverage")

    search_values = _section(root, "search", SearchConfig)
    integer_fields = {"max_solves", "initial_points", "seed", "candidate_pool", "max_candidate_attempts", "candidate_draws"}
    for key, value in list(search_values.items()):
        search_values[key] = _number(value, f"search.{key}", positive=key != "seed", integer=key in integer_fields)
    search = SearchConfig(**search_values)
    if search.seed < 0 or search.initial_points < 1:
        raise ConfigurationError("search seed must be nonnegative and initial_points must be positive")
    if not 0 < search.local_fraction <= 1 or not 0 < search.min_radius <= search.initial_radius <= search.max_radius <= 1:
        raise ConfigurationError("Invalid normalized local search fraction or radius ordering")
    if search.candidate_draws < search.candidate_pool or search.max_candidate_attempts < search.max_solves:
        raise ConfigurationError("candidate_draws must cover candidate_pool; max_candidate_attempts must cover max_solves")

    result_values = _section(root, "results", ResultsConfig)
    results = ResultsConfig(**result_values)
    for key in ("frequency", "q_loaded", "efield"):
        value = getattr(results, key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"results.{key} must be a nonempty tree template")
        try:
            placeholders = [(name, spec, conversion) for _, name, spec, conversion in string.Formatter().parse(value) if name is not None]
            if placeholders != [("mode", "", None)]:
                raise ValueError("Only {mode} is supported")
            value.format(mode=1)
        except (ValueError, KeyError, IndexError) as exc:
            raise ConfigurationError(f"results.{key} must contain only the {{mode}} placeholder") from exc
    if results.frequency_unit not in {"Hz", "kHz", "MHz", "GHz"}:
        raise ConfigurationError("results.frequency_unit must be Hz, kHz, MHz, or GHz")
    config = WorkflowConfig(PathsConfig(template, output, library_path), tuple(parameters[name] for name in PARAMETER_NAMES), physics, geometry, solver, search, results)
    if live:
        config.validate_live()
    return config
