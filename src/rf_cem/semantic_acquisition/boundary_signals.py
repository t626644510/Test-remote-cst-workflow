"""Region-free deterministic boundary signals for Semantic Acquisition A0."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.signal import find_peaks


BOUNDARY_SIGNAL_ALGORITHM_VERSION = "rf_cem.semantic_acquisition.boundary_signals.v0"
DEFAULT_SAMPLE_COUNTS = (512, 2048)
_POINT_TOLERANCE_MM = 1.0e-10
_UNIT_TOLERANCE = 1.0e-9


class BoundarySignalError(ValueError):
    """Raised when a numeric boundary signal input is invalid."""


@dataclass(frozen=True)
class BoundaryPoint:
    """One axisymmetric RF-vacuum profile point in millimetres."""

    z_mm: float
    r_mm: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.z_mm) or not math.isfinite(self.r_mm):
            raise BoundarySignalError("boundary points must be finite")

    def distance_to(self, other: "BoundaryPoint") -> float:
        """Return Euclidean profile-plane distance in millimetres."""

        return math.hypot(other.z_mm - self.z_mm, other.r_mm - self.r_mm)


@dataclass(frozen=True)
class BoundarySegment:
    """One geometry-only native curve trace with endpoint unit tangents."""

    points: tuple[BoundaryPoint, ...]
    start_tangent: tuple[float, float]
    end_tangent: tuple[float, float]

    def __post_init__(self) -> None:
        points = _deduplicate_points(self.points)
        if len(points) < 2 or _trace_length(points) <= _POINT_TOLERANCE_MM:
            raise BoundarySignalError("boundary segment must have non-zero length")
        _validate_unit_vector(self.start_tangent, "start_tangent")
        _validate_unit_vector(self.end_tangent, "end_tangent")


@dataclass(frozen=True)
class BoundaryJoin:
    """Numeric data for one original patch join, without semantic identifiers."""

    left_end: BoundaryPoint
    right_start: BoundaryPoint
    left_tangent: tuple[float, float]
    right_tangent: tuple[float, float]

    def __post_init__(self) -> None:
        _validate_unit_vector(self.left_tangent, "left_tangent")
        _validate_unit_vector(self.right_tangent, "right_tangent")


@dataclass(frozen=True)
class BoundaryTrace:
    """Complete ordered contour plus independently measured original joins."""

    segments: tuple[BoundarySegment, ...]
    joins: tuple[BoundaryJoin, ...] = ()

    def __post_init__(self) -> None:
        if not self.segments:
            raise BoundarySignalError("boundary trace requires at least one segment")


@dataclass(frozen=True)
class SignalParameters:
    """Finite thresholds for the A0 deterministic signal subset."""

    sample_counts: tuple[int, ...] = DEFAULT_SAMPLE_COUNTS
    merge_distance_u: float = 0.005
    stability_tolerance_u: float = 0.005
    radius_prominence_mm: float = 0.001
    curvature_prominence_per_mm: float = 0.002
    curvature_zero_per_mm: float = 0.0001
    c0_gap_threshold_mm: float = 1.0e-6
    g1_angle_threshold_deg: float = 2.0
    native_segment_min_samples: int = 9

    def __post_init__(self) -> None:
        if len(self.sample_counts) < 2 or len(set(self.sample_counts)) != len(
            self.sample_counts
        ):
            raise BoundarySignalError("at least two distinct sample counts are required")
        if any(count < 32 for count in self.sample_counts):
            raise BoundarySignalError("sample counts must be at least 32")
        for name in (
            "merge_distance_u",
            "stability_tolerance_u",
            "radius_prominence_mm",
            "curvature_prominence_per_mm",
            "curvature_zero_per_mm",
            "c0_gap_threshold_mm",
            "g1_angle_threshold_deg",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise BoundarySignalError(f"{name} must be finite and positive")
        if self.native_segment_min_samples < 3:
            raise BoundarySignalError("native_segment_min_samples must be at least three")

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical JSON-compatible threshold declaration."""

        return {
            "sample_counts": list(sorted(self.sample_counts)),
            "merge_distance_u": self.merge_distance_u,
            "stability_tolerance_u": self.stability_tolerance_u,
            "radius_prominence_mm": self.radius_prominence_mm,
            "curvature_prominence_per_mm": self.curvature_prominence_per_mm,
            "curvature_zero_per_mm": self.curvature_zero_per_mm,
            "c0_gap_threshold_mm": self.c0_gap_threshold_mm,
            "g1_angle_threshold_deg": self.g1_angle_threshold_deg,
            "native_segment_min_samples": self.native_segment_min_samples,
            "length_unit": "mm",
            "curvature_unit": "1/mm",
            "angle_unit": "deg",
        }


@dataclass(frozen=True)
class ScaleCandidate:
    """Signals merged at one sampling density."""

    sample_count: int
    u: float
    u_interval: tuple[float, float]
    signals: tuple[str, ...]


@dataclass(frozen=True)
class LandmarkCandidate:
    """One stable or unstable multi-scale landmark proposal."""

    u: float
    u_interval: tuple[float, float]
    signals: tuple[str, ...]
    scale_positions: tuple[tuple[int, float], ...]
    stable: bool

    def to_mapping(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible representation."""

        return {
            "u": self.u,
            "u_interval": list(self.u_interval),
            "signals": list(self.signals),
            "scale_positions": [
                {"sample_count": count, "u": position}
                for count, position in self.scale_positions
            ],
            "stable": self.stable,
        }


@dataclass(frozen=True)
class ContinuitySignalDiagnostic:
    """Independent numeric C0/G1 classification for one original join."""

    join_index: int
    u_by_scale: tuple[tuple[int, float], ...]
    gap_mm: float
    tangent_angle_deg: float
    c0_gap_detected: bool
    g1_jump_detected: bool


@dataclass(frozen=True)
class CandidateExtraction:
    """Stable candidates, unstable observations, and continuity diagnostics."""

    candidates: tuple[LandmarkCandidate, ...]
    unstable_candidates: tuple[LandmarkCandidate, ...]
    per_scale: tuple[tuple[int, tuple[ScaleCandidate, ...]], ...]
    continuity: tuple[ContinuitySignalDiagnostic, ...]


@dataclass(frozen=True)
class _SignalObservation:
    u: float
    signal: str


def extract_landmark_candidates(
    trace: BoundaryTrace, parameters: SignalParameters | None = None
) -> CandidateExtraction:
    """Extract the complete deterministic A0 signal subset at multiple scales."""

    params = parameters or SignalParameters()
    per_scale: list[tuple[int, tuple[ScaleCandidate, ...]]] = []
    continuity_by_scale: dict[int, tuple[ContinuitySignalDiagnostic, ...]] = {}
    for sample_count in sorted(params.sample_counts):
        points = resample_by_arc_length(
            trace,
            sample_count,
            native_segment_min_samples=params.native_segment_min_samples,
        )
        observations, diagnostics = _extract_at_scale(points, trace.joins, params)
        per_scale.append(
            (
                sample_count,
                _merge_scale_observations(
                    observations, sample_count, params.merge_distance_u
                ),
            )
        )
        continuity_by_scale[sample_count] = diagnostics

    candidates, unstable = _match_across_scales(
        tuple(per_scale),
        stability_tolerance_u=params.stability_tolerance_u,
        merge_distance_u=params.merge_distance_u,
    )
    continuity = _combine_continuity_diagnostics(continuity_by_scale)
    return CandidateExtraction(
        candidates=candidates,
        unstable_candidates=unstable,
        per_scale=tuple(per_scale),
        continuity=continuity,
    )


def resample_by_arc_length(
    trace: BoundaryTrace,
    sample_count: int,
    *,
    native_segment_min_samples: int = 9,
) -> tuple[BoundaryPoint, ...]:
    """Uniformly resample the complete contour without region information.

    This intentionally duplicates the small numerical idea behind
    ``observation.observer._resample_by_arc_length`` because that helper is
    private.  The duplicate is scoped to Semantic Acquisition until a public
    two-consumer contract is justified.
    """

    if sample_count < 3:
        raise BoundarySignalError("sample_count must be at least three")
    lengths = [_trace_length(_deduplicate_points(segment.points)) for segment in trace.segments]
    total = sum(lengths)
    if total <= _POINT_TOLERANCE_MM:
        raise BoundarySignalError("boundary trace has zero total length")
    dense: list[BoundaryPoint] = []
    for segment, length in zip(trace.segments, lengths):
        allocated = max(
            native_segment_min_samples,
            int(math.ceil((sample_count - 1) * length / total)) + 1,
        )
        sampled = _sample_smooth_segment(segment, allocated)
        if dense and dense[-1].distance_to(sampled[0]) <= _POINT_TOLERANCE_MM:
            dense.extend(sampled[1:])
        else:
            dense.extend(sampled)
    return _resample_polyline_by_arc_length(tuple(dense), sample_count)


def signed_curvature(
    points: Sequence[BoundaryPoint], index: int
) -> float:
    """Return signed three-point curvature in ``1/mm``.

    The formula is the local equivalent of the private R4 observer helper and
    is kept here rather than importing across that private boundary.
    """

    if index == 0 or index == len(points) - 1:
        return 0.0
    first, middle, last = points[index - 1], points[index], points[index + 1]
    first_length = first.distance_to(middle)
    second_length = middle.distance_to(last)
    diagonal = last.distance_to(first)
    denominator = first_length * second_length * diagonal
    if denominator <= _POINT_TOLERANCE_MM**3:
        return 0.0
    twice_signed_area = (
        (middle.z_mm - first.z_mm) * (last.r_mm - first.r_mm)
        - (middle.r_mm - first.r_mm) * (last.z_mm - first.z_mm)
    )
    return 2.0 * twice_signed_area / denominator


def _sample_smooth_segment(
    segment: BoundarySegment, sample_count: int
) -> tuple[BoundaryPoint, ...]:
    points = _deduplicate_points(segment.points)
    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + left.distance_to(right))
    total = cumulative[-1]
    targets = np.linspace(0.0, total, sample_count)
    coordinates = np.asarray([(point.z_mm, point.r_mm) for point in points], dtype=float)
    if len(points) == 2:
        z_values = np.interp(targets, cumulative, coordinates[:, 0])
        r_values = np.interp(targets, cumulative, coordinates[:, 1])
    else:
        z_spline = CubicSpline(
            cumulative,
            coordinates[:, 0],
            bc_type=((1, segment.start_tangent[0]), (1, segment.end_tangent[0])),
        )
        r_spline = CubicSpline(
            cumulative,
            coordinates[:, 1],
            bc_type=((1, segment.start_tangent[1]), (1, segment.end_tangent[1])),
        )
        z_values = z_spline(targets)
        r_values = r_spline(targets)
    result = tuple(
        BoundaryPoint(float(z_value), float(r_value))
        for z_value, r_value in zip(z_values, r_values)
    )
    return (points[0], *result[1:-1], points[-1])


def _resample_polyline_by_arc_length(
    points: tuple[BoundaryPoint, ...], sample_count: int
) -> tuple[BoundaryPoint, ...]:
    points = _deduplicate_points(points)
    lengths = [0.0]
    for left, right in zip(points, points[1:]):
        lengths.append(lengths[-1] + left.distance_to(right))
    total = lengths[-1]
    if total <= _POINT_TOLERANCE_MM:
        raise BoundarySignalError("curve total arc length must be positive")
    result: list[BoundaryPoint] = []
    segment_index = 0
    for index in range(sample_count):
        target = total * index / (sample_count - 1)
        while segment_index < len(lengths) - 2 and target > lengths[segment_index + 1]:
            segment_index += 1
        left_length = lengths[segment_index]
        right_length = lengths[segment_index + 1]
        width = right_length - left_length
        fraction = 0.0 if width <= _POINT_TOLERANCE_MM else (target - left_length) / width
        left = points[segment_index]
        right = points[segment_index + 1]
        result.append(
            BoundaryPoint(
                z_mm=left.z_mm + fraction * (right.z_mm - left.z_mm),
                r_mm=left.r_mm + fraction * (right.r_mm - left.r_mm),
            )
        )
    result[0] = points[0]
    result[-1] = points[-1]
    return tuple(result)


def _extract_at_scale(
    points: tuple[BoundaryPoint, ...],
    joins: tuple[BoundaryJoin, ...],
    parameters: SignalParameters,
) -> tuple[tuple[_SignalObservation, ...], tuple[ContinuitySignalDiagnostic, ...]]:
    count = len(points)
    u_values = np.linspace(0.0, 1.0, count)
    radius = np.asarray([point.r_mm for point in points], dtype=float)
    curvature = np.asarray(
        [signed_curvature(points, index) for index in range(count)], dtype=float
    )
    minimum_peak_distance = max(
        1, int(math.ceil(parameters.merge_distance_u * (count - 1)))
    )
    observations = [
        _SignalObservation(0.0, "profile_endpoint"),
        _SignalObservation(1.0, "profile_endpoint"),
    ]
    for index in find_peaks(
        radius,
        prominence=parameters.radius_prominence_mm,
        distance=minimum_peak_distance,
    )[0]:
        observations.append(
            _SignalObservation(float(u_values[index]), "radius_local_maximum")
        )
    for index in find_peaks(
        -radius,
        prominence=parameters.radius_prominence_mm,
        distance=minimum_peak_distance,
    )[0]:
        observations.append(
            _SignalObservation(float(u_values[index]), "radius_local_minimum")
        )
    for index in find_peaks(
        curvature,
        prominence=parameters.curvature_prominence_per_mm,
        distance=minimum_peak_distance,
    )[0]:
        observations.append(
            _SignalObservation(float(u_values[index]), "curvature_local_maximum")
        )
    for index in find_peaks(
        -curvature,
        prominence=parameters.curvature_prominence_per_mm,
        distance=minimum_peak_distance,
    )[0]:
        observations.append(
            _SignalObservation(float(u_values[index]), "curvature_local_minimum")
        )
    observations.extend(
        _curvature_zero_crossings(
            u_values, curvature, parameters.curvature_zero_per_mm
        )
    )
    observations.extend(_symmetry_crossings(u_values, points))

    diagnostics: list[ContinuitySignalDiagnostic] = []
    for join_index, join in enumerate(joins):
        gap_mm = join.left_end.distance_to(join.right_start)
        tangent_angle_deg = _tangent_angle_deg(
            join.left_tangent, join.right_tangent
        )
        join_point = BoundaryPoint(
            0.5 * (join.left_end.z_mm + join.right_start.z_mm),
            0.5 * (join.left_end.r_mm + join.right_start.r_mm),
        )
        join_u = _project_to_polyline_u(join_point, points)
        c0_detected = gap_mm > parameters.c0_gap_threshold_mm
        g1_detected = tangent_angle_deg > parameters.g1_angle_threshold_deg
        if c0_detected:
            observations.append(_SignalObservation(join_u, "c0_gap"))
        if g1_detected:
            observations.append(_SignalObservation(join_u, "g1_tangent_jump"))
        diagnostics.append(
            ContinuitySignalDiagnostic(
                join_index=join_index,
                u_by_scale=((count, join_u),),
                gap_mm=gap_mm,
                tangent_angle_deg=tangent_angle_deg,
                c0_gap_detected=c0_detected,
                g1_jump_detected=g1_detected,
            )
        )
    return tuple(observations), tuple(diagnostics)


def _curvature_zero_crossings(
    u_values: np.ndarray, curvature: np.ndarray, zero_threshold: float
) -> tuple[_SignalObservation, ...]:
    signs = np.sign(np.where(np.abs(curvature) >= zero_threshold, curvature, 0.0))
    nonzero = np.flatnonzero(signs)
    result: list[_SignalObservation] = []
    for left_index, right_index in zip(nonzero, nonzero[1:]):
        if signs[left_index] * signs[right_index] >= 0.0:
            continue
        left_value = abs(float(curvature[left_index]))
        right_value = abs(float(curvature[right_index]))
        fraction = left_value / (left_value + right_value)
        position = float(
            u_values[left_index]
            + fraction * (u_values[right_index] - u_values[left_index])
        )
        result.append(_SignalObservation(position, "curvature_zero_crossing"))
    return tuple(result)


def _symmetry_crossings(
    u_values: np.ndarray, points: tuple[BoundaryPoint, ...]
) -> tuple[_SignalObservation, ...]:
    result: list[_SignalObservation] = []
    for index, (left, right) in enumerate(zip(points, points[1:])):
        if abs(left.z_mm) <= _POINT_TOLERANCE_MM:
            result.append(_SignalObservation(float(u_values[index]), "symmetry_z0"))
        if left.z_mm * right.z_mm < 0.0:
            fraction = abs(left.z_mm) / (abs(left.z_mm) + abs(right.z_mm))
            position = float(
                u_values[index] + fraction * (u_values[index + 1] - u_values[index])
            )
            result.append(_SignalObservation(position, "symmetry_z0"))
    if abs(points[-1].z_mm) <= _POINT_TOLERANCE_MM:
        result.append(_SignalObservation(1.0, "symmetry_z0"))
    return tuple(result)


def _merge_scale_observations(
    observations: Iterable[_SignalObservation],
    sample_count: int,
    merge_distance_u: float,
) -> tuple[ScaleCandidate, ...]:
    ordered = sorted(observations, key=lambda item: (item.u, item.signal))
    if not ordered:
        return ()
    clusters: list[list[_SignalObservation]] = [[ordered[0]]]
    for observation in ordered[1:]:
        if observation.u - clusters[-1][-1].u < merge_distance_u:
            clusters[-1].append(observation)
        else:
            clusters.append([observation])
    return tuple(
        ScaleCandidate(
            sample_count=sample_count,
            u=sum(item.u for item in cluster) / len(cluster),
            u_interval=(min(item.u for item in cluster), max(item.u for item in cluster)),
            signals=tuple(sorted({item.signal for item in cluster})),
        )
        for cluster in clusters
    )


def _match_across_scales(
    per_scale: tuple[tuple[int, tuple[ScaleCandidate, ...]], ...],
    *,
    stability_tolerance_u: float,
    merge_distance_u: float,
) -> tuple[tuple[LandmarkCandidate, ...], tuple[LandmarkCandidate, ...]]:
    first_count, first_candidates = per_scale[0]
    used: dict[int, set[int]] = {count: set() for count, _ in per_scale}
    stable: list[LandmarkCandidate] = []
    unmatched: list[ScaleCandidate] = []
    for first_index, first in enumerate(first_candidates):
        matches = [(first_count, first)]
        for count, candidates in per_scale[1:]:
            choices = [
                (abs(candidate.u - first.u), index, candidate)
                for index, candidate in enumerate(candidates)
                if index not in used[count]
                and set(candidate.signals).intersection(first.signals)
                and abs(candidate.u - first.u) <= stability_tolerance_u
            ]
            if not choices:
                matches = []
                break
            _, selected_index, selected = min(
                choices, key=lambda item: (item[0], item[2].u, item[1])
            )
            matches.append((count, selected))
        if not matches:
            unmatched.append(first)
            continue
        used[first_count].add(first_index)
        for count, selected in matches[1:]:
            selected_index = per_scale[[item[0] for item in per_scale].index(count)][
                1
            ].index(selected)
            used[count].add(selected_index)
        positions = tuple((count, candidate.u) for count, candidate in matches)
        stable.append(
            LandmarkCandidate(
                u=sum(position for _, position in positions) / len(positions),
                u_interval=(
                    min(candidate.u_interval[0] for _, candidate in matches),
                    max(candidate.u_interval[1] for _, candidate in matches),
                ),
                signals=tuple(
                    sorted(
                        {
                            signal
                            for _, candidate in matches
                            for signal in candidate.signals
                        }
                    )
                ),
                scale_positions=positions,
                stable=True,
            )
        )
    for count, candidates in per_scale[1:]:
        unmatched.extend(
            candidate for index, candidate in enumerate(candidates) if index not in used[count]
        )
    unstable = tuple(
        LandmarkCandidate(
            u=candidate.u,
            u_interval=candidate.u_interval,
            signals=candidate.signals,
            scale_positions=((candidate.sample_count, candidate.u),),
            stable=False,
        )
        for candidate in sorted(unmatched, key=lambda item: (item.u, item.sample_count))
    )
    return _merge_stable_candidates(tuple(stable), merge_distance_u), unstable


def _merge_stable_candidates(
    candidates: tuple[LandmarkCandidate, ...], merge_distance_u: float
) -> tuple[LandmarkCandidate, ...]:
    ordered = sorted(candidates, key=lambda item: item.u)
    if not ordered:
        return ()
    clusters: list[list[LandmarkCandidate]] = [[ordered[0]]]
    for candidate in ordered[1:]:
        if candidate.u - clusters[-1][-1].u < merge_distance_u:
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])
    result = []
    for cluster in clusters:
        scale_positions = tuple(
            sorted(
                {
                    (count, position)
                    for candidate in cluster
                    for count, position in candidate.scale_positions
                }
            )
        )
        result.append(
            LandmarkCandidate(
                u=sum(position for _, position in scale_positions) / len(scale_positions),
                u_interval=(
                    min(candidate.u_interval[0] for candidate in cluster),
                    max(candidate.u_interval[1] for candidate in cluster),
                ),
                signals=tuple(
                    sorted(
                        {
                            signal
                            for candidate in cluster
                            for signal in candidate.signals
                        }
                    )
                ),
                scale_positions=scale_positions,
                stable=True,
            )
        )
    return tuple(result)


def _combine_continuity_diagnostics(
    by_scale: dict[int, tuple[ContinuitySignalDiagnostic, ...]]
) -> tuple[ContinuitySignalDiagnostic, ...]:
    counts = sorted(by_scale)
    if not counts or not by_scale[counts[0]]:
        return ()
    expected = len(by_scale[counts[0]])
    if any(len(by_scale[count]) != expected for count in counts):
        raise BoundarySignalError("continuity join count changed across scales")
    result = []
    for index in range(expected):
        items = [by_scale[count][index] for count in counts]
        first = items[0]
        if any(
            abs(item.gap_mm - first.gap_mm) > _POINT_TOLERANCE_MM
            or abs(item.tangent_angle_deg - first.tangent_angle_deg) > _UNIT_TOLERANCE
            for item in items[1:]
        ):
            raise BoundarySignalError("continuity measurements changed across scales")
        result.append(
            ContinuitySignalDiagnostic(
                join_index=index,
                u_by_scale=tuple(
                    (count, by_scale[count][index].u_by_scale[0][1]) for count in counts
                ),
                gap_mm=first.gap_mm,
                tangent_angle_deg=first.tangent_angle_deg,
                c0_gap_detected=first.c0_gap_detected,
                g1_jump_detected=first.g1_jump_detected,
            )
        )
    return tuple(result)


def _project_to_polyline_u(
    target: BoundaryPoint, points: Sequence[BoundaryPoint]
) -> float:
    lengths = [0.0]
    for left, right in zip(points, points[1:]):
        lengths.append(lengths[-1] + left.distance_to(right))
    best_distance = math.inf
    best_s = 0.0
    for index, (left, right) in enumerate(zip(points, points[1:])):
        dz = right.z_mm - left.z_mm
        dr = right.r_mm - left.r_mm
        denominator = dz * dz + dr * dr
        fraction = 0.0
        if denominator > _POINT_TOLERANCE_MM**2:
            fraction = max(
                0.0,
                min(
                    1.0,
                    ((target.z_mm - left.z_mm) * dz + (target.r_mm - left.r_mm) * dr)
                    / denominator,
                ),
            )
        projected = BoundaryPoint(
            left.z_mm + fraction * dz, left.r_mm + fraction * dr
        )
        distance = target.distance_to(projected)
        if distance < best_distance:
            best_distance = distance
            best_s = lengths[index] + fraction * math.sqrt(denominator)
    return best_s / lengths[-1]


def _tangent_angle_deg(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    dot = max(-1.0, min(1.0, left[0] * right[0] + left[1] * right[1]))
    return math.degrees(math.acos(dot))


def _deduplicate_points(
    points: Sequence[BoundaryPoint],
) -> tuple[BoundaryPoint, ...]:
    result: list[BoundaryPoint] = []
    for point in points:
        if not isinstance(point, BoundaryPoint):
            raise BoundarySignalError("boundary traces require BoundaryPoint values")
        if not result or result[-1].distance_to(point) > _POINT_TOLERANCE_MM:
            result.append(point)
    return tuple(result)


def _trace_length(points: Sequence[BoundaryPoint]) -> float:
    return sum(left.distance_to(right) for left, right in zip(points, points[1:]))


def _validate_unit_vector(value: tuple[float, float], label: str) -> None:
    if len(value) != 2 or any(not math.isfinite(item) for item in value):
        raise BoundarySignalError(f"{label} must be a finite 2-vector")
    if abs(math.hypot(*value) - 1.0) > _UNIT_TOLERANCE:
        raise BoundarySignalError(f"{label} must be a unit vector")


__all__ = [
    "BOUNDARY_SIGNAL_ALGORITHM_VERSION",
    "DEFAULT_SAMPLE_COUNTS",
    "BoundaryJoin",
    "BoundaryPoint",
    "BoundarySegment",
    "BoundarySignalError",
    "BoundaryTrace",
    "CandidateExtraction",
    "ContinuitySignalDiagnostic",
    "LandmarkCandidate",
    "ScaleCandidate",
    "SignalParameters",
    "extract_landmark_candidates",
    "resample_by_arc_length",
    "signed_curvature",
]
