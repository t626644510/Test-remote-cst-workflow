"""Human-readable, offline reports of existing WF5 mode evidence.

This module only reads archived analysis and writes report products. Frequencies
are converted from Hz to MHz; circuit R/Q stays in ohm/m and loaded impedance is
converted from ohm/m to kiloohm/m. It never recomputes or validates CST results.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping


CSV_FIELDS = (
    "evaluation_id", "evaluation_status", "mode", "frequency_mhz", "total_q",
    "rq_principal_ohm_per_m", "zx_kohm_per_m", "zy_kohm_per_m", "zmax_kohm_per_m",
    "principal_angle_deg", "quality_status", "threshold_status", "quality_reasons",
    "threshold_kohm_per_m", "analysis_path", "raw_evidence_path",
)


def diagnostic_summary(error: str) -> str:
    """Summarize structured quality failures; raw evidence remains in state.json."""
    try:
        payload = json.loads(error)
    except (TypeError, ValueError):
        return str(error)
    if not isinstance(payload, dict) or not isinstance(payload.get("modes"), list):
        return str(error)
    reasons = _reasons(payload.get("quality_reasons"))
    for mode in payload["modes"]:
        reasons += _reasons(mode.get("quality_reasons"), (mode.get("metrics") or {}).get("quality_reasons"))
    return "Quality check failed: " + "; ".join(dict.fromkeys(reasons)) + ". Full evidence: state.json and the mode table below."


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _read_analysis(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("modes"), list) else None


def _analysis(record: Mapping[str, Any]) -> tuple[dict[str, Any] | None, Path | None]:
    """Prefer committed metrics; locate their matching raw bundle when available."""
    inline = record.get("modes")
    inline = inline if isinstance(inline, dict) and isinstance(inline.get("modes"), list) else None
    # In-memory dataclasses contain tuples; archived JSON has equivalent lists.
    comparable = json.loads(json.dumps(inline)) if inline is not None else None
    attempt = record.get("attempt_dir")
    paths = sorted(Path(attempt).glob("attempt_*/postprocess_*/analysis.json"), reverse=True) if attempt else []
    if attempt:
        paths += sorted(Path(attempt).glob("attempt_*/latest_analysis.json"), reverse=True)
    for path in paths:
        saved = _read_analysis(path)
        if saved is not None and (inline is None or saved == comparable):
            return inline or saved, path
    return inline, None


def _reasons(*sources: Any) -> list[str]:
    values: list[str] = []
    for source in sources:
        if isinstance(source, str):
            source = [source]
        if isinstance(source, (list, tuple)):
            values.extend(str(value) for value in source if value)
    return list(dict.fromkeys(values))


def _text(value: Any) -> str:
    """Keep arbitrary reasons and paths inside one Markdown table cell."""
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def mode_report_lines(
    root: Path, report: Mapping[str, Any], state: Mapping[str, Any],
    band_mhz: tuple[float, float],
) -> list[str]:
    """Write modes.csv and return the report.md mode section.

    Best valid evaluation wins. Without one, the newest available failed/pending
    evaluation becomes diagnostics only: no numerical value can make it pass.
    Missing/nonfinite numbers stay blank in CSV and appear as em dashes in the
    Markdown table. Existing raw evidence is read but never edited.
    """
    best = report.get("best")
    chosen: Mapping[str, Any] | None = best
    data, analysis_path = _analysis(best) if best else (None, None)
    if best is None:
        candidates = ([state["pending"]] if state.get("pending") else []) + list(reversed(state.get("records", [])))
        for candidate in candidates:
            candidate_data, candidate_path = _analysis(candidate)
            if candidate_data is not None and candidate_data.get("modes"):
                chosen, data, analysis_path = candidate, candidate_data, candidate_path
                break
    threshold = float(report["threshold_ohm_per_m"]) / 1000
    rows: list[dict[str, Any]] = []
    for mode in (data or {}).get("modes", []):
        if best is not None and (data or {}).get("mode_policy") == "largest_two" and mode.get("mode_number") not in data.get("objective_mode_numbers", []):
            continue
        frequency = _finite(mode.get("frequency_hz"))
        if frequency is not None and not band_mhz[0] * 1e6 <= frequency <= band_mhz[1] * 1e6:
            continue
        metrics = mode.get("metrics") or {}
        reasons = _reasons((data or {}).get("quality_reasons"), mode.get("quality_reasons"), metrics.get("quality_reasons"))
        values = dict(
            frequency_mhz=frequency / 1e6 if frequency is not None else None,
            total_q=_finite(mode.get("q_loaded")),
            rq_principal_ohm_per_m=_finite(metrics.get("rq_principal_ohm_per_m")),
            principal_angle_deg=_finite(metrics.get("principal_angle_deg")),
        )
        for label, key in (("zx", "x"), ("zy", "y"), ("zmax", "principal")):
            impedance = _finite(metrics.get(f"impedance_{key}_ohm_per_m"))
            values[f"{label}_kohm_per_m"] = impedance / 1000 if impedance is not None else None
        complete = all(values[key] is not None for key in (
            "frequency_mhz", "total_q", "rq_principal_ohm_per_m",
            "zx_kohm_per_m", "zy_kohm_per_m", "zmax_kohm_per_m",
        ))
        physical = complete and values["frequency_mhz"] > 0 and values["total_q"] > 0 and all(
            values[key] >= 0 for key in ("rq_principal_ohm_per_m", "zx_kohm_per_m", "zy_kohm_per_m", "zmax_kohm_per_m"))
        quality_ok = (best is not None and chosen.get("status") == "valid" and
            (data or {}).get("quality_ok") is True and mode.get("quality_ok") is True and
            metrics.get("quality_ok") is True and not reasons and physical)
        if not complete:
            reasons.append("missing_or_nonfinite_metrics")
        elif not physical:
            reasons.append("nonphysical_metrics")
        if best is None:
            reasons.append("evaluation_not_valid")
        if not quality_ok and not reasons:
            reasons.append("quality_not_confirmed")
        raw_path = str(chosen.get("attempt_dir", "")) if chosen else ""
        if analysis_path:
            field_dir = analysis_path.parent / "fields" / f"mode_{mode.get('mode_number', '')}"
            if field_dir.is_dir():
                raw_path = str(field_dir)
        rows.append(dict(
            evaluation_id=chosen.get("id", "") if chosen else "",
            evaluation_status=chosen.get("status", "pending") if chosen else "",
            mode=mode.get("mode_number"), **values,
            quality_status="valid" if quality_ok else "invalid_or_unverified",
            threshold_status=("meets_threshold" if values["zmax_kohm_per_m"] <= threshold else "above_threshold") if quality_ok else "undetermined",
            quality_reasons="; ".join(dict.fromkeys(reasons)), threshold_kohm_per_m=threshold,
            analysis_path=str(analysis_path) if analysis_path else "", raw_evidence_path=raw_path,
        ))
    rows.sort(key=lambda row: (row["frequency_mhz"] if row["frequency_mhz"] is not None else math.inf, str(row["mode"])))
    with (Path(root) / "modes.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    lines = ["", "## Window mode impedances", "",
        f"Window: {band_mhz[0]:g}–{band_mhz[1]:g} MHz; configured threshold: {threshold:g} kΩ/m per mode.",
        "R/Qmax and Zmax use the strongest real transverse polarization; peak fields, β=1, circuit convention."]
    if best is None:
        lines += ["", "**Diagnostic only — no valid evaluation is available; threshold compliance is undetermined.**"]
    elif chosen:
        lines += ["", f"Best valid evaluation: {_text(chosen.get('id'))}."]
    if chosen:
        lines += [f"Source evaluation status: {_text(chosen.get('status', 'pending'))}.",
                  f"Raw evidence directory: {_text(chosen.get('attempt_dir'))}"]
    if analysis_path:
        lines += [f"Source analysis: {_text(analysis_path)}"]
    if not rows:
        if best is not None and (data or {}).get("empty_band") and (data or {}).get("coverage_complete"):
            lines += ["", "No modes in the window; the saved evaluation explicitly records complete coverage and an empty band."]
        else:
            lines += ["", "No window mode metrics are available. Missing values are not zero and do not establish threshold compliance."]
        return lines
    lines += ["", "Unavailable values are shown as — (blank in modes.csv); diagnostic values are not acceptance results.", "",
        "| Mode | Frequency (MHz) | Total-Q | R/Qmax (Ω/m) | Zx (kΩ/m) | Zy (kΩ/m) | Zmax (kΩ/m) | Angle (deg) | Quality | Threshold | Reasons |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    columns = ("mode", "frequency_mhz", "total_q", "rq_principal_ohm_per_m", "zx_kohm_per_m", "zy_kohm_per_m", "zmax_kohm_per_m", "principal_angle_deg", "quality_status", "threshold_status", "quality_reasons")
    lines += ["| " + " | ".join(_text(row[key]) for key in columns) + " |" for row in rows]
    return lines
