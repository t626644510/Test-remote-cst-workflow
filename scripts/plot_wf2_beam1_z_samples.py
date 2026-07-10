"""Plot Beam1 longitudinal wake impedance for WF2 warmup samples.

This is a no-CST artifact inspection helper.  It reads the curated
``wf2_warmup_total/index.total.jsonl`` bundle, opens each referenced NPZ, and
creates one PNG per effective sample.  Frequency values are plotted in the
axis units stored by the NPZ files; current WF2 wakefield NPZs store a
MHz-equivalent axis, while objective replay converts it to Hz internally.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


BEAM1_Z_KEY = "1D_Results_Particle_Beams_ParticleBeam1_Wake_impedance_Z"
DEFAULT_RESULTS = Path("Results")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            record["_line"] = line_no
            records.append(record)
    return records


def _is_valid_warmup_record(record: dict[str, Any], bundle_dir: Path) -> bool:
    if record.get("record_type") != "evaluation":
        return False
    if record.get("evaluation_ok") is not True:
        return False
    if record.get("solver_ok") is not True:
        return False
    if record.get("smoke_only") is True:
        return False
    try:
        scalar = float(record.get("scalar_penalty"))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(scalar):
        return False
    npz_name = str(record.get("npz_file", "") or "")
    return bool(npz_name) and (bundle_dir / npz_name).is_file()


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return "N/A"
    if abs(numeric) >= 1000 or (0 < abs(numeric) < 0.001):
        return f"{numeric:.4e}"
    return f"{numeric:.5g}"


def _text_block(record: dict[str, Any], has_beam1_z: bool) -> str:
    params = record.get("params", {})
    raw_values = record.get("raw_values", {})
    penalties = record.get("penalty_values", {})
    mask = record.get("measurement_mask", {})
    lines = [
        f"bundle iter: {record.get('iter')}",
        f"source iter: {record.get('source_iter')}  attempt: {record.get('source_attempt')}",
        f"source npz: {record.get('source_npz')}",
        f"bundle npz: {record.get('npz_file')}",
        f"scalar penalty: {_format_value(record.get('scalar_penalty'))}",
        f"Beam1 Z: {'available' if has_beam1_z else 'MISSING in this NPZ'}",
        "",
        "Raw / penalty / measured",
    ]
    for name in ("z_longitudinal", "z_transverse", "antenna_absorption", "antenna_absorption_db"):
        measured = mask.get(name, False)
        lines.append(
            f"{name}: raw={_format_value(raw_values.get(name))}  "
            f"pen={_format_value(penalties.get(name))}  "
            f"meas={'Y' if measured else 'N'}"
        )
    lines.extend(["", "Antenna / geometry parameters"])
    for name, value in params.items():
        lines.append(f"{name}: {_format_value(value)}")
    skipped = record.get("skipped_phases", [])
    if skipped:
        lines.extend(["", f"skipped phases: {', '.join(map(str, skipped))}"])
    return "\n".join(lines)


def _load_beam1_z(npz_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    with np.load(npz_path, allow_pickle=True) as data:
        x_key = f"{BEAM1_Z_KEY}/xdata"
        real_key = f"{BEAM1_Z_KEY}/ydata_real"
        imag_key = f"{BEAM1_Z_KEY}/ydata_imag"
        if x_key not in data.files or real_key not in data.files or imag_key not in data.files:
            return None
        return (
            np.asarray(data[x_key], dtype=float),
            np.asarray(data[real_key], dtype=float),
            np.asarray(data[imag_key], dtype=float),
        )


def _plot_record(record: dict[str, Any], bundle_dir: Path, output_path: Path) -> bool:
    npz_path = bundle_dir / str(record["npz_file"])
    beam1_z = _load_beam1_z(npz_path)
    has_beam1_z = beam1_z is not None

    fig = plt.figure(figsize=(15.5, 8.8))
    grid = fig.add_gridspec(
        nrows=2,
        ncols=2,
        width_ratios=[2.4, 1.0],
        height_ratios=[1.0, 1.0],
        left=0.055,
        right=0.985,
        top=0.92,
        bottom=0.09,
        wspace=0.12,
        hspace=0.14,
    )
    ax_mag = fig.add_subplot(grid[0, 0])
    ax_components = fig.add_subplot(grid[1, 0], sharex=ax_mag)
    ax_text = fig.add_subplot(grid[:, 1])
    ax_text.axis("off")

    title = (
        f"WF2 Beam1 Wake Impedance Z | bundle {int(record['iter']):04d} "
        f"| source iter {record.get('source_iter')}"
    )
    fig.suptitle(title, fontsize=14, fontweight="bold")

    if beam1_z is None:
        ax_mag.text(
            0.5,
            0.5,
            "Beam1 Z curve is not present in this NPZ\n"
            "This is expected for valid pre-filter/partial warmup rows.",
            ha="center",
            va="center",
            fontsize=13,
            transform=ax_mag.transAxes,
        )
        ax_components.axis("off")
        ax_mag.set_xticks([])
        ax_mag.set_yticks([])
    else:
        x, real, imag = beam1_z
        mag = np.hypot(real, imag)
        peak_idx = int(np.nanargmax(mag))
        hom_mask = x >= 550.0
        hom_idx = (
            int(np.where(hom_mask)[0][np.nanargmax(mag[hom_mask])])
            if np.any(hom_mask)
            else peak_idx
        )

        ax_mag.plot(x, mag, color="#1f77b4", linewidth=1.5, label="|Z|")
        ax_mag.axvline(
            550.0,
            color="#d62728",
            linestyle="--",
            linewidth=1.0,
            label="HOM lower bound 550 MHz",
        )
        ax_mag.scatter([x[peak_idx]], [mag[peak_idx]], color="#111111", s=28, zorder=5)
        ax_mag.scatter([x[hom_idx]], [mag[hom_idx]], color="#ff7f0e", s=28, zorder=5)
        ax_mag.annotate(
            f"global {x[peak_idx]:.3f}, {mag[peak_idx]:.1f} Ohm",
            xy=(x[peak_idx], mag[peak_idx]),
            xytext=(0.48, 0.78),
            textcoords="axes fraction",
            arrowprops={"arrowstyle": "->", "color": "#333333", "lw": 0.8},
            fontsize=8.5,
        )
        ax_mag.annotate(
            f"HOM {x[hom_idx]:.3f}, {mag[hom_idx]:.1f} Ohm",
            xy=(x[hom_idx], mag[hom_idx]),
            xytext=(0.63, 0.36),
            textcoords="axes fraction",
            arrowprops={"arrowstyle": "->", "color": "#333333", "lw": 0.8},
            fontsize=8.5,
        )
        ax_mag.set_ylabel("|Z| (Ohm)")
        ax_mag.grid(True, color="#d0d0d0", linewidth=0.8)
        ax_mag.legend(loc="upper right", fontsize=8.5)

        ax_components.plot(x, real, color="#2ca02c", linewidth=1.0, label="Re(Z)")
        ax_components.plot(x, imag, color="#9467bd", linewidth=1.0, label="Im(Z)")
        ax_components.axvline(550.0, color="#d62728", linestyle="--", linewidth=1.0)
        ax_components.axhline(0.0, color="#444444", linewidth=0.7)
        ax_components.set_xlabel("Frequency axis stored in NPZ (MHz-equivalent)")
        ax_components.set_ylabel("Z components (Ohm)")
        ax_components.grid(True, color="#d0d0d0", linewidth=0.8)
        ax_components.legend(loc="upper right", fontsize=8.5)
        ax_components.set_xlim(float(np.nanmin(x)), float(np.nanmax(x)))

    ax_text.text(
        0.0,
        1.0,
        _text_block(record, has_beam1_z),
        ha="left",
        va="top",
        family="monospace",
        fontsize=8.2,
        linespacing=1.22,
    )
    fig.text(
        0.055,
        0.035,
        f"Source bundle: {bundle_dir / str(record['npz_file'])}",
        fontsize=7.5,
        color="#555555",
    )
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return has_beam1_z


def _write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "file",
        "bundle_iter",
        "source_iter",
        "source_attempt",
        "source_npz",
        "bundle_npz",
        "scalar_penalty",
        "beam1_z_available",
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            values = [
                str(row.get("file", "")),
                str(row.get("bundle_iter", "")),
                str(row.get("source_iter", "")),
                str(row.get("source_attempt", "")),
                str(row.get("source_npz", "")),
                str(row.get("bundle_npz", "")),
                str(row.get("scalar_penalty", "")),
                str(row.get("beam1_z_available", "")),
            ]
            handle.write(",".join(value.replace(",", ";") for value in values) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create one Beam1 Z review plot per WF2 warmup-total sample.",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Results directory containing wf2_warmup_total (default: Results)",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=None,
        help="Optional explicit index.total.jsonl path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output folder for PNG plots",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete existing PNGs in the output folder before plotting",
    )
    args = parser.parse_args()

    results_dir = args.results.resolve()
    index_path = (
        args.index.resolve()
        if args.index is not None
        else results_dir / "wf2_warmup_total" / "index.total.jsonl"
    )
    bundle_dir = index_path.parent
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else results_dir / "plots" / "wf2_beam1_z_warmup_total"
    )

    if not index_path.is_file():
        raise FileNotFoundError(f"Warmup index not found: {index_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        for old_png in output_dir.glob("*.png"):
            old_png.unlink()
        for old_manifest in output_dir.glob("manifest.csv"):
            old_manifest.unlink()

    records = [
        record
        for record in _load_jsonl(index_path)
        if _is_valid_warmup_record(record, bundle_dir)
    ]
    if not records:
        raise RuntimeError(f"No valid warmup records found in {index_path}")

    manifest_rows: list[dict[str, Any]] = []
    available = 0
    for ordinal, record in enumerate(records, 1):
        bundle_iter = int(record["iter"])
        source_iter = record.get("source_iter", "unknown")
        source_attempt = record.get("source_attempt", "unknown")
        output_name = (
            f"{ordinal:03d}_bundle_{bundle_iter:04d}"
            f"_src_{source_iter}_a{source_attempt}_beam1_z.png"
        )
        output_path = output_dir / output_name
        has_curve = _plot_record(record, bundle_dir, output_path)
        available += int(has_curve)
        manifest_rows.append(
            {
                "file": output_name,
                "bundle_iter": bundle_iter,
                "source_iter": source_iter,
                "source_attempt": source_attempt,
                "source_npz": record.get("source_npz", ""),
                "bundle_npz": record.get("npz_file", ""),
                "scalar_penalty": record.get("scalar_penalty", ""),
                "beam1_z_available": has_curve,
            }
        )

    _write_manifest(output_dir / "manifest.csv", manifest_rows)
    print(f"Output folder: {output_dir}")
    print(f"Valid samples plotted: {len(records)}")
    print(f"Beam1 Z available: {available}")
    print(f"Beam1 Z missing/placeholder: {len(records) - available}")
    print(f"Manifest: {output_dir / 'manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
