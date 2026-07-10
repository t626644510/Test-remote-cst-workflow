"""Command-line interface for RF-CEM literature semantic packages."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .arxiv_ingest import (
    ArxivClient,
    ArxivIngestError,
    build_source_manifest,
    write_source_manifest,
)
from .audit import write_audit_html
from .corpus_audit import CorpusAuditError, write_corpus_audit_html
from .pdf_evidence import PdfEvidenceError, render_pdf_pages
from .prior_mapper import build_draft_prior, merge_draft_prior, read_prior_yaml
from .types import PriorDraftError, write_json, write_yaml
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
    merge_parser.add_argument("--package", type=Path, required=True)
    merge_parser.add_argument("--base-prior", type=Path, required=True)
    merge_parser.add_argument("--draft-prior", type=Path, required=True)
    merge_parser.add_argument("--out", type=Path, required=True)
    review_group = merge_parser.add_mutually_exclusive_group()
    review_group.add_argument("--require-reviewed", dest="require_reviewed", action="store_true")
    review_group.add_argument("--allow-unreviewed", dest="require_reviewed", action="store_false")
    merge_parser.set_defaults(require_reviewed=True)

    audit_parser = subparsers.add_parser("audit", help="Write an HTML audit report.")
    audit_parser.add_argument("--package", type=Path, required=True)
    audit_parser.add_argument("--draft-prior", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path, required=True)

    search_parser = subparsers.add_parser(
        "arxiv-search",
        help="Discover arXiv metadata candidates without assigning applicability.",
    )
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--max-results", type=int, default=10)
    search_parser.add_argument("--out", type=Path, required=True)

    fetch_parser = subparsers.add_parser(
        "arxiv-fetch",
        help="Fetch one explicitly versioned arXiv source and immutable manifest.",
    )
    fetch_parser.add_argument("--id", dest="arxiv_id", required=True)
    fetch_parser.add_argument("--out-dir", type=Path, required=True)

    render_parser = subparsers.add_parser(
        "render-evidence",
        help="Render selected one-based PDF pages to PNG evidence with Poppler.",
    )
    render_parser.add_argument("--pdf", type=Path, required=True)
    render_parser.add_argument("--pages", type=int, nargs="+", required=True)
    render_parser.add_argument("--out-dir", type=Path, required=True)
    render_parser.add_argument("--pdftoppm", default="pdftoppm")
    render_parser.add_argument("--dpi", type=int, default=150)

    corpus_parser = subparsers.add_parser(
        "corpus-audit",
        help="Build one self-contained audit HTML from a corpus manifest.",
    )
    corpus_parser.add_argument("--bundle-root", type=Path, required=True)
    corpus_parser.add_argument("--manifest", type=Path, required=True)
    corpus_parser.add_argument("--out", type=Path, required=True)

    review_parser = subparsers.add_parser(
        "review-gui",
        help="Serve the authenticated no-CST literature/geometry review GUI.",
    )
    review_parser.add_argument("--bundle-root", type=Path, required=True)
    review_parser.add_argument(
        "--manifest", type=Path, default=Path("corpus_manifest.json")
    )
    review_parser.add_argument("--paper-id", default="sls2")
    review_parser.add_argument("--session-root", type=Path, required=True)
    review_parser.add_argument("--port", type=int, default=0)
    review_parser.add_argument("--deflection-mm", type=float, default=0.5)

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
        package = load_semantic_package(args.package)
        base_prior = read_prior_yaml(args.base_prior)
        draft_prior = read_prior_yaml(args.draft_prior)
        try:
            merged = merge_draft_prior(
                base_prior,
                draft_prior,
                semantic_package=package,
                require_reviewed=args.require_reviewed,
            )
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

    if args.command == "arxiv-search":
        try:
            candidates = ArxivClient().search(args.query, max_results=args.max_results)
        except (ArxivIngestError, OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        write_json(
            args.out,
            {
                "schema_version": "rf_cem.arxiv_search_candidates.v1",
                "query": args.query,
                "candidates": [asdict(candidate) for candidate in candidates],
                "warning": (
                    "Search rank is discovery metadata only; a human must review "
                    "relevance, authority, and RF-CEM applicability."
                ),
            },
        )
        print(f"Wrote {len(candidates)} arXiv candidates to {args.out}")
        return 0

    if args.command == "arxiv-fetch":
        client = ArxivClient()
        try:
            metadata = client.fetch_metadata(args.arxiv_id)
            pdf = client.download_pdf(args.arxiv_id, args.out_dir / "source.pdf")
            manifest = build_source_manifest(metadata, pdf, pdf_path="source.pdf")
            manifest_path = write_source_manifest(
                args.out_dir / "source_manifest.json",
                manifest,
            )
        except (ArxivIngestError, OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Wrote pinned arXiv source manifest to {manifest_path}")
        return 0

    if args.command == "render-evidence":
        try:
            artifacts = render_pdf_pages(
                args.pdf,
                args.pages,
                args.out_dir,
                pdftoppm=args.pdftoppm,
                dpi=args.dpi,
            )
        except (PdfEvidenceError, OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        output_root = args.out_dir.resolve()
        manifest_entries = []
        for artifact in artifacts:
            entry = dict(artifact)
            entry["path"] = Path(entry["path"]).resolve().relative_to(output_root).as_posix()
            manifest_entries.append(entry)
        write_json(args.out_dir / "render_manifest.json", manifest_entries)
        print(f"Rendered {len(artifacts)} evidence pages to {args.out_dir}")
        return 0

    if args.command == "corpus-audit":
        try:
            write_corpus_audit_html(
                args.out,
                args.bundle_root,
                args.manifest,
            )
        except (CorpusAuditError, OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Wrote literature corpus audit to {args.out}")
        return 0

    if args.command == "review-gui":
        from .review_app import Sls2LiteratureReviewApp

        try:
            app = Sls2LiteratureReviewApp(
                bundle_root=args.bundle_root,
                corpus_manifest=args.manifest,
                session_root=args.session_root,
                paper_id=args.paper_id,
                deflection_mm=args.deflection_mm,
            )
            launch = app.prepare_server(port=args.port)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Review URL: {launch.review_url}", flush=True)
        print(f"Review HTML: {launch.html_path}", flush=True)
        print(f"Initial STEP: {launch.initial_step_path}", flush=True)
        print(
            "Preview-only; live CST and production-prior mutation are disabled.",
            flush=True,
        )
        try:
            launch.server.serve_forever()
        except KeyboardInterrupt:
            print("Review server stopped.", flush=True)
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
