"""Workflow 4 command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .config import Workflow4Config, load_workflow4_config
from .workflow import Workflow4Campaign

DEFAULT_CONFIG = Path(__file__).resolve().with_name("config.yaml")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Workflow 4 - RF gun HOM eigenmode batch calculation",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Workflow 4 YAML configuration",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate input and write clusters/windows without launching CST",
    )
    parser.add_argument(
        "--audit-results",
        action="store_true",
        help="Audit configured result-tree paths and external field files",
    )
    parser.add_argument(
        "--offline-only",
        metavar="RUN_DIR",
        default="",
        help="Re-run offline HDF5 post-processing in an existing campaign",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the latest or configured hash-matching campaign",
    )
    parser.add_argument(
        "--resume-preview",
        action="store_true",
        help="Read state and print skip/run/avoid decisions plus ETA without CST",
    )
    parser.add_argument(
        "--window-id",
        default="",
        help="Run exactly one planned window; saturation follow-ups are deferred",
    )
    parser.add_argument(
        "--force-retry",
        action="store_true",
        help="Allow one explicitly selected avoid_retry window to get fresh budgets",
    )
    parser.add_argument(
        "--template-migration-preview",
        action="store_true",
        help="Preview explicit template revision adoption without writing state",
    )
    parser.add_argument(
        "--adopt-template-revision",
        action="store_true",
        help="Adopt the current template hash and reset selected retry budgets",
    )
    parser.add_argument(
        "--retry-scope",
        choices=("long-related",),
        default="long-related",
        help="Window set reset by template adoption",
    )
    parser.add_argument(
        "--template-change-note",
        default="",
        help="Required provenance note for --adopt-template-revision",
    )
    return parser


def _latest_campaign(output_root: Path) -> Path:
    candidates = sorted(
        path
        for path in output_root.glob("hom_campaign_*")
        if (path / "campaign_state.json").is_file()
    )
    if not candidates:
        raise FileNotFoundError(
            f"no resumable Workflow 4 campaign under {output_root}"
        )
    return candidates[-1]


def resolve_campaign_dir(
    config: Workflow4Config,
    *,
    resume: bool,
    offline_dir: str = "",
) -> Path:
    if offline_dir:
        return Path(offline_dir).expanduser().resolve()
    if config.campaign_dir is not None:
        return config.campaign_dir
    if resume:
        return _latest_campaign(config.output_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return config.output_root / f"hom_campaign_{timestamp}"


def _setup_logging(campaign_dir: Path, *, read_only: bool = False) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if not read_only:
        campaign_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(
                campaign_dir / "workflow_4_runtime.log",
                encoding="utf-8",
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.force_retry and not args.window_id:
        raise SystemExit("--force-retry requires --window-id")
    if args.force_retry and not (args.resume or args.resume_preview):
        raise SystemExit("--force-retry requires --resume or --resume-preview")
    if args.template_migration_preview and args.adopt_template_revision:
        raise SystemExit(
            "choose only one of --template-migration-preview and "
            "--adopt-template-revision"
        )
    if args.adopt_template_revision and not args.template_change_note.strip():
        raise SystemExit(
            "--adopt-template-revision requires --template-change-note"
        )
    migration_action = (
        args.template_migration_preview or args.adopt_template_revision
    )
    config = load_workflow4_config(args.config)
    campaign_dir = resolve_campaign_dir(
        config,
        resume=(
            args.resume
            or args.resume_preview
            or migration_action
            or bool(args.offline_only)
        ),
        offline_dir=args.offline_only,
    )
    _setup_logging(
        campaign_dir,
        read_only=args.resume_preview or args.template_migration_preview,
    )
    campaign = Workflow4Campaign(
        config,
        campaign_dir,
        resume=(
            args.resume
            or args.resume_preview
            or migration_action
            or bool(args.offline_only)
        ),
    )

    if migration_action:
        campaign.initialize_template_migration(persist=False)
        if args.template_migration_preview:
            preview = campaign.template_migration_preview(
                retry_scope=args.retry_scope
            )
        else:
            preview = campaign.adopt_template_revision(
                retry_scope=args.retry_scope,
                change_note=args.template_change_note,
            )
        low, high = preview["realistic_hours"]
        print(
            f"Template changed={preview['changed']}: "
            f"{preview['old_template_hash']} -> "
            f"{preview['new_template_hash']}"
        )
        print(
            f"reset={len(preview['reset_window_ids'])}, "
            f"run_after_adoption={preview['run_count_after_adoption']}, "
            f"skip_completed={preview['skip_completed_count']}, "
            f"historical_ideal={preview['ideal_hours']:.1f} h, "
            f"historical_realistic={low:.1f}-{high:.1f} h"
        )
        print(f"ETA basis: {preview['eta_basis']}")
        for window_id in preview["reset_window_ids"]:
            print(f"reset long-related failure: {window_id}")
        return 0

    if args.resume_preview:
        campaign.initialize(
            require_template=True,
            allow_config_change=True,
            persist=False,
        )
        preview = campaign.resume_preview(
            window_id=args.window_id,
            force_retry=args.force_retry,
        )
        for row in preview["windows"]:
            print(
                f"{row['solver_window_id']}: {row['status']} -> "
                f"{row['decision']} ({row['estimated_minutes']:.0f} min)"
            )
        low, high = preview["realistic_hours"]
        print(
            f"Resume preview: run={preview['run_count']}, "
            f"skip={preview['skip_count']}, avoid={preview['avoid_count']}, "
            f"ideal={preview['ideal_hours']:.1f} h, "
            f"realistic={low:.1f}-{high:.1f} h"
        )
        return 0

    if args.offline_only:
        campaign.initialize(require_template=True, allow_config_change=True)
        modes = campaign.offline_reprocess()
        print(f"Offline post-processing complete: {len(modes)} unique modes")
        return 0

    campaign.initialize(
        require_template=not args.plan_only,
        allow_config_change=args.resume,
    )
    if args.plan_only:
        print(
            f"Plan complete: {len(campaign.records)} rows -> "
            f"{len(campaign.clusters)} clusters -> {len(campaign.windows)} windows"
        )
        print(campaign_dir)
        return 0
    if args.audit_results:
        audit = campaign.audit_results()
        print(
            "Result contract audit complete: "
            f"native_modes={audit['native_mode_count']}, "
            f"complete={audit['template_contract_complete']}"
        )
        print(campaign_dir / "result_contract_audit.json")
        return 0

    modes = campaign.run(
        window_id=args.window_id,
        force_retry=args.force_retry,
    )
    print(f"Workflow 4 complete: {len(modes)} unique simulated modes")
    print(campaign_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
