"""Measurement input validation, clustering, and safe solver-window planning."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .models import SolverWindow, TargetCluster, TargetRecord

REQUIRED_COLUMNS = (
    "condition",
    "freq_hz",
    "freq_ghz",
    "q",
    "residual_prominence_db",
    "raw_peak_db",
    "baseline_db",
    "bandwidth_hz",
    "rank_source",
    "propagation_background",
    "suggested_span_mhz",
)


def _parse_finite(row: dict[str, str], name: str, row_number: int) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: invalid numeric field {name!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"row {row_number}: {name!r} must be finite")
    return value


def _parse_bool(value: str, row_number: int) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(
        f"row {row_number}: propagation_background must be true or false"
    )


def _source_row_id(row: dict[str, str]) -> str:
    canonical = json.dumps(
        {key: row.get(key, "").strip() for key in REQUIRED_COLUMNS},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"SRC_{digest}"


def load_target_records(path: str | Path) -> list[TargetRecord]:
    """Load and strictly validate the suspicious-HOM measurement CSV."""

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing required CSV columns: {', '.join(missing)}")

        records: list[TargetRecord] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            condition = row["condition"].strip()
            rank_source = row["rank_source"].strip()
            if not condition:
                raise ValueError(f"row {row_number}: condition must not be empty")
            if not rank_source:
                raise ValueError(f"row {row_number}: rank_source must not be empty")

            freq_hz = _parse_finite(row, "freq_hz", row_number)
            freq_ghz = _parse_finite(row, "freq_ghz", row_number)
            q_value = _parse_finite(row, "q", row_number)
            bandwidth_hz = _parse_finite(row, "bandwidth_hz", row_number)
            suggested_span_mhz = _parse_finite(
                row, "suggested_span_mhz", row_number
            )
            if min(freq_hz, freq_ghz, q_value, bandwidth_hz, suggested_span_mhz) <= 0:
                raise ValueError(
                    f"row {row_number}: frequencies, q, bandwidth, and span must be positive"
                )
            expected_hz = freq_ghz * 1e9
            tolerance_hz = max(1.0, abs(freq_hz) * 1e-9)
            if abs(freq_hz - expected_hz) > tolerance_hz:
                raise ValueError(
                    f"row {row_number}: freq_hz and freq_ghz disagree "
                    f"({freq_hz} vs {expected_hz})"
                )

            source_id = _source_row_id(row)
            if source_id in seen_ids:
                raise ValueError(
                    f"row {row_number}: duplicate input row content ({source_id})"
                )
            seen_ids.add(source_id)
            records.append(
                TargetRecord(
                    source_row_id=source_id,
                    source_row_number=row_number,
                    condition=condition,
                    freq_hz=freq_hz,
                    freq_ghz=freq_ghz,
                    q_measurement=q_value,
                    residual_prominence_db=_parse_finite(
                        row, "residual_prominence_db", row_number
                    ),
                    raw_peak_db=_parse_finite(row, "raw_peak_db", row_number),
                    baseline_db=_parse_finite(row, "baseline_db", row_number),
                    bandwidth_hz=bandwidth_hz,
                    rank_source=rank_source,
                    propagation_background=_parse_bool(
                        row["propagation_background"], row_number
                    ),
                    suggested_span_mhz=suggested_span_mhz,
                )
            )
    return records


def records_are_compatible(a: TargetRecord, b: TargetRecord) -> bool:
    """Return whether two different-condition measurements may share a cluster."""

    if a.condition == b.condition:
        return False
    midpoint_hz = 0.5 * (a.freq_hz + b.freq_hz)
    threshold_hz = max(
        a.suggested_span_mhz * 1e6,
        b.suggested_span_mhz * 1e6,
        0.005 * midpoint_hz,
    )
    return abs(a.freq_hz - b.freq_hz) <= threshold_hz


def _clusters_can_merge(
    left: tuple[TargetRecord, ...],
    right: tuple[TargetRecord, ...],
) -> bool:
    conditions = [record.condition for record in (*left, *right)]
    if len(conditions) != len(set(conditions)):
        return False
    return all(records_are_compatible(a, b) for a in left for b in right)


def _cluster_distance(
    left: tuple[TargetRecord, ...],
    right: tuple[TargetRecord, ...],
) -> float:
    return abs(
        statistics.median(record.freq_hz for record in left)
        - statistics.median(record.freq_hz for record in right)
    )


def cluster_targets(records: Iterable[TargetRecord]) -> list[TargetCluster]:
    """Complete-link agglomerative clustering with condition uniqueness."""

    groups: list[tuple[TargetRecord, ...]] = [
        (record,) for record in sorted(records, key=lambda item: item.freq_hz)
    ]
    while True:
        candidates: list[tuple[float, int, int]] = []
        for left_index in range(len(groups)):
            for right_index in range(left_index + 1, len(groups)):
                if _clusters_can_merge(groups[left_index], groups[right_index]):
                    candidates.append(
                        (
                            _cluster_distance(
                                groups[left_index], groups[right_index]
                            ),
                            left_index,
                            right_index,
                        )
                    )
        if not candidates:
            break
        _, left_index, right_index = min(candidates)
        merged = tuple(
            sorted(
                (*groups[left_index], *groups[right_index]),
                key=lambda item: (item.freq_hz, item.condition),
            )
        )
        groups[left_index] = merged
        del groups[right_index]

    groups.sort(key=lambda group: statistics.median(r.freq_hz for r in group))
    clusters: list[TargetCluster] = []
    for index, group in enumerate(groups, start=1):
        frequencies = [record.freq_hz for record in group]
        max_span_mhz = max(record.suggested_span_mhz for record in group)
        clusters.append(
            TargetCluster(
                target_cluster_id=f"TC_{index:04d}",
                records=group,
                target_freq_hz=float(statistics.median(frequencies)),
                freq_min_hz=min(frequencies),
                freq_max_hz=max(frequencies),
                suggested_span_max_mhz=max_span_mhz,
                required_min_hz=min(frequencies) - max_span_mhz * 1e6,
                required_max_hz=max(frequencies) + max_span_mhz * 1e6,
                propagation_background=any(
                    record.propagation_background for record in group
                ),
            )
        )
    return clusters


def _split_oversized_cluster(
    cluster: TargetCluster,
    usable_width_hz: float,
    overlap_hz: float,
) -> list[tuple[tuple[str, ...], float, float, str]]:
    """Split one required interval into overlapping coverage segments."""

    low = cluster.required_min_hz
    high = cluster.required_max_hz
    if high - low <= usable_width_hz:
        return [((cluster.target_cluster_id,), low, high, "initial")]

    stride_hz = usable_width_hz - overlap_hz
    if stride_hz <= 0:
        raise ValueError("split overlap must be smaller than usable width")
    segments: list[tuple[tuple[str, ...], float, float, str]] = []
    segment_low = low
    while segment_low + usable_width_hz < high:
        segments.append(
            (
                (cluster.target_cluster_id,),
                segment_low,
                segment_low + usable_width_hz,
                "split",
            )
        )
        segment_low += stride_hz
    final_low = max(low, high - usable_width_hz)
    final = (
        (cluster.target_cluster_id,),
        final_low,
        high,
        "split",
    )
    if (
        not segments
        or abs(final_low - segments[-1][1]) > 1.0
        or abs(high - segments[-1][2]) > 1.0
    ):
        segments.append(final)
    return segments


def build_solver_windows(
    clusters: Iterable[TargetCluster],
    *,
    search_half_width_mhz: float = 10.0,
    guard_mhz: float = 1.0,
    max_clusters_per_window: int = 3,
    split_overlap_mhz: float = 2.0,
) -> list[SolverWindow]:
    """Greedily merge clusters that fit safely inside a fixed CST window."""

    if search_half_width_mhz <= guard_mhz:
        raise ValueError("search half width must be larger than guard")
    usable_width_hz = 2.0 * (search_half_width_mhz - guard_mhz) * 1e6
    overlap_hz = split_overlap_mhz * 1e6
    sorted_clusters = sorted(clusters, key=lambda item: item.required_min_hz)

    atomic: list[tuple[tuple[str, ...], float, float, str]] = []
    normal: list[TargetCluster] = []
    for cluster in sorted_clusters:
        if cluster.required_max_hz - cluster.required_min_hz > usable_width_hz:
            atomic.extend(
                _split_oversized_cluster(cluster, usable_width_hz, overlap_hz)
            )
        else:
            normal.append(cluster)

    index = 0
    while index < len(normal):
        group = [normal[index]]
        coverage_low = normal[index].required_min_hz
        coverage_high = normal[index].required_max_hz
        next_index = index + 1
        while next_index < len(normal) and len(group) < max_clusters_per_window:
            candidate = normal[next_index]
            merged_low = min(coverage_low, candidate.required_min_hz)
            merged_high = max(coverage_high, candidate.required_max_hz)
            if merged_high - merged_low > usable_width_hz:
                break
            group.append(candidate)
            coverage_low = merged_low
            coverage_high = merged_high
            next_index += 1
        atomic.append(
            (
                tuple(item.target_cluster_id for item in group),
                coverage_low,
                coverage_high,
                "initial",
            )
        )
        index = next_index

    atomic.sort(key=lambda item: (item[1], item[2], item[0]))
    windows: list[SolverWindow] = []
    half_width_hz = search_half_width_mhz * 1e6
    for index, (cluster_ids, low, high, kind) in enumerate(atomic, start=1):
        center_hz = 0.5 * (low + high)
        windows.append(
            SolverWindow(
                solver_window_id=f"WIN_{index:04d}",
                cluster_ids=cluster_ids,
                f_hom_mhz=center_hz / 1e6,
                search_min_hz=center_hz - half_width_hz,
                search_max_hz=center_hz + half_width_hz,
                coverage_min_hz=low,
                coverage_max_hz=high,
                kind=kind,
            )
        )
    return windows


def saturation_followups(
    window: SolverWindow,
    clusters_by_id: dict[str, TargetCluster],
    *,
    search_half_width_mhz: float = 10.0,
    probe_offset_mhz: float = 5.0,
) -> tuple[list[SolverWindow], str | None]:
    """Create deterministic follow-up windows after a three-mode saturation."""

    half_width_hz = search_half_width_mhz * 1e6
    if len(window.cluster_ids) > 1:
        followups: list[SolverWindow] = []
        for index, cluster_id in enumerate(window.cluster_ids, start=1):
            cluster = clusters_by_id[cluster_id]
            center_hz = cluster.target_freq_hz
            followups.append(
                SolverWindow(
                    solver_window_id=f"{window.solver_window_id}_C{index}",
                    cluster_ids=(cluster_id,),
                    f_hom_mhz=center_hz / 1e6,
                    search_min_hz=center_hz - half_width_hz,
                    search_max_hz=center_hz + half_width_hz,
                    coverage_min_hz=cluster.required_min_hz,
                    coverage_max_hz=cluster.required_max_hz,
                    kind="saturation_split",
                    parent_window_id=window.solver_window_id,
                )
            )
        return followups, None

    if window.kind == "saturation_probe":
        return [], "mode_enumeration_incomplete"

    followups = []
    for suffix, offset_mhz in (("M", -probe_offset_mhz), ("P", probe_offset_mhz)):
        center_mhz = window.f_hom_mhz + offset_mhz
        center_hz = center_mhz * 1e6
        followups.append(
            replace(
                window,
                solver_window_id=f"{window.solver_window_id}_{suffix}5",
                f_hom_mhz=center_mhz,
                search_min_hz=center_hz - half_width_hz,
                search_max_hz=center_hz + half_width_hz,
                kind="saturation_probe",
                parent_window_id=window.solver_window_id,
                probe_offset_mhz=offset_mhz,
            )
        )
    return followups, None
