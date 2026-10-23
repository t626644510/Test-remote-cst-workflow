"""Configurable saved-mode collection on a caller-owned CST project.

VBA provenance: cst-hom-audit/scripts/collect.py (reviewed 2026-09-28).
Its CST 2026 verified calls are documented under Online Help/mergedProjects/
VBA_3D/special_vbapostproc (VectorPlot3D, QFactor). The existing CSTProject
raw ``project`` accessor exposes ``schematic.execute_vba_code``; this module
does not invent Model3D methods, create environments, solve, close or save.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field, fields as dataclass_fields, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from cst_optimization.core.project import CSTProject
from cst_optimization.core.results import ResultReader

from .physics import TransverseMetrics, calculate_transverse_metrics


@dataclass(frozen=True)
class PostprocessConfig:
    """Result contract and beam integration settings; machine paths are absent."""

    z_range_mm: tuple[float, float]
    z_samples: int = 1883
    offsets_mm: tuple[float, float, float] = (2.0, 4.0, 6.0)
    frequency_pattern: str = r"1D Results\\Mode Frequencies\\Mode (\d+)"
    frequency_unit: str = "MHz"
    q_loaded_path: str = r"1D Results\Q Factors\Total-Q\Mode {mode}"
    field_path: str = r"2D/3D Results\Modes\Mode {mode}\e"
    geometry_unit: str = "mm"
    beta: float = 1.0
    field_amplitude: str = "peak"
    conductivity_layers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    gradient_tolerance: float = 0.02
    sampling_tolerance: float = 0.01
    minimum_q: float = 10.0
    energy_match_tolerance: float = 1e-6
    minimum_separation_linewidths: float = 1.0
    vba_timeout_s: float = 180.0
    mode_policy: str = "strict_all"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> PostprocessConfig:
        """Construct and validate a portable explicit postprocessing contract."""
        kwargs = dict(values)
        for key in ("z_range_mm", "offsets_mm"):
            if key in kwargs:
                kwargs[key] = tuple(map(float, kwargs[key]))
        return cls(**kwargs)

    def __post_init__(self) -> None:
        if self.mode_policy not in ("strict_all", "largest_two"):
            raise ValueError("mode_policy must be strict_all or largest_two")
        if self.beta != 1 or self.field_amplitude != "peak":
            raise ValueError("postprocessor requires confirmed peak fields and beta=1")
        if len(self.z_range_mm) != 2 or not np.isfinite(self.z_range_mm).all() or self.z_range_mm[0] >= self.z_range_mm[1]:
            raise ValueError("z_range_mm must be finite and increasing")
        if isinstance(self.z_samples, bool) or not isinstance(self.z_samples, int) or self.z_samples < 5 or self.z_samples % 2 != 1:
            raise ValueError("z_samples must be an odd integer >=5")
        if len(self.offsets_mm) != 3 or not np.isfinite(self.offsets_mm).all() or not 0 < self.offsets_mm[0] < self.offsets_mm[1] < self.offsets_mm[2]:
            raise ValueError("three increasing positive offsets_mm required")
        if self.frequency_unit not in {"Hz", "kHz", "MHz", "GHz"} or self.geometry_unit not in {"mm", "cm", "m", "um"}:
            raise ValueError("unsupported frequency/geometry units")
        if re.compile(self.frequency_pattern).groups != 1:
            raise ValueError("frequency_pattern requires one numeric mode capture")
        if "{mode}" not in self.q_loaded_path or "{mode}" not in self.field_path:
            raise ValueError("Q and E-field paths require {mode}")
        thresholds = (self.gradient_tolerance, self.sampling_tolerance, self.minimum_q, self.energy_match_tolerance, self.minimum_separation_linewidths, self.vba_timeout_s)
        if not np.isfinite(thresholds).all() or min(thresholds) <= 0:
            raise ValueError("quality thresholds and VBA timeout must be finite positive")


@dataclass(frozen=True)
class NativeMode:
    """Dynamic native mode identity, frequency in Hz and dimensionless loaded Q."""

    mode_number: int
    frequency_hz: float
    q_loaded: float
    frequency_path: str = ""
    q_loaded_path: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.mode_number, bool) or not isinstance(self.mode_number, int) or self.mode_number < 1:
            raise ValueError("native mode identity must be a positive integer")
        if not np.isfinite([self.frequency_hz, self.q_loaded]).all() or min(self.frequency_hz, self.q_loaded) <= 0:
            raise ValueError("native frequency and loaded Q must be finite and positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessedMode:
    """Native mode and optional validated field-derived impedance."""

    native: NativeMode
    metrics: TransverseMetrics | None
    energy_j: float | None = None
    quality_reasons: tuple[str, ...] = ()

    @property
    def quality_ok(self) -> bool:
        return self.metrics is not None and self.metrics.quality_ok and not self.quality_reasons

    def to_dict(self) -> dict[str, Any]:
        return {**self.native.to_dict(), "metrics": self.metrics.to_dict() if self.metrics else None,
                "energy_j": self.energy_j, "quality_ok": self.quality_ok,
                "quality_reasons": list(self.quality_reasons)}


@dataclass(frozen=True)
class PostprocessResult:
    """All native frequencies for coverage and every in-band mode for scoring."""

    native_modes: tuple[NativeMode, ...]
    modes: tuple[ProcessedMode, ...]
    quality_reasons: tuple[str, ...] = ()
    mode_policy: str = "strict_all"

    def _ranked_modes(self) -> tuple[ProcessedMode, ...]:
        """Rank finite transverse impedances (ohm/m) before applying quality gates.

        An unreadable mode cannot be classified as weak. Missing fields/energy
        or a nonfinite score therefore still prevent a successful selection.
        """
        for mode in self.modes:
            score = mode.metrics.impedance_principal_ohm_per_m if mode.metrics else None
            if score is None or not math.isfinite(score) or score < 0:
                return ()
        return tuple(sorted(self.modes,
            key=lambda m: m.metrics.impedance_principal_ohm_per_m, reverse=True))

    @property
    def quality_ok(self) -> bool:
        if not self.modes or self.quality_reasons:
            return False
        if self.mode_policy == "largest_two":
            ranked = self._ranked_modes()
            # User-selected objective: weaker modes retain diagnostics but no
            # longer veto the two strongest in-band single-mode responses.
            return bool(ranked) and all(m.quality_ok for m in ranked[:2])
        return all(m.quality_ok for m in self.modes)

    @property
    def worst_impedance_ohm_per_m(self) -> float | None:
        if not self.quality_ok:
            return None
        return max(m.metrics.impedance_principal_ohm_per_m for m in self.modes)  # type: ignore[union-attr,type-var]

    @property
    def objective_mode_numbers(self) -> list[int]:
        """Select by impedance rank, never by CST ID or by discarding bad leaders."""
        if not self.quality_ok:
            return []
        ranked = self._ranked_modes()
        return [m.native.mode_number for m in (ranked[:2] if self.mode_policy == "largest_two" else ranked)]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "convention": "peak; beta=1; circuit c*gi*gj_conjugate/(2*omega^2*U); ohm/m",
                "native_modes": [m.to_dict() for m in self.native_modes],
                "modes": [m.to_dict() for m in self.modes], "quality_ok": self.quality_ok,
                "quality_reasons": list(self.quality_reasons),
                "mode_policy": self.mode_policy, "objective_mode_numbers": self.objective_mode_numbers,
                "worst_impedance_ohm_per_m": self.worst_impedance_ohm_per_m}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _read_scalar(reader: ResultReader, path: str) -> float:
    """Native frequency and Q entries are one-value 1D results."""
    values = np.asarray(reader.get_result_item(path).get_ydata()).reshape(-1)
    if len(values) != 1 or np.iscomplexobj(values) and np.any(values.imag != 0):
        raise ValueError(f"expected one real scalar at {path}")
    value = float(values[0].real)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"nonfinite/nonpositive scalar at {path}")
    return value


def read_native_modes(project_path: str | Path, config: PostprocessConfig) -> list[NativeMode]:
    """Discover every native mode, including outside the objective window.

    Missing Q or an unreadable frequency is an error; modes are never silently
    omitted. The caller checks solver-window coverage before field sampling.
    """
    reader = ResultReader(str(project_path), allow_interactive=True, cache_project_file=False)
    pattern = re.compile(config.frequency_pattern)
    factor = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[config.frequency_unit]
    modes: dict[int, NativeMode] = {}
    for path in reader.list_tree_items():
        match = pattern.fullmatch(path)
        if not match:
            continue
        number = int(match.group(1))
        if number < 1 or number in modes:
            raise ValueError(f"invalid/duplicate native mode identity {number}")
        qpath = config.q_loaded_path.format(mode=number)
        modes[number] = NativeMode(number, _read_scalar(reader, path) * factor,
                                   _read_scalar(reader, qpath), path, qpath)
    if not modes:
        raise ValueError("no modes matched the configured native frequency pattern")
    return sorted(modes.values(), key=lambda mode: (mode.frequency_hz, mode.mode_number))


def trajectory_coordinates(offsets_mm: Sequence[float]) -> np.ndarray:
    """Return the beam axis and six symmetric offsets along each axis, in mm."""
    offsets = sorted([-float(x) for x in offsets_mm] + list(map(float, offsets_mm)))
    return np.asarray([(0.0, 0.0)] + [(x, 0.0) for x in offsets] + [(0.0, y) for y in offsets])


def _layers(project_path: Path, config: PostprocessConfig) -> dict[str, dict[str, Any]]:
    layers = {name: dict(value) for name, value in config.conductivity_layers.items()}
    if not layers:
        qfi = project_path.with_suffix("") / "Model/3D/Model.qfi"
        if qfi.exists():
            for line in qfi.read_text(errors="replace").splitlines():
                if line.startswith("Layer "):
                    name, conductivity, mu = line[6:].rsplit(None, 2)
                    layers[name] = {"conductivity": conductivity, "mu": float(mu)}
    if not layers:
        raise ValueError("no QFactor conductivity layers: configure or provide Model.qfi")
    for name, value in layers.items():
        sigma, mu = value["conductivity"], float(value["mu"])
        if not name or not math.isfinite(mu) or mu <= 0:
            raise ValueError("invalid QFactor layer name/permeability")
        if str(sigma).upper() != "PEC" and (not math.isfinite(float(sigma)) or float(sigma) <= 0):
            raise ValueError("invalid QFactor conductivity")
    return layers


def _vbs(value: Any) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("VBA string cannot contain a newline")
    return '"' + text.replace('"', '""') + '"'


def _num(value: float) -> str:
    return format(float(value), ".15g")


def build_field_vba(mode: NativeMode, raw_dir: Path, config: PostprocessConfig) -> str:
    """Verified VectorPlot3D sampling macro; coordinates converted from mm."""
    scale = {"mm": 1.0, "cm": 0.1, "m": 0.001, "um": 1000.0}[config.geometry_unit]
    z0, z1 = config.z_range_mm
    count = config.z_samples
    adds = []
    for x, y in trajectory_coordinates(config.offsets_mm):
        adds.extend([f"For j=0 To {count - 1}", f"VectorPlot3D.AddListItem {_num(x * scale)}, {_num(y * scale)}, {_num(z0 * scale)}+{_num((z1 - z0) * scale)}*j/{count - 1}", "Next j"])
    n = 13 * count
    return "\n".join(["Option Explicit", "Sub Main", "Dim j As Long,k As Long,fo As Integer",
        "Dim xr As Double,yr As Double,zr As Double,xi As Double,yi As Double,zi As Double,ok As Boolean",
        f"If Not SelectTreeItem({_vbs(config.field_path.format(mode=mode.mode_number))}) Then Err.Raise 1001, , \"Missing E field\"",
        "VectorPlot3D.Reset", *adds, "VectorPlot3D.CalculateList",
        f"If VectorPlot3D.GetListLength <> {n} Then Err.Raise 1002", "fo=FreeFile",
        f"Open {_vbs(raw_dir / 'tracks.csv')} For Output As #fo",
        'Print #fo,"Ex_re,Ey_re,Ez_re,Ex_im,Ey_im,Ez_im,valid"', f"For k=0 To {n - 1}",
        "ok=VectorPlot3D.GetListItem(k,xr,yr,zr,xi,yi,zi)",
        'Print #fo,Trim$(Str$(xr)) & "," & Trim$(Str$(yr)) & "," & Trim$(Str$(zr)) & "," & Trim$(Str$(xi)) & "," & Trim$(Str$(yi)) & "," & Trim$(Str$(zi)) & "," & CStr(CInt(ok))',
        "Next k", "Close #fo", "VectorPlot3D.Reset", "End Sub"])


def build_energy_vba(mode: NativeMode, raw_dir: Path, layers: Mapping[str, Mapping[str, Any]]) -> str:
    """Verified QFactor macro for matching stored energy; wall Q is diagnostic."""
    settings = []
    for name, value in layers.items():
        settings += [f".SetConductivity {_vbs(name)}, {_vbs(value['conductivity'])}", f".SetMu {_vbs(name)}, {_num(value['mu'])}"]
    return "\n".join(["Option Explicit", "Sub Main", "Dim fo As Integer", "With QFactor", ".Reset",
        f'.SetHField "Mode {mode.mode_number}"', *settings, ".UseNewMethod True", ".Save3DData False", ".Calculate",
        f".ASCIIExport {_vbs(raw_dir / 'qfactor_check.txt')}", "End With", "fo=FreeFile",
        f"Open {_vbs(raw_dir / 'energy.csv')} For Output As #fo", 'Print #fo,"U_J,Q_wall_postprocess"',
        'Print #fo,Trim$(Str$(QFactor.GetTotalEnergy)) & "," & Trim$(Str$(QFactor.GetTotalQ))', "Close #fo", "End Sub"])


def analyze_mode_files(mode: NativeMode, raw_dir: Path, config: PostprocessConfig) -> ProcessedMode:
    """Validate raw fields, QFactor mode frequency/energy and compute impedance."""
    with (raw_dir / "energy.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError("energy.csv must contain exactly one mode")
    energy, qwall = float(rows[0]["U_J"]), float(rows[0]["Q_wall_postprocess"])
    if not np.isfinite([energy, qwall]).all() or min(energy, qwall) <= 0:
        raise ValueError("invalid stored energy/wall Q")
    meta = {}
    check_path = raw_dir / "qfactor_check.txt"
    if not check_path.exists():
        check_path = raw_dir / "losses.txt"  # Earlier cst-hom-audit archives.
    for line in check_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        for prefix in ("Frequency/Hz", "Energy/J"):
            if line.startswith(prefix):
                meta[prefix] = float(line.split()[-1])
    if set(meta) != {"Frequency/Hz", "Energy/J"} or not np.isfinite(list(meta.values())).all():
        raise ValueError("QFactor check lacks finite frequency/energy metadata")
    if abs(meta["Frequency/Hz"] / mode.frequency_hz - 1) > config.energy_match_tolerance or abs(meta["Energy/J"] / energy - 1) > config.energy_match_tolerance:
        raise ValueError("QFactor energy belongs to a different mode or field normalization")
    data = np.loadtxt(raw_dir / "tracks.csv", delimiter=",", skiprows=1, ndmin=2)
    if data.shape != (13 * config.z_samples, 7) or not np.isfinite(data).all() or not np.all(data[:, -1] != 0):
        raise ValueError("invalid/incomplete VectorPlot3D samples")
    ez = (data[:, 2] + 1j * data[:, 5]).reshape(13, config.z_samples)
    metrics = calculate_transverse_metrics(ez, np.linspace(*config.z_range_mm, config.z_samples) * 1e-3,
        trajectory_coordinates(config.offsets_mm), frequency_hz=mode.frequency_hz, energy_j=energy,
        q_loaded=mode.q_loaded, gradient_tolerance=config.gradient_tolerance,
        sampling_tolerance=config.sampling_tolerance, minimum_q=config.minimum_q,
        enforce_minimum_q=config.mode_policy == "strict_all")
    return ProcessedMode(mode, metrics, energy)


def _finalize_result(native: tuple[NativeMode, ...], rows: Sequence[ProcessedMode], config: PostprocessConfig) -> PostprocessResult:
    """Apply the same isolated-mode and empty-band rules online and offline."""
    processed = []
    for row in rows:
        mode = row.native
        overlap = any(other.mode_number != mode.mode_number and
            abs(other.frequency_hz - mode.frequency_hz) <= config.minimum_separation_linewidths *
            0.5 * (mode.frequency_hz / mode.q_loaded + other.frequency_hz / other.q_loaded)
            for other in native)
        if overlap and config.mode_policy == "strict_all":
            row = ProcessedMode(mode, row.metrics, row.energy_j,
                (*row.quality_reasons, "overlapping_mode_linewidths"))
        processed.append(row)
    return PostprocessResult(native, tuple(processed), () if processed else ("no_modes_in_objective_band",), config.mode_policy)


def analyze_bundle(bundle_dir: str | Path, *, mode_policy: str | None = None) -> PostprocessResult:
    """Recompute a relocated raw bundle without CST access or filesystem writes.

    Modern bundles retain their objective band. Legacy skill bundles without a
    band are conservatively checked over *all* native modes: missing fields
    cannot become a successful all-window result. ``source_project`` is merely
    provenance and is never opened. Legacy energy ``losses.txt`` is supported.
    """
    folder = Path(bundle_dir)
    native_json = json.loads((folder / "native.json").read_text(encoding="utf-8-sig"))
    raw_config = json.loads((folder / "field_config.json").read_text(encoding="utf-8-sig"))
    config_names = {item.name for item in dataclass_fields(PostprocessConfig)}
    config = PostprocessConfig.from_mapping({k: v for k, v in raw_config.items() if k in config_names})
    if mode_policy is not None:
        config = replace(config, mode_policy=mode_policy)
    data = native_json["modes"]
    if isinstance(data, dict):
        native = tuple(NativeMode(int(key), float(value["frequency_Hz"]), float(value["Q_loaded"]))
                       for key, value in data.items())
    else:
        native = tuple(NativeMode(**value) for value in data)
    if len({m.mode_number for m in native}) != len(native):
        raise ValueError("duplicate native mode identities")
    band = raw_config.get("band_mhz")
    if band is not None and (len(band) != 2 or not np.isfinite(band).all() or not 0 < band[0] < band[1]):
        raise ValueError("invalid archived objective band")
    selected = [m for m in native if band is None or band[0] * 1e6 <= m.frequency_hz <= band[1] * 1e6]
    rows = []
    for mode in selected:
        try:
            rows.append(analyze_mode_files(mode, folder / "fields" / f"mode_{mode.mode_number}", config))
        except Exception as exc:
            rows.append(ProcessedMode(mode, None, None, (f"postprocess_failed:{type(exc).__name__}:{exc}",)))
    return _finalize_result(native, rows, config)


def collect_and_analyze(
    project: CSTProject, project_path: str | Path, output_dir: str | Path,
    config: PostprocessConfig, band_mhz: tuple[float, float],
    *, native_modes: Sequence[NativeMode] | None = None,
) -> PostprocessResult:
    """Sample ALL in-band modes without changing project/session ownership.

    Caller must pass its solved, saved working copy and independently verify
    frequency-window coverage. Any missing mode data prevents success. Native
    out-of-band modes remain in native.json and participate in overlap checks.
    """
    path, out = Path(project_path).resolve(), Path(output_dir).resolve()
    if Path(project.filename).resolve() != path:
        raise ValueError("postprocess project handle does not match working-copy path")
    if not np.isfinite(band_mhz).all() or not 0 < band_mhz[0] < band_mhz[1]:
        raise ValueError("invalid objective frequency band in MHz")
    out.mkdir(parents=True, exist_ok=False)
    native = tuple(native_modes if native_modes is not None else read_native_modes(path, config))
    if len({m.mode_number for m in native}) != len(native):
        raise ValueError("duplicate native mode identities")
    _write_json(out / "native.json", {"source_project": str(path), "modes": [m.to_dict() for m in native]})
    layers = _layers(path, config)
    _write_json(out / "field_config.json", {**asdict(config), "conductivity_layers": layers,
                "xy_mm": trajectory_coordinates(config.offsets_mm).tolist(), "band_mhz": list(band_mhz)})
    selected = [m for m in native if band_mhz[0] * 1e6 <= m.frequency_hz <= band_mhz[1] * 1e6]
    processed = []
    for mode in selected:
        raw = out / "fields" / f"mode_{mode.mode_number}"
        raw.mkdir(parents=True)
        try:
            for name, macro in (("tracks.bas", build_field_vba(mode, raw, config)),
                                ("energy.bas", build_energy_vba(mode, raw, layers))):
                (raw / name).write_text(macro, encoding="utf-8")
                project.project.schematic.execute_vba_code(macro, timeout=config.vba_timeout_s)
            processed.append(analyze_mode_files(mode, raw, config))
        except Exception as exc:
            reason = f"postprocess_failed:{type(exc).__name__}:{exc}"
            (raw / "error.txt").write_text(reason, encoding="utf-8")
            processed.append(ProcessedMode(mode, None, None, (reason,)))
    result = _finalize_result(native, processed, config)
    _write_json(out / "analysis.json", result.to_dict())
    return result
