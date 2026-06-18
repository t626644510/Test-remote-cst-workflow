"""Report and review artifact writers for the STEP feature assistant."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def write_face_inventory_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write face inventory rows to CSV."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_review_report(
    geometry_manifest: dict,
    feature_graph_draft: dict,
    hints_path: str | None = None,
) -> str:
    """Return a Markdown review report."""
    summary = geometry_manifest.get("model_summary", {})
    reader = geometry_manifest.get("reader", {})
    features = feature_graph_draft.get("features", [])
    type_counts: dict[str, int] = {}
    for feature in features:
        feature_type = str(feature.get("type", "Unknown"))
        type_counts[feature_type] = type_counts.get(feature_type, 0) + 1

    lines = [
        f"# STEP Feature Review: {Path(geometry_manifest.get('source_step', 'model.step')).name}",
        "",
        "## Source",
        "",
        f"- STEP: `{geometry_manifest.get('source_step')}`",
        f"- Reader backend: `{reader.get('backend')}`",
        f"- Units: `{reader.get('units') or 'unknown'}`",
        f"- Hints: `{hints_path or 'none'}`",
        "",
        "## Model Summary",
        "",
        f"- Solids: {summary.get('solid_count')}",
        f"- Shells: {summary.get('shell_count')}",
        f"- Faces: {summary.get('face_count')}",
        f"- Edges: {summary.get('edge_count')}",
        f"- Axis: `{summary.get('detected_axis')}`",
        f"- BBox: `{summary.get('bbox')}`",
        "",
        "## Reader Limitations",
        "",
    ]
    for limitation in reader.get("limitations", []):
        lines.append(f"- {limitation}")

    lines.extend(["", "## Candidate Feature Counts", ""])
    if type_counts:
        for feature_type, count in sorted(type_counts.items()):
            lines.append(f"- {feature_type}: {count}")
    else:
        lines.append("- None")

    lines.extend(["", "## Candidate Features", ""])
    for feature in features[:80]:
        refs = ", ".join(feature.get("geometry_refs", []))
        lines.append(
            f"- `{feature.get('id')}` {feature.get('type')} "
            f"confidence={feature.get('confidence')} refs=[{refs}]"
        )
        evidence = "; ".join(feature.get("evidence", []))
        if evidence:
            lines.append(f"  Evidence: {evidence}")
    if len(features) > 80:
        lines.append(f"- ... {len(features) - 80} more candidates omitted from report.")

    unassigned = feature_graph_draft.get("unassigned_faces", [])
    lines.extend(["", "## Unassigned Faces", ""])
    if unassigned:
        face_map = {face.get("face_id"): face for face in geometry_manifest.get("faces", [])}
        for face_id in unassigned[:120]:
            face = face_map.get(face_id, {})
            lines.append(
                f"- `{face_id}` {face.get('surface_type', 'unknown')}; "
                f"area={face.get('area')}; centroid={face.get('centroid')}; "
                f"adjacent={face.get('adjacent_faces', [])}"
            )
        if len(unassigned) > 120:
            lines.append(f"... {len(unassigned) - 120} more")
    else:
        lines.append("None.")

    missing_expected = feature_graph_draft.get("missing_expected_features", [])
    lines.extend(["", "## Missing Expected Features", ""])
    lines.append(", ".join(missing_expected) if missing_expected else "None.")

    lines.extend(
        [
            "",
            "## Review Workflow",
            "",
            "1. Open `preview/model_review.html` when generated.",
            "2. Review `review_report.md`, then `face_inventory.csv`.",
            "3. Export or edit `reviewed_feature_labels.yaml` using the project template.",
            "4. Re-run with `--reviewed-labels` to create `resolved_feature_graph.json`.",
            "5. Feed only the resolved graph into CSTTranslator.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_face_coloring_legend(feature_graph_draft: dict) -> dict:
    """Build a simple feature-type color legend for future visualization."""
    palette = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
    ]
    feature_types = sorted({feature.get("type", "Unknown") for feature in feature_graph_draft.get("features", [])})
    return {
        "schema_version": "0.1",
        "legend": {
            feature_type: {
                "color": palette[index % len(palette)],
                "description": f"Candidate {feature_type}",
            }
            for index, feature_type in enumerate(feature_types)
        },
    }
