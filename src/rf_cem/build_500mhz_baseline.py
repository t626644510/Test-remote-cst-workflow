"""CLI for building the 500 MHz baseline CSTTranslator v0 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .design_package import BaselineDesignPackage, BaselinePaths
from .history_templates import load_cst_history_templates
from .translator import FilenameMode, translate_baseline
from .udsg_builder import build_baseline_udsg


def main(argv: Sequence[str] | None = None) -> int:
    """Build no-CST RF-CEM artifacts for Appendix/500MHz_baseline."""
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.build_500mhz_baseline",
        description="Build CSTTranslator v0 artifacts for the imported 500 MHz baseline.",
    )
    parser.add_argument("--appendix", type=Path, required=True, help="Path to Appendix/500MHz_baseline.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for generated artifacts.")
    parser.add_argument(
        "--step-filename-mode",
        choices=("star-basename", "absolute"),
        default="star-basename",
        help="How to emit the STEP .FileName argument in CST VBA.",
    )
    args = parser.parse_args(argv)

    paths = BaselinePaths.from_appendix(args.appendix)
    paths.validate()
    package = BaselineDesignPackage()
    templates = load_cst_history_templates(paths.model_history_json)
    udsg, review_diff = build_baseline_udsg(paths, package, templates.recipe)
    artifacts = translate_baseline(
        udsg,
        templates,
        paths.step_file,
        filename_mode=args.step_filename_mode,  # type: ignore[arg-type]
    )
    write_artifacts(args.output_dir, udsg, review_diff, artifacts)
    print(f"Wrote RF-CEM 500 MHz baseline artifacts to {args.output_dir}")
    return 0


def write_artifacts(output_dir: Path, udsg: dict, review_diff: dict, artifacts: object) -> None:
    """Write generated artifacts to the requested output directory."""
    semantic_dir = output_dir / "semantic"
    generated_dir = output_dir / "generated"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    _write_json(semantic_dir / "udsg.v0.json", udsg)
    _write_json(generated_dir / "review_session_diff.json", review_diff)
    _write_json(generated_dir / "cst_actions.json", artifacts.actions)
    _write_json(generated_dir / "cst_mapping_table.json", artifacts.mapping_table)
    _write_json(generated_dir / "translator_report.json", artifacts.report)
    (generated_dir / "cst_script.bas").write_text(artifacts.script, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
