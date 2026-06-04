"""No-CST tolerance analysis CLI — TAM6.

Explicitly invoked only via ``python -m workflows.rfgun_sao.tolerance_cli``.
No CST, no JSONL, no Excel, no runtime/config changes.

Usage::

    python -m workflows.rfgun_sao.tolerance_cli --db PATH
    python -m workflows.rfgun_sao.tolerance_cli --db PATH --format json
    python -m workflows.rfgun_sao.tolerance_cli --db PATH --output report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from workflows.rfgun_sao.tolerance_analysis import (
    ToleranceAnalysisConfig,
    analyze_tolerance_records,
)
from workflows.rfgun_sao.tolerance_report import (
    render_tolerance_markdown,
    tolerance_analysis_report_to_dict,
)
from workflows.rfgun_sao.tolerance_db_adapter import (
    load_records_from_sqlite_db,
)


def parse_csv_arg(value: str | None) -> tuple[str, ...] | None:
    """Parse a comma-separated argument value into a tuple.

    ``None`` or empty string → ``None``.
    ``"a,b,c"`` → ``("a", "b", "c")``.
    """
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return tuple(parts) if parts else None


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the tolerance analysis CLI."""
    parser = argparse.ArgumentParser(
        description="Tolerance analysis on an evaluation database",
    )
    parser.add_argument(
        "--db", type=str, required=True,
        help="Path to an existing SQLite evaluation database",
    )
    parser.add_argument(
        "--format", type=str, default="markdown", choices={"markdown", "json"},
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write output to this file; if omitted print to stdout",
    )
    parser.add_argument(
        "--metrics", type=str, default=None,
        help="Comma-separated metric names",
    )
    parser.add_argument(
        "--params", type=str, default=None,
        help="Comma-separated parameter names",
    )
    parser.add_argument(
        "--clean-method", type=str, default="iqr", choices={"iqr", "mad"},
        help="Outlier detection method (default: iqr)",
    )
    parser.add_argument(
        "--sensitivity-method", type=str, default="spearman",
        choices={"spearman", "pearson", "linear_beta"},
        help="Sensitivity method (default: spearman)",
    )
    parser.add_argument(
        "--no-clean-cv", action="store_true",
        help="Skip clean CV computation",
    )
    parser.add_argument(
        "--no-sensitivity", action="store_true",
        help="Skip sensitivity analysis",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the tolerance analysis CLI.

    Parameters
    ----------
    argv : sequence of str or None
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code (0 on success, nonzero on error).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Validate DB path
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: DB path does not exist: {db_path}", file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"Error: DB path is not a file: {db_path}", file=sys.stderr)
        return 1

    # Load records
    try:
        records = load_records_from_sqlite_db(str(db_path))
    except Exception as exc:
        print(f"Error loading DB: {exc}", file=sys.stderr)
        return 1

    # Build config
    try:
        cfg = ToleranceAnalysisConfig(
            metric_names=parse_csv_arg(args.metrics),
            param_names=parse_csv_arg(args.params),
            clean_method=args.clean_method,
            sensitivity_method=args.sensitivity_method,
            include_clean_cv=not args.no_clean_cv,
            include_sensitivity=not args.no_sensitivity,
        )
    except Exception as exc:
        print(f"Error building config: {exc}", file=sys.stderr)
        return 1

    # Run analysis
    try:
        report = analyze_tolerance_records(records, config=cfg)
    except Exception as exc:
        print(f"Error during analysis: {exc}", file=sys.stderr)
        return 1

    # Render output
    if args.format == "json":
        output = json.dumps(
            tolerance_analysis_report_to_dict(report),
            indent=2, sort_keys=True, ensure_ascii=False,
        )
    else:
        output = render_tolerance_markdown(report)

    # Write or print output
    if args.output:
        out_path = Path(args.output)
        if not out_path.parent.exists():
            print(
                f"Error: output parent directory does not exist: {out_path.parent}",
                file=sys.stderr,
            )
            return 1
        try:
            out_path.write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"Error writing output: {exc}", file=sys.stderr)
            return 1
    else:
        print(output)

    return 0


def main() -> int:
    """Entry point for ``python -m`` invocation."""
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
