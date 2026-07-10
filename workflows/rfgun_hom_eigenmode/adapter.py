"""Configuration-driven CST result-tree adapter for Workflow 4."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from cst_optimization.core.results import ResultReader

from .config import FieldContractConfig, ResultContractConfig
from .fields import save_complex_line_npz
from .models import ComplexLineField, NativeModeResult


def _unit_factor(unit: str) -> float:
    normalized = unit.strip().lower()
    factors = {
        "": 1.0,
        "hz": 1.0,
        "khz": 1e3,
        "mhz": 1e6,
        "ghz": 1e9,
        "v": 1.0,
        "j": 1.0,
        "w": 1.0,
        "ohm": 1.0,
        "ω": 1.0,
    }
    if normalized not in factors:
        raise ValueError(f"unsupported result unit {unit!r}")
    return factors[normalized]


class EigenmodeResultAdapter:
    """Normalize configured 0D/1D CST result paths into mode records."""

    def __init__(
        self,
        project_path: str | Path,
        contract: ResultContractConfig,
        *,
        max_modes: int = 3,
        allow_interactive: bool = False,
    ) -> None:
        self.project_path = Path(project_path)
        self.contract = contract
        self.max_modes = max_modes
        self.reader = ResultReader(
            str(self.project_path),
            allow_interactive=allow_interactive,
            cache_project_file=False,
        )
        self.errors: dict[str, str] = {}

    def _read_series(self, logical_name: str, path: str) -> list[float]:
        factor = _unit_factor(self.contract.units.get(logical_name, ""))
        if "{mode}" in path:
            values: list[float] = []
            for mode in range(1, self.max_modes + 1):
                try:
                    scalar = self.reader.get_scalar(path.format(mode=mode))
                except Exception:
                    break
                values.append(float(scalar.value) * factor)
            return values

        try:
            _, values = self.reader.get_1d_result(path)
            array = np.asarray(values).reshape(-1)
            return [
                float(value.real if np.iscomplexobj(value) else value) * factor
                for value in array[: self.max_modes]
            ]
        except Exception as one_d_error:
            try:
                scalar = self.reader.get_scalar(path)
                return [float(scalar.value) * factor]
            except Exception as scalar_error:
                raise RuntimeError(
                    f"1D read failed: {one_d_error}; 0D read failed: {scalar_error}"
                ) from scalar_error

    def read_native_modes(self) -> list[NativeModeResult]:
        series: dict[str, list[float]] = {}
        self.errors = {}
        all_paths = {
            **self.contract.paths,
            **{
                f"regional_q:{name}": path
                for name, path in self.contract.regional_q_paths.items()
            },
        }
        for logical_name, path in all_paths.items():
            if not path.strip():
                self.errors[logical_name] = "path_not_configured"
                continue
            try:
                series[logical_name] = self._read_series(logical_name, path)
            except Exception as exc:
                self.errors[logical_name] = str(exc)

        frequencies = series.get("frequency", [])
        modes: list[NativeModeResult] = []
        for index, frequency_hz in enumerate(frequencies[: self.max_modes]):
            if not math.isfinite(frequency_hz) or frequency_hz <= 0:
                continue

            def value(name: str) -> float | None:
                values = series.get(name, [])
                return values[index] if index < len(values) else None

            regional = {
                key.split(":", 1)[1]: values[index]
                for key, values in series.items()
                if key.startswith("regional_q:") and index < len(values)
            }
            q0_values = [
                regional[name]
                for name in self.contract.q0_components
                if name in regional and regional[name] > 0
            ]
            q0 = (
                1.0 / sum(1.0 / q_value for q_value in q0_values)
                if len(q0_values) == len(self.contract.q0_components)
                and q0_values
                else value("q0")
            )
            source_paths = {
                name: path
                for name, path in self.contract.paths.items()
                if name in series
            }
            modes.append(
                NativeModeResult(
                    mode_number=index + 1,
                    frequency_hz=frequency_hz,
                    r_over_q_ohm=value("r_over_q"),
                    voltage_v=value("voltage"),
                    total_energy_j=value("total_energy"),
                    total_loss_w=value("total_loss"),
                    residual=value("residual"),
                    q_loaded=value("q_loaded"),
                    q0=q0,
                    regional_q=regional,
                    source_treepaths=source_paths,
                )
            )
        return modes

    def audit(
        self,
        field_contract: FieldContractConfig,
    ) -> dict[str, Any]:
        tree_items: list[str] = []
        colormap_items: list[str] = []
        tree_error = ""
        try:
            tree_items = self.reader.list_tree_items("0D/1D")
            colormap_items = self.reader.list_colormap_items()
        except Exception as exc:
            tree_error = str(exc)

        native_modes = self.read_native_modes()
        required_missing = [
            name
            for name in self.contract.required
            if name not in self.contract.paths or name in self.errors
        ]
        export_files = (
            sorted(
                str(path.relative_to(field_contract.export_dir))
                for path in field_contract.export_dir.rglob("*")
                if path.is_file()
            )
            if field_contract.export_dir.exists()
            else []
        )
        field_matches: dict[str, dict[str, list[str]]] = {}
        for point, pattern in field_contract.patterns.items():
            field_matches[point] = {}
            for mode in range(1, self.max_modes + 1):
                formatted = pattern.format(mode=mode, point=point)
                matches = [
                    str(path.relative_to(field_contract.export_dir))
                    for path in field_contract.export_dir.glob(formatted)
                ]
                field_matches[point][str(mode)] = sorted(matches)
        line_result_status: dict[str, dict[str, str]] = {}
        for point, path in field_contract.line_result_paths.items():
            line_result_status[point] = {}
            for mode in range(1, len(native_modes) + 1):
                formatted = path.format(mode=mode, point=point)
                try:
                    self.read_complex_line(formatted)
                    line_result_status[point][str(mode)] = "available"
                except Exception as exc:
                    line_result_status[point][str(mode)] = str(exc)
        required_points = {"center", "x_plus", "x_minus", "y_plus", "y_minus"}
        missing_field_patterns = []
        for mode in range(1, len(native_modes) + 1):
            for point in required_points:
                line_ok = (
                    line_result_status.get(point, {}).get(str(mode))
                    == "available"
                )
                hdf5_ok = bool(
                    field_matches.get(point, {}).get(str(mode), [])
                )
                if not (line_ok or hdf5_ok):
                    missing_field_patterns.append(f"mode_{mode}:{point}")

        return {
            "project_path": str(self.project_path.resolve()),
            "tree_items_0d_1d": tree_items,
            "tree_items_colormap": colormap_items,
            "tree_read_error": tree_error,
            "configured_paths": self.contract.paths,
            "configured_regional_q_paths": self.contract.regional_q_paths,
            "result_read_errors": self.errors,
            "native_mode_count": len(native_modes),
            "required_missing": required_missing,
            "missing_field_patterns": missing_field_patterns,
            "template_contract_complete": not (
                required_missing or missing_field_patterns
            ),
            "field_export_dir": str(field_contract.export_dir.resolve()),
            "field_export_files": export_files,
            "field_pattern_matches": field_matches,
            "line_result_status": line_result_status,
        }

    def read_complex_line(self, tree_path: str) -> ComplexLineField:
        """Read a complex 1D Ez result and convert its coordinate to metres."""

        item = self.reader.get_result_item(tree_path)
        z = np.asarray(item.get_xdata(), dtype=float)
        ez = np.asarray(item.get_ydata(), dtype=np.complex128)
        xlabel = str(getattr(item, "xlabel", "") or "").lower()
        if "/ mm" in xlabel or xlabel.endswith("mm"):
            z = z * 1e-3
        elif "/ cm" in xlabel or xlabel.endswith("cm"):
            z = z * 1e-2
        elif "/ m" not in xlabel and not xlabel.endswith("m"):
            raise ValueError(
                f"cannot determine longitudinal coordinate unit from {xlabel!r}"
            )
        if z.ndim != 1 or ez.ndim != 1 or len(z) != len(ez) or len(z) < 2:
            raise ValueError(
                f"invalid complex line shape z={z.shape}, Ez={ez.shape}"
            )
        return ComplexLineField(
            z_m=z,
            ez_v_per_m=ez,
            source_path=tree_path,
        )

    def archive_complex_lines(
        self,
        modes: list[NativeModeResult],
        field_contract: FieldContractConfig,
        destination: str | Path,
    ) -> dict[str, dict[str, str]]:
        """Archive configured 1D Ez curves as portable NPZ artifacts."""

        output = Path(destination)
        status: dict[str, dict[str, str]] = {}
        for mode in modes:
            mode_key = str(mode.mode_number)
            status[mode_key] = {}
            for point, template in field_contract.line_result_paths.items():
                tree_path = template.format(
                    mode=mode.mode_number,
                    point=point,
                )
                try:
                    field = self.read_complex_line(tree_path)
                    target = output / f"mode_{mode.mode_number}_{point}.npz"
                    save_complex_line_npz(target, field)
                    status[mode_key][point] = str(target.resolve())
                except Exception as exc:
                    status[mode_key][point] = f"ERROR: {exc}"
        return status


def write_native_results(
    path: str | Path,
    modes: list[NativeModeResult],
    errors: dict[str, str],
) -> None:
    Path(path).write_text(
        json.dumps(
            {
                "modes": [mode.to_dict() for mode in modes],
                "result_read_errors": errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def read_native_results(path: str | Path) -> tuple[list[NativeModeResult], dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return (
        [NativeModeResult.from_dict(item) for item in payload.get("modes", [])],
        dict(payload.get("result_read_errors", {})),
    )
