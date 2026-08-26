"""Isolated CadQuery/OCP worker for RF-CEM parametric geometry.

CadQuery/OCP is intentionally imported only inside this worker process.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys


# Profile coordinates use millimetres. A 1e-3 mm (1 micrometre) fitting
# tolerance is negligible for the cavity scale while avoiding platform-specific
# failures seen with CadQuery's 1e-6 default variational smoothing.
_SPLINE_APPROX_TOLERANCE_MM = 1e-3
_SPLINE_INTERPOLATION_TOLERANCE_MM = 1e-6
_CONSTRAINED_SPLINE_REFERENCE_SAMPLES = 257
_SPLINE_FIDELITY_EVALUATION_SAMPLES = 513


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rf_cem.parametric_geometry.core.cadquery_worker")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        report = _recover(request)
        with args.output.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    except BaseException as exc:
        print(f"CadQuery parametric geometry worker failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.stderr.flush()
        os._exit(1)


def _recover(request: dict) -> dict:
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer

    output_step = Path(request["output_step"])
    output_step.parent.mkdir(parents=True, exist_ok=True)
    step_value = request.get("step_file")
    body_index = int(request.get("body_index") or 0)
    body = None
    solids: list[object] = []
    baseline = None
    if step_value:
        imported = cq.importers.importStep(str(Path(step_value))).val()
        solids = list(imported.Solids())
        body = solids[body_index] if solids else imported
        baseline = _metrics(body, BRepCheck_Analyzer)

    profile_points = [(float(z), float(r)) for z, r in request["profile_points"]]
    if len(profile_points) < 2:
        raise ValueError("profile_points must contain at least two points")
    profile_segments = request.get("profile_segments") or []
    generated_wp, curve_report = _build_generated_workplane(cq, profile_points, profile_segments)
    generated = generated_wp.val()
    cq.exporters.export(generated_wp, str(output_step))

    generated_metrics = _metrics(generated, BRepCheck_Analyzer)
    generated_vertices, generated_triangles = generated.tessellate(float(request.get("deflection_mm") or 0.25))
    if body is not None:
        tess_vertices, tess_triangles = body.tessellate(float(request.get("deflection_mm") or 0.25))
        envelope = _radial_envelope(tess_vertices)
        tessellation_source = "seed_step"
    else:
        tess_vertices, tess_triangles = generated_vertices, generated_triangles
        envelope = _radial_envelope(generated_vertices)
        tessellation_source = "generated"
    return {
        "schema_version": "cadquery_recovery_kernel.v0",
        "reader": {
            "backend": "cadquery_ocp_worker",
            "cadquery_version": cq.__version__,
            "notes": [
                "CadQuery/OCP ran in an isolated worker process.",
                "Generated STEP is rebuilt from parametric r-z profile segments.",
            ],
        },
        "body_selection": {
            "mode": "seed_step" if body is not None else "generated_without_seed",
            "body_index": body_index if body is not None else None,
            "solid_count": len(solids),
        },
        "baseline": baseline,
        "generated": generated_metrics,
        "generated_mesh": _mesh_payload(generated_vertices, generated_triangles),
        "tessellation": {
            "source": tessellation_source,
            "deflection_mm": float(request.get("deflection_mm") or 0.25),
            "vertex_count": len(tess_vertices),
            "triangle_count": len(tess_triangles),
            "radial_envelope_point_count": len(envelope),
        },
        "curve_generation": curve_report,
        "sections": _section_debug(profile_points, envelope),
        "output_step": str(output_step),
    }


def _build_generated_workplane(cq, profile_points: list[tuple[float, float]], profile_segments: list[dict]):
    if profile_segments:
        try:
            workplane, realized_segments = _workplane_from_segments(
                cq, profile_segments
            )
            return workplane, {
                "mode": "cadquery_curve_segments",
                "fallbacks": [],
                "approximations": _segment_approximation_reports(
                    profile_segments, realized_segments
                ),
                "realized_segments": realized_segments,
            }
        except Exception as exc:
            return _workplane_from_polyline(cq, profile_points), {
                "mode": "dense_polyline_fallback",
                "fallbacks": [f"curve segment construction failed: {type(exc).__name__}: {exc}"],
                "realized_segments": [],
            }
    return _workplane_from_polyline(cq, profile_points), {
        "mode": "legacy_profile_polyline",
        "fallbacks": [],
        "realized_segments": [],
    }


def _workplane_from_polyline(cq, profile_points: list[tuple[float, float]]):
    polyline = [(0.0, profile_points[0][0])]
    polyline.extend((r, z) for z, r in profile_points)
    polyline.append((0.0, profile_points[-1][0]))
    return cq.Workplane("XZ").polyline(polyline).close().revolve()


def _workplane_from_segments(cq, profile_segments: list[dict]):
    first = profile_segments[0]
    start = first["start"]
    wp = cq.Workplane("XZ").moveTo(0.0, float(start["z"])).lineTo(float(start["r"]), float(start["z"]))
    realized_segments = []
    for segment in profile_segments:
        kind = str(segment.get("kind"))
        end = segment["end"]
        curve = segment.get("curve", {})
        tangent_constraints = curve.get("endpoint_tangent_constraints")
        construction_contract = "cadquery.lineTo.v0"
        constraint_endpoints = {"start": False, "end": False}
        comparison_points: list[tuple[float, float]] = []
        comparison_source = "not_applicable"
        comparison_reference_edge = None
        fidelity_tolerance_mm = _SPLINE_APPROX_TOLERANCE_MM
        if kind == "arc":
            mid = curve.get("mid")
            if not mid:
                raise ValueError(f"arc segment {segment.get('id')} is missing curve.mid")
            wp = wp.threePointArc((float(mid["r"]), float(mid["z"])), (float(end["r"]), float(end["z"])))
            construction_contract = "cadquery.threePointArc.v0"
        elif kind == "nurbs":
            max_degree = int(curve.get("degree_max") or 3)
            if not 1 <= max_degree <= 5:
                raise ValueError(
                    f"nurbs segment {segment.get('id')} degree_max must be from 1 to 5"
                )
            tolerance_mm = float(
                curve.get("tolerance_mm", _SPLINE_APPROX_TOLERANCE_MM)
            )
            if not math.isfinite(tolerance_mm) or tolerance_mm <= 0.0:
                raise ValueError(
                    f"nurbs segment {segment.get('id')} tolerance_mm must be positive and finite"
                )
            if tangent_constraints:
                point_payload = curve.get("fit_input_points") or []
                source_points = [
                    (float(point["r"]), float(point["z"]))
                    for point in point_payload
                ]
                expected_start = (
                    float(segment["start"]["r"]),
                    float(segment["start"]["z"]),
                )
                if len(source_points) < 2 or not _same_point(
                    source_points[0], expected_start
                ):
                    raise ValueError(
                        f"constrained spline {segment.get('id')} must begin with its fit-input start"
                    )
                start_tangent = _workplane_tangent(
                    tangent_constraints.get("start_tangent_unit")
                )
                end_tangent = _workplane_tangent(
                    tangent_constraints.get("end_tangent_unit")
                )
                reference_edge = cq.Edge.makeSplineApprox(
                    [cq.Vector(r, 0.0, z) for r, z in source_points],
                    tol=tolerance_mm,
                    maxDeg=max_degree,
                )
                fractions = [
                    (1.0 - math.cos(math.pi * index / (
                        _CONSTRAINED_SPLINE_REFERENCE_SAMPLES - 1
                    )))
                    / 2.0
                    for index in range(_CONSTRAINED_SPLINE_REFERENCE_SAMPLES)
                ]
                reference_points = [
                    reference_edge.positionAt(fraction)
                    for fraction in fractions
                ]
                all_points = [
                    (float(point.x), float(point.z))
                    for point in reference_points
                ]
                all_points[0] = expected_start
                all_points[-1] = (
                    float(segment["end"]["r"]),
                    float(segment["end"]["z"]),
                )
                tangents = [None] * len(all_points)
                tangents[0] = start_tangent
                tangents[-1] = end_tangent
                if start_tangent is None and end_tangent is None:
                    raise ValueError(
                        f"constrained spline {segment.get('id')} has no endpoint direction"
                    )
                if tangent_constraints.get("constraint_kind") != "geometric_direction":
                    raise ValueError("unsupported spline tangent constraint kind")
                if tangent_constraints.get("scale_tangent") is not True:
                    raise ValueError("spline tangent direction must use scale=True")
                wp = wp.spline(
                    all_points[1:],
                    tangents=tangents,
                    scale=True,
                    tol=_SPLINE_INTERPOLATION_TOLERANCE_MM,
                    includeCurrent=True,
                )
                construction_contract = str(
                    curve.get("realized_backend_contract")
                    or "cadquery.spline.tangent_constrained.v0"
                )
                if construction_contract != "cadquery.spline.tangent_constrained.v0":
                    raise ValueError("unsupported constrained spline backend contract")
                constraint_endpoints = {
                    "start": start_tangent is not None,
                    "end": end_tangent is not None,
                }
                comparison_points = source_points
                comparison_source = str(
                    curve.get("comparison_source")
                    or (
                        "cadquery.splineApprox.v0 realization of "
                        "SplineApproxRepresentation.fit_input_points"
                    )
                )
                comparison_reference_edge = reference_edge
                fidelity_tolerance_mm = tolerance_mm
            else:
                sampled = curve.get("sampled_points") or []
                point_payload = sampled or curve.get("control_points", [])
                all_points = [
                    (float(point["r"]), float(point["z"]))
                    for point in point_payload
                ]
                points = list(all_points)
                if sampled and points and _same_point(
                    points[0],
                    (
                        float(segment["start"]["r"]),
                        float(segment["start"]["z"]),
                    ),
                ):
                    points = points[1:]
                if len(points) < 2:
                    raise ValueError(
                        f"nurbs segment {segment.get('id')} has fewer than two usable points"
                    )
                wp = wp.splineApprox(
                    points,
                    tol=tolerance_mm,
                    maxDeg=max_degree,
                    smoothing=None,
                    includeCurrent=True,
                )
                construction_contract = str(
                    curve.get("realized_backend_contract")
                    or "cadquery.splineApprox.v0"
                )
                comparison_points = all_points
                comparison_source = (
                    "sampled_points" if sampled else "control_points"
                )
                fidelity_tolerance_mm = tolerance_mm
        else:
            wp = wp.lineTo(float(end["r"]), float(end["z"]))
        realized_segments.append(
            _realized_segment_report(
                cq,
                wp.val(),
                segment,
                construction_contract=construction_contract,
                constraint_endpoints=constraint_endpoints,
                comparison_points=comparison_points,
                comparison_source=comparison_source,
                comparison_reference_edge=comparison_reference_edge,
                fidelity_tolerance_mm=fidelity_tolerance_mm,
            )
        )
    last = profile_segments[-1]["end"]
    return (
        wp.lineTo(0.0, float(last["z"])).close().revolve(),
        realized_segments,
    )


def _workplane_tangent(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("endpoint tangent must contain [dz, dr]")
    dz = float(value[0])
    dr = float(value[1])
    if not math.isfinite(dz) or not math.isfinite(dr):
        raise ValueError("endpoint tangent must be finite")
    if abs(math.hypot(dz, dr) - 1.0) > 1e-6:
        raise ValueError("endpoint tangent must be a unit vector")
    return (dr, dz)


def _realized_segment_report(
    cq,
    edge,
    segment: dict,
    *,
    construction_contract: str,
    constraint_endpoints: dict[str, bool],
    comparison_points: list[tuple[float, float]],
    comparison_source: str,
    comparison_reference_edge,
    fidelity_tolerance_mm: float,
) -> dict:
    start = edge.positionAt(0.0)
    end = edge.positionAt(1.0)
    start_tangent = edge.tangentAt(0.0)
    end_tangent = edge.tangentAt(1.0)
    expected_start = segment["start"]
    expected_end = segment["end"]
    if (
        math.hypot(
            float(start.z) - float(expected_start["z"]),
            float(start.x) - float(expected_start["r"]),
        )
        > 1e-6
        or math.hypot(
            float(end.z) - float(expected_end["z"]),
            float(end.x) - float(expected_end["r"]),
        )
        > 1e-6
    ):
        raise ValueError(
            f"realized segment {segment.get('id')} changed profile orientation or endpoints"
        )
    report = {
        "patch_id": str(segment.get("id")),
        "actual_start_point": {"z_mm": float(start.z), "r_mm": float(start.x)},
        "actual_end_point": {"z_mm": float(end.z), "r_mm": float(end.x)},
        "actual_start_tangent_unit": [
            float(start_tangent.z),
            float(start_tangent.x),
        ],
        "actual_end_tangent_unit": [
            float(end_tangent.z),
            float(end_tangent.x),
        ],
        "edge_kind": str(edge.geomType()).lower(),
        "orientation": "left_to_right",
        "construction_contract": construction_contract,
        "source_representation_contract": segment.get("curve", {}).get(
            "source_representation_contract"
        )
        or segment.get("curve", {}).get("backend_contract"),
        "tangent_constraints_applied": any(constraint_endpoints.values()),
        "applied_endpoint_constraints": dict(constraint_endpoints),
    }
    if comparison_points:
        source_trace_deviations = [
            edge.distance(cq.Vertex.makeVertex(r, 0.0, z))
            for r, z in comparison_points
        ]
        if comparison_reference_edge is None:
            maximum = max(float(value) for value in source_trace_deviations)
            sampling_policy = "all_backend_input_trace_points_projected_to_realized_edge"
            actual_to_reference = maximum
            reference_to_actual = maximum
        else:
            fractions = [
                index / (_SPLINE_FIDELITY_EVALUATION_SAMPLES - 1)
                for index in range(_SPLINE_FIDELITY_EVALUATION_SAMPLES)
            ]
            actual_samples = [edge.positionAt(fraction) for fraction in fractions]
            reference_samples = [
                comparison_reference_edge.positionAt(fraction)
                for fraction in fractions
            ]
            actual_to_reference = max(
                comparison_reference_edge.distance(
                    cq.Vertex.makeVertex(point.x, point.y, point.z)
                )
                for point in actual_samples
            )
            reference_to_actual = max(
                edge.distance(
                    cq.Vertex.makeVertex(point.x, point.y, point.z)
                )
                for point in reference_samples
            )
            maximum = max(actual_to_reference, reference_to_actual)
            sampling_policy = (
                "bidirectional_513_normalized_arc_length_edge_samples"
            )
        report["geometry_fidelity"] = {
            "maximum_deviation_mm": float(maximum),
            "actual_to_reference_max_deviation_mm": float(actual_to_reference),
            "reference_to_actual_max_deviation_mm": float(reference_to_actual),
            "source_trace_point_max_deviation_mm": max(
                float(value) for value in source_trace_deviations
            ),
            "sampling_policy": sampling_policy,
            "realization_input_sampling_policy": (
                "257_cosine_clustered_normalized_arc_length_samples"
                if comparison_reference_edge is not None
                else "backend_input_trace_points"
            ),
            "comparison_source": comparison_source,
            "sample_count": len(comparison_points),
            "tolerance_mm": fidelity_tolerance_mm,
            "pass": maximum <= fidelity_tolerance_mm,
        }
    return report


def _same_point(
    left: tuple[float, float],
    right: tuple[float, float],
    tolerance: float = 1e-12,
) -> bool:
    return abs(left[0] - right[0]) <= tolerance and abs(left[1] - right[1]) <= tolerance


def _segment_approximation_reports(
    profile_segments: list[dict], realized_segments: list[dict]
) -> list[dict]:
    reports = []
    realized_by_id = {
        str(item.get("patch_id")): item for item in realized_segments
    }
    for segment in profile_segments:
        if str(segment.get("kind")) != "nurbs":
            continue
        curve = segment.get("curve", {})
        sampled = curve.get("sampled_points") or []
        controls = curve.get("control_points") or []
        fit_inputs = curve.get("fit_input_points") or []
        constrained = bool(curve.get("endpoint_tangent_constraints"))
        realized = realized_by_id.get(str(segment.get("id")), {})
        reports.append(
            {
                "segment_id": str(segment.get("id", "")),
                "method": (
                    "cadquery.Workplane.spline"
                    if constrained
                    else "cadquery.Workplane.splineApprox"
                ),
                "input_source": (
                    "fit_input_points"
                    if constrained
                    else "sampled_points" if sampled else "control_points"
                ),
                "input_point_count": len(fit_inputs or sampled or controls),
                "max_degree": int(curve.get("degree_max") or 3),
                "tolerance_mm": float(
                    curve.get("tolerance_mm", _SPLINE_APPROX_TOLERANCE_MM)
                ),
                "smoothing": None,
                "source_representation_contract": curve.get(
                    "source_representation_contract"
                )
                or curve.get("backend_contract"),
                "realized_backend_contract": realized.get(
                    "construction_contract"
                ),
                "endpoint_tangent_constraints": curve.get(
                    "endpoint_tangent_constraints"
                ),
                "tangent_constraints_applied": realized.get(
                    "tangent_constraints_applied"
                ),
                "geometry_fidelity": realized.get("geometry_fidelity"),
                "fidelity": curve.get("fidelity"),
                "declared_source_curve": curve.get("source_curve"),
            }
        )
    return reports


def _metrics(shape, analyzer_cls) -> dict:
    bbox = shape.BoundingBox()
    analyzer = analyzer_cls(shape.wrapped, True)
    return {
        "bbox_mm": {
            "xmin": float(bbox.xmin),
            "xmax": float(bbox.xmax),
            "ymin": float(bbox.ymin),
            "ymax": float(bbox.ymax),
            "zmin": float(bbox.zmin),
            "zmax": float(bbox.zmax),
        },
        "volume_mm3": float(shape.Volume()),
        "surface_area_mm2": float(shape.Area()),
        "brep_valid": bool(analyzer.IsValid()),
    }


def _radial_envelope(vertices: list[object]) -> list[list[float]]:
    by_z: dict[float, float] = {}
    for vertex in vertices:
        z = round(float(vertex.z), 3)
        radius = math.hypot(float(vertex.x), float(vertex.y))
        if radius > by_z.get(z, -1.0):
            by_z[z] = radius
    return [[z, radius] for z, radius in sorted(by_z.items())]


def _mesh_payload(vertices: list[object], triangles: list[object]) -> dict:
    return {
        "vertices": [[float(vertex.x), float(vertex.y), float(vertex.z)] for vertex in vertices],
        "triangles": [[int(triangle[0]), int(triangle[1]), int(triangle[2])] for triangle in triangles],
    }


def _section_debug(profile_points: list[tuple[float, float]], envelope: list[list[float]]) -> list[dict]:
    sections = []
    for phi in (0, 45, 90, 135):
        sections.append(
            {
                "phi_deg": phi,
                "section_source": "grammar_profile_from_feature_manifest",
                "points": [[z, r] for z, r in profile_points],
                "curve_types": ["line", "arc", "nurbs"],
                "valid": True,
                "radial_envelope_reference_points": envelope[:20],
            }
        )
    return sections


if __name__ == "__main__":  # pragma: no cover
    main()
