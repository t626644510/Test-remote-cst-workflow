"""Command-line interface for RF-CEM literature semantic packages."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .audit import write_audit_html
from .prior_mapper import build_draft_prior, merge_draft_prior, read_prior_yaml
from .types import PriorDraftError, write_yaml
from .validator import has_errors, load_semantic_package, validate_semantic_package


def main(argv: Sequence[str] | None = None) -> int:
    """Run literature semantic validation, draft-prior, merge, and audit commands."""
    parser = argparse.ArgumentParser(prog="python -m rf_cem.literature_semantics")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a literature_semantics.v0 package.")
    validate_parser.add_argument("--package", type=Path, required=True)

    draft_parser = subparsers.add_parser("draft-prior", help="Generate expert_prior.draft.v0.yaml.")
    draft_parser.add_argument("--package", type=Path, required=True)
    draft_parser.add_argument("--base-prior", type=Path, required=True)
    draft_parser.add_argument("--out", type=Path, required=True)

    merge_parser = subparsers.add_parser("merge-prior", help="Merge a reviewed draft into an expert_prior.v0 YAML file.")
    merge_parser.add_argument("--base-prior", type=Path, required=True)
    merge_parser.add_argument("--draft-prior", type=Path, required=True)
    merge_parser.add_argument("--out", type=Path, required=True)
    merge_parser.add_argument("--require-reviewed", action="store_true")

    audit_parser = subparsers.add_parser("audit", help="Write an HTML audit report.")
    audit_parser.add_argument("--package", type=Path, required=True)
    audit_parser.add_argument("--draft-prior", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "validate":
        package = load_semantic_package(args.package)
        issues = validate_semantic_package(package)
        for issue in issues:
            print(f"{issue.severity.upper()}: {issue.path}: {issue.message}")
        if not issues:
            print("OK: literature semantic package is valid")
        return 1 if has_errors(issues) else 0

    if args.command == "draft-prior":
        package = load_semantic_package(args.package)
        base_prior = read_prior_yaml(args.base_prior)
        draft = build_draft_prior(
            package,
            base_prior_ref=args.base_prior,
            literature_semantics_ref=args.package,
            base_prior=base_prior,
        )
        write_yaml(args.out, draft)
        print(f"Wrote expert prior draft to {args.out}")
        return 0

    if args.command == "merge-prior":
        base_prior = read_prior_yaml(args.base_prior)
        draft_prior = read_prior_yaml(args.draft_prior)
        try:
            merged = merge_draft_prior(base_prior, draft_prior, require_reviewed=args.require_reviewed)
        except PriorDraftError as exc:
            print(f"ERROR: {exc}")
            return 1
        write_yaml(args.out, merged)
        print(f"Wrote merged expert prior to {args.out}")
        return 0

    if args.command == "audit":
        package = load_semantic_package(args.package)
        draft_prior = read_prior_yaml(args.draft_prior)
        write_audit_html(args.out, package, draft_prior)
        print(f"Wrote literature semantics audit to {args.out}")
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
