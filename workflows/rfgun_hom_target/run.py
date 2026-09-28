"""Portable WF5 CLI: config validation, baseline, campaign, resume and replay."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import logging
from pathlib import Path
import sys

from .config import load_config
from .storage import (CampaignStore, atomic_json, copy_verified_project,
                      digest, fingerprint, project_manifest)


def parser() -> argparse.ArgumentParser:
    """Define explicit offline/live command modes without a hidden default run."""
    result = argparse.ArgumentParser(description="WF5 transverse HOM threshold optimization")
    result.add_argument("--config", type=Path, help="Workflow YAML (required except for offline bundle replay)")
    modes = result.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-config", action="store_true", help="Validate configuration; never import CST")
    modes.add_argument("--baseline-only", action="store_true", help="Evaluate template geometry, then stop")
    modes.add_argument("--optimize", action="store_true", help="Start the budgeted search")
    modes.add_argument("--resume", action="store_true", help="Resume this output directory, including field-only recovery")
    modes.add_argument("--analyze-only", type=Path, metavar="BUNDLE", help="Recompute a saved field bundle without CST")
    result.add_argument("--max-solves", type=int, help="Override total solve budget for a NEW campaign")
    result.add_argument("--seed-campaign", type=Path, help="Recompute a stopped campaign's baseline fields under a new mode policy; new campaigns only")
    return result


def main(argv: list[str] | None = None) -> int:
    """Execute one explicit mode; failures preserve diagnostics and resumable state."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parser().parse_args(argv)
    if args.seed_campaign and not (args.optimize or args.baseline_only):
        parser().error("--seed-campaign requires a new --optimize or --baseline-only campaign")
    if args.analyze_only:
        from .postprocess import analyze_bundle
        result = analyze_bundle(args.analyze_only)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result.quality_ok else 2
    if args.config is None:
        parser().error("--config is required for this operation")
    config = load_config(args.config)
    if args.max_solves is not None:
        if args.max_solves < 1 or args.resume:
            parser().error("--max-solves must be positive and is only available for a new campaign")
        config = replace(config, search=replace(config.search, max_solves=args.max_solves))
    if args.validate_config:
        print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))
        return 0
    config.validate_live()
    from .runtime import CSTEvaluator, read_baseline
    from .search import Campaign
    source = config.paths.template_path
    manifest = project_manifest(source)
    # Include executable workflow and shared core source, not the branch name or a timestamp.
    root = Path(__file__).resolve().parents[2]
    sources = list(Path(__file__).parent.glob("*.py")) + list((root / "src/cst_optimization").rglob("*.py"))
    code = {str(p.relative_to(root)): digest(p) for p in sorted(sources)}
    contract = fingerprint({"config": config.as_dict(), "template": manifest, "code": code})
    store = CampaignStore(config.paths.output_dir, contract, config.search.max_solves, resume=args.resume)
    try:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(store.root / "campaign.log", encoding="utf-8")])
        if not (store.root / "template.json").exists():
            template, copied = copy_verified_project(source, store.root / "template")
            if copied != manifest:
                raise RuntimeError("Source changed between campaign fingerprint and immutable snapshot")
            atomic_json(store.root / "template.json", {"project": str(template), "manifest": copied,
                                                       "source": str(source)})
            atomic_json(store.root / "config.resolved.json", config.as_dict())
        else:
            saved = json.loads((store.root / "template.json").read_text(encoding="utf-8"))
            template = Path(saved["project"])
            if project_manifest(template) != manifest:
                raise RuntimeError("Immutable template snapshot fingerprint changed")
        baseline = read_baseline(template, config)
        atomic_json(store.root / "baseline_parameters.json", baseline)
        campaign = Campaign(config, store, CSTEvaluator(config, template))
        if args.seed_campaign:
            from .seeding import import_baseline
            import_baseline(config, store, template, args.seed_campaign)
            logging.info("Imported and recomputed baseline; no CST solve consumed")
            campaign.report()
        report = campaign.run(baseline, baseline_only=args.baseline_only)
        unchanged = project_manifest(source) == manifest
        atomic_json(store.root / "source_verification.json", {"source_unchanged": unchanged,
                                                              "template_manifest": manifest})
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["status"] in {"target_reached", "baseline_complete"} else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
