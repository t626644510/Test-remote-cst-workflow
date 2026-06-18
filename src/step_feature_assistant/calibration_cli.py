"""Generate explainable rule-calibration statistics from reviewed projects."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

import yaml

from .classifier_cli import _resolved_labels, _reviewed_project_dirs
from .ml_features import face_feature_row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="step_feature_assistant.calibration_cli")
    parser.add_argument("--review-roots", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    build_calibration(args.review_roots, args.output_dir)
    return 0


def build_calibration(review_roots: Iterable[Path], output_dir: Path) -> dict:
    """Build a human-reviewed calibration proposal without changing production rules."""
    projects = _reviewed_project_dirs(review_roots)
    samples: dict[str, list[dict]] = defaultdict(list)
    rejected_counts: Counter[str] = Counter()
    missed_counts: Counter[str] = Counter()
    for project in projects:
        manifest = _read_json(project / "geometry_manifest.json")
        draft = _read_json(project / "feature_graph_draft.json")
        resolved = _read_json(project / "resolved_feature_graph.json")
        labels_by_face, _ = _resolved_labels(resolved)
        face_map = {face["face_id"]: face for face in manifest.get("faces", [])}
        for face_id, labels in labels_by_face.items():
            if face_id not in face_map:
                continue
            row = face_feature_row(manifest, face_map[face_id], project.name)
            for label in labels:
                samples[label].append(row)
        for feature in resolved.get("features", []):
            if feature.get("status") == "rejected":
                rejected_counts[str(feature.get("type"))] += 1
        for expected in draft.get("missing_expected_features", []):
            missed_counts[str(expected)] += 1

    proposals = {}
    for label, rows in sorted(samples.items()):
        proposals[label] = {
            "sample_count": len(rows),
            "surface_types": dict(Counter(row["surface_type"] for row in rows)),
            "radius_ratio_range": _range(rows, "radius_ratio"),
            "axis_center_norm_range": _range(rows, "axis_center_norm"),
            "area_ratio_range": _range(rows, "area_ratio"),
            "mean_adjacent_count": mean(row["adjacent_count"] for row in rows),
            "status": "proposal_only",
        }
    payload = {
        "schema_version": "0.1",
        "reviewed_project_count": len(projects),
        "profiles": {},
        "feature_statistics": proposals,
        "rejected_candidate_counts": dict(rejected_counts),
        "missing_expected_feature_counts": dict(missed_counts),
        "automatic_rule_changes": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "calibration_proposal.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8"
    )
    (output_dir / "calibration_report.md").write_text(_report(payload), encoding="utf-8")
    return payload


def _range(rows: list[dict], key: str) -> list[float]:
    values = [float(row[key]) for row in rows]
    return [min(values), max(values)]


def _report(payload: dict) -> str:
    lines = [
        "# Feature Rule Calibration",
        "",
        f"- Reviewed projects: {payload['reviewed_project_count']}",
        "- Production rules changed automatically: no",
        "",
        "## Feature Statistics",
        "",
    ]
    for label, stats in payload["feature_statistics"].items():
        lines.append(
            f"- {label}: n={stats['sample_count']}, surfaces={stats['surface_types']}, "
            f"radius_ratio={stats['radius_ratio_range']}, axis_center={stats['axis_center_norm_range']}"
        )
    lines.extend(
        [
            "",
            "## Errors",
            "",
            f"- Rejected candidates: {payload['rejected_candidate_counts']}",
            f"- Missing expected features: {payload['missing_expected_feature_counts']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
