"""Command-line entry points for deterministic W0/W1/W2 rebuild and serving."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Sequence

from .indexer import WorkbenchIndexError, WorkbenchSourceSet, rebuild_workbench
from .registry import RegistryReader, WorkbenchRegistryError
from .server import WorkbenchServer


def build_parser() -> argparse.ArgumentParser:
    """Build the Workbench command-line parser."""
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.workbench",
        description="Build and browse the local no-CST RF-CEM project catalog.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rebuild = subparsers.add_parser(
        "rebuild", help="atomically rebuild the derived SQLite registry"
    )
    rebuild.add_argument("--database", type=Path, required=True)
    rebuild.add_argument("--repo-root", type=Path, default=Path.cwd())
    rebuild.add_argument("--family-profile", type=Path, required=True)
    rebuild.add_argument("--family-profile-validation", type=Path)
    rebuild.add_argument("--architecture-document", type=Path)
    rebuild.add_argument(
        "--literature-package", type=Path, action="append", default=[]
    )
    rebuild.add_argument("--review-session", type=Path, action="append", default=[])
    rebuild.add_argument("--family-grammar", type=Path)
    rebuild.add_argument(
        "--instance-boundary-graph", type=Path, action="append", default=[]
    )
    rebuild.add_argument("--instance-graph-diff", type=Path)
    rebuild.add_argument(
        "--compile-record", type=Path, action="append", default=[]
    )

    serve = subparsers.add_parser(
        "serve", help="serve one existing registry on authenticated loopback"
    )
    serve.add_argument("--database", type=Path, required=True)
    serve.add_argument("--repo-root", type=Path, default=Path.cwd())
    serve.add_argument("--port", type=int, default=0)

    status = subparsers.add_parser(
        "status", help="print deterministic registry and source status JSON"
    )
    status.add_argument("--database", type=Path, required=True)
    status.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one Workbench command and return a process exit code."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "rebuild":
            root = args.repo_root.resolve()
            source_set = WorkbenchSourceSet(
                repo_root=root,
                family_profile=_resolve(root, args.family_profile),
                family_profile_validation=_resolve_optional(
                    root, args.family_profile_validation
                ),
                architecture_document=_resolve_optional(
                    root, args.architecture_document
                ),
                literature_packages=tuple(
                    _resolve(root, path) for path in args.literature_package
                ),
                review_sessions=tuple(
                    _resolve(root, path) for path in args.review_session
                ),
                family_grammar=_resolve_optional(root, args.family_grammar),
                instance_boundary_graphs=tuple(
                    _resolve(root, path)
                    for path in args.instance_boundary_graph
                ),
                instance_graph_diff=_resolve_optional(
                    root, args.instance_graph_diff
                ),
                compile_records=tuple(
                    _resolve(root, path) for path in args.compile_record
                ),
            )
            summary = rebuild_workbench(args.database, source_set)
            print(
                json.dumps(
                    {
                        "database": str(summary.database),
                        "entity_count": summary.entity_count,
                        "input_set_sha256": summary.input_set_sha256,
                        "relation_count": summary.relation_count,
                        "source_count": summary.source_count,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "serve":
            server = WorkbenchServer(
                args.database,
                source_root=args.repo_root,
                port=args.port,
            )
            print(f"workbench_url={server.workbench_url}")
            print("mode=read_only_no_cst")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                return 0
            return 0
        if args.command == "status":
            reader = RegistryReader(args.database)
            print(
                json.dumps(
                    {
                        "metadata": reader.metadata(),
                        "counts": reader.entity_counts(),
                        "sources": reader.audit_sources(args.repo_root),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
    except (
        OSError,
        sqlite3.Error,
        WorkbenchIndexError,
        WorkbenchRegistryError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


def _resolve(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _resolve_optional(root: Path, path: Path | None) -> Path | None:
    return None if path is None else _resolve(root, path)


__all__ = ["build_parser", "main"]
