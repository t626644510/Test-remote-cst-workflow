"""Command-line interface for STEP feature graph drafting."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Sequence

import yaml

from .cadquery_reader import build_geometry_manifest_for_backend
from .classifier import SklearnFeatureScorer
from .feature_candidate_generator import generate_feature_graph_draft
from .layer_builders import build_feature_candidates, build_geometry_graph, build_udsg_geometry_layer
from .model_profiles import load_model_profile
from .report_writer import build_face_coloring_legend, build_review_report, write_face_inventory_csv
from .review_merger import load_review_yaml, merge_reviewed_labels, write_review_template
from .reviewer import write_interactive_reviewer
from .topology_analyzer import build_adjacency_graph, build_face_inventory_rows


MODEL_TYPES = ("normal_conducting_500mhz", "xband_2.3cell_gun", "bare_cavity_500mhz")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run STEP topology extraction and feature candidate generation."""
    parser = argparse.ArgumentParser(
        prog="step_feature_assistant",
        description="Build geometry manifests and feature-graph drafts from STEP B-Rep files.",
    )
    parser.add_argument("--step-file", type=Path, required=True, help="Input STEP/STP file.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated review artifacts.")
    parser.add_argument("--axis", default="z", choices=("x", "y", "z"), help="Beam axis used for RF feature rules.")
    parser.add_argument("--model-type", required=True, choices=MODEL_TYPES, help="Model family for feature heuristics.")
    parser.add_argument(
        "--backend",
        default="fallback",
        choices=("fallback", "cadquery", "auto"),
        help="STEP reader backend. fallback preserves v1 behavior; cadquery uses CadQuery/OCP when installed.",
    )
    parser.add_argument("--preview", choices=("html", "none"), default="html", help="Generate an offline interactive reviewer.")
    parser.add_argument("--open-reviewer", action="store_true", help="Open the generated HTML reviewer after extraction.")
    parser.add_argument("--rules", type=Path, default=None, help="Optional reviewed rule-profile overrides.")
    parser.add_argument("--classifier-model", type=Path, default=None, help="Optional experimental classifier.joblib.")
    parser.add_argument("--hints", type=Path, default=None, help="Optional YAML hints for feature labeling.")
    parser.add_argument("--reviewed-labels", type=Path, default=None, help="Optional reviewed labels YAML to resolve graph.")
    parser.add_argument(
        "--legacy-only",
        action="store_true",
        help="Write only legacy Helper2 outputs and omit UDSG-facing geometry-layer files.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    preview_dir = output_dir / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_path = preview_dir / "face_meshes.json"
    if mesh_path.exists():
        mesh_path.unlink()

    hints = _load_yaml(args.hints) if args.hints else {}
    profile = load_model_profile(args.model_type, args.rules)
    geometry_manifest = build_geometry_manifest_for_backend(
        args.step_file,
        args.axis,
        args.backend,
        mesh_output=mesh_path if args.preview == "html" else None,
    )
    face_rows = build_face_inventory_rows(geometry_manifest)
    adjacency_graph = build_adjacency_graph(geometry_manifest)
    feature_graph_draft = generate_feature_graph_draft(
        geometry_manifest,
        model_type=args.model_type,
        axis=args.axis,
        hints=hints,
        rules=profile,
    )
    geometry_graph = None
    feature_candidates = None
    udsg_geometry_layer = None
    if not args.legacy_only:
        geometry_graph = build_geometry_graph(geometry_manifest, adjacency_graph)
        feature_candidates = build_feature_candidates(feature_graph_draft)
        udsg_geometry_layer = build_udsg_geometry_layer(
            geometry_graph,
            feature_candidates,
            feature_graph_draft.get("face_groups", []),
        )
    classifier_suggestions = None
    if args.classifier_model is not None:
        classifier_suggestions = SklearnFeatureScorer(args.classifier_model).score_manifest(geometry_manifest)
    report = build_review_report(
        geometry_manifest,
        feature_graph_draft,
        hints_path=str(args.hints) if args.hints else None,
    )
    legend = build_face_coloring_legend(feature_graph_draft)

    _write_json(output_dir / "geometry_manifest.json", geometry_manifest)
    _write_json(output_dir / "face_inventory.json", face_rows)
    write_face_inventory_csv(output_dir / "face_inventory.csv", face_rows)
    _write_json(output_dir / "adjacency_graph.json", adjacency_graph)
    _write_json(output_dir / "feature_graph_draft.json", feature_graph_draft)
    if not args.legacy_only:
        _write_json(output_dir / "geometry_graph.json", geometry_graph)
        _write_json(output_dir / "feature_candidates.json", feature_candidates)
        _write_json(output_dir / "udsg_geometry_layer.json", udsg_geometry_layer)
    _write_json(preview_dir / "face_coloring_legend.json", legend)
    write_review_template(output_dir / "reviewed_feature_labels.template.yaml", feature_graph_draft)
    _write_text(output_dir / "review_report.md", report)
    if classifier_suggestions is not None:
        _write_json(output_dir / "classifier_suggestions.json", classifier_suggestions)

    reviewer_path = preview_dir / "model_review.html"
    if args.preview == "html" and mesh_path.exists():
        write_interactive_reviewer(
            reviewer_path,
            mesh_path,
            geometry_manifest,
            feature_graph_draft,
            classifier_suggestions,
            geometry_graph=geometry_graph,
            feature_candidates=feature_candidates,
            udsg_geometry_layer=udsg_geometry_layer,
        )
    elif reviewer_path.exists():
        reviewer_path.unlink()

    if args.reviewed_labels is not None:
        review_data = load_review_yaml(args.reviewed_labels)
        resolved = merge_reviewed_labels(feature_graph_draft, review_data, geometry_manifest)
        _write_json(output_dir / "resolved_feature_graph.json", resolved)

    print(f"Wrote STEP feature assistant outputs to {output_dir}")
    if args.preview == "html" and not reviewer_path.exists():
        print("Interactive HTML preview was not generated because the selected backend did not provide face meshes.")
    if args.open_reviewer and reviewer_path.exists():
        os.startfile(str(reviewer_path.resolve()))
    return 0


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
