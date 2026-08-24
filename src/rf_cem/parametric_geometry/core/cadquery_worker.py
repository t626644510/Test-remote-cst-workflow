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
            return _workplane_from_segments(cq, profile_segments), {
                "mode": "cadquery_curve_segments",
                "fallbacks": [],
                "approximations": _segment_approximation_reports(profile_segments),
            }
        except Exception as exc:
            return _workplane_from_polyline(cq, profile_points), {
                "mode": "dense_polyline_fallback",
                "fallbacks": [f"curve segment construction failed: {type(exc).__name__}: {exc}"],
            }
    return _workplane_from_polyline(cq, profile_points), {"mode": "legacy_profile_polyline", "fallbacks": []}


def _workplane_from_polyline(cq, profile_points: list[tuple[float, float]]):
    polyline = [(0.0, profile_points[0][0])]
    polyline.extend((r, z) for z, r in profile_points)
    polyline.append((0.0, profile_points[-1][0]))
    return cq.Workplane("XZ").polyline(polyline).close().revolve()


def _workplane_from_segments(cq, profile_segments: list[dict]):
    first = profile_segments[0]
    start = first["start"]
    wp = cq.Workplane("XZ").moveTo(0.0, float(start["z"])).lineTo(float(start["r"]), float(start["z"]))
    for segment in profile_segments:
        kind = str(segment.get("kind"))
        end = segment["end"]
        if kind == "arc":
            mid = segment.get("curve", {}).get("mid")
            if not mid:
                raise ValueError(f"arc segment {segment.get('id')} is missing curve.mid")
            wp = wp.threePointArc((float(mid["r"]), float(mid["z"])), (float(end["r"]), float(end["z"])))
        elif kind == "nurbs":
            curve = segment.get("curve", {})
            sampled = curve.get("sampled_points") or []
            point_payload = sampled or curve.get("control_points", [])
            points = [(float(point["r"]), float(point["z"])) for point in point_payload]
            if sampled and points and _same_point(points[0], (float(segment["start"]["r"]), float(segment["start"]["z"]))):
                points = points[1:]
            if len(points) < 2:
                raise ValueError(f"nurbs segment {segment.get('id')} has fewer than two usable points")
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
            wp = wp.splineApprox(
                points,
                tol=tolerance_mm,
                maxDeg=max_degree,
                smoothing=None,
                includeCurrent=True,
            )
        else:
            wp = wp.lineTo(float(end["r"]), float(end["z"]))
    last = profile_segments[-1]["end"]
    return wp.lineTo(0.0, float(last["z"])).close().revolve()


def _same_point(
    left: tuple[float, float],
    right: tuple[float, float],
    tolerance: float = 1e-12,
) -> bool:
    return abs(left[0] - right[0]) <= tolerance and abs(left[1] - right[1]) <= tolerance


def _segment_approximation_reports(profile_segments: list[dict]) -> list[dict]:
    reports = []
    for segment in profile_segments:
        if str(segment.get("kind")) != "nurbs":
            continue
        curve = segment.get("curve", {})
        sampled = curve.get("sampled_points") or []
        controls = curve.get("control_points") or []
        reports.append(
            {
                "segment_id": str(segment.get("id", "")),
                "method": "cadquery.Workplane.splineApprox",
                "input_source": "sampled_points" if sampled else "control_points",
                "input_point_count": len(sampled or controls),
                "max_degree": int(curve.get("degree_max") or 3),
                "tolerance_mm": float(
                    curve.get("tolerance_mm", _SPLINE_APPROX_TOLERANCE_MM)
                ),
                "smoothing": None,
                "backend_contract": curve.get("backend_contract"),
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
