"""Command-line interface for CST history extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .command_classifier import build_command_inventory, classify_history_items
from .history_reader import read_cst_file_history, read_history_macro
from .macro_parser import parse_history_text
from .recipe_builder import build_recipe_manifest, summarize_geometry_history
from .report_writer import build_history_analysis_report


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the extractor CLI."""
    parser = argparse.ArgumentParser(
        prog="cst_history_extractor",
        description="Extract recipe-oriented settings from exported CST history macros.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--history-macro", type=Path, help="Exported CST history/macro text file.")
    source_group.add_argument("--cst-file", type=Path, help="CST project file; reads unpacked Model/3D/ModelHistory.json when available.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for extraction outputs.")
    parser.add_argument("--project-id", default="", help="Optional project id for output JSON.")
    parser.add_argument(
        "--cst-library-path",
        type=Path,
        default=None,
        help="Optional CST python_cst_libraries path for opening --cst-file if ModelHistory.json is not unpacked yet.",
    )
    args = parser.parse_args(argv)

    if args.history_macro is not None:
        source = read_history_macro(args.history_macro)
        source_path = args.history_macro
    else:
        source = read_cst_file_history(args.cst_file, args.cst_library_path)
        source_path = args.cst_file

    project_id = args.project_id or _derive_project_id(source_path)
    output_dir = args.output_dir
    raw_dir = output_dir / "raw_history"
    analysis_dir = output_dir / "analysis"
    reports_dir = output_dir / "reports"
    for directory in (raw_dir, analysis_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if source.history_items:
        items = source.history_items
    elif source.raw_text:
        items = parse_history_text(source.raw_text, source_name=source_path.name)
    else:
        items = []
    classified = classify_history_items(items)
    inventory = build_command_inventory(project_id, source.source_path, classified)
    geometry_summary = summarize_geometry_history(classified)
    recipe = build_recipe_manifest(
        project_id,
        source.source_path,
        classified,
        history_limitations=source.limitations,
    )
    report = build_history_analysis_report(
        project_id,
        source.source_path,
        classified,
        recipe,
        geometry_summary,
        source.limitations,
    )

    _write_text(raw_dir / "history_raw.txt", source.raw_text)
    _write_json(raw_dir / "history_items.json", [item.to_dict() for item in items])
    _write_json(raw_dir / "cst_probe.json", source.cst_probe)
    _write_json(raw_dir / "history_source_metadata.json", source.metadata)
    _write_json(analysis_dir / "command_inventory.json", inventory)
    _write_json(analysis_dir / "cst_recipe_manifest.json", recipe)
    _write_json(analysis_dir / "geometry_history_summary.json", geometry_summary)
    _write_json(
        analysis_dir / "unknown_or_unclassified_commands.json",
        inventory["unknown_commands"],
    )
    _write_text(reports_dir / "history_analysis_report.md", report)

    print(f"Wrote CST history extraction outputs to {output_dir}")
    return 0


def _derive_project_id(path: Path) -> str:
    return path.stem or "cst_project"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
