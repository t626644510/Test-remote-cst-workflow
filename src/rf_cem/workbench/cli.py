"""Command-line entry points for deterministic W0-W4 rebuild and serving."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Sequence

from .indexer import WorkbenchIndexError, WorkbenchSourceSet, rebuild_workbench
from .profile import (
    WorkbenchProfileError,
    inspect_workbench_profile,
    rebuild_workbench_profile,
    resolve_workbench_profile,
)
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
    rebuild.add_argument("--database", type=Path)
    rebuild.add_argument("--repo-root", type=Path, default=Path.cwd())
    rebuild.add_argument("--profile", type=Path)
    rebuild.add_argument("--family-profile", type=Path)
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
    rebuild.add_argument(
        "--family-induction-bundle",
        type=Path,
        help="immutable R3 family-induction proof-bundle directory",
    )
    rebuild.add_argument(
        "--observation-contract-bundle",
        type=Path,
        help="immutable R4 observation/constraint proof-bundle directory",
    )

    serve = subparsers.add_parser(
        "serve", help="serve one existing registry on authenticated loopback"
    )
    serve.add_argument("--database", type=Path)
    serve.add_argument("--repo-root", type=Path, default=Path.cwd())
    serve.add_argument("--profile", type=Path)
    serve.add_argument("--port", type=int, default=0)

    status = subparsers.add_parser(
        "status", help="print deterministic registry and source status JSON"
    )
    status.add_argument("--database", type=Path)
    status.add_argument("--repo-root", type=Path, default=Path.cwd())
    status.add_argument("--profile", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one Workbench command and return a process exit code."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "rebuild":
            if args.profile is not None:
                _reject_mixed_profile_args(args)
                resolved = resolve_workbench_profile(args.repo_root, args.profile)
                summary = rebuild_workbench_profile(resolved)
            else:
                if args.database is None or args.family_profile is None:
                    raise WorkbenchProfileError(
                        "rebuild requires --profile or both --database and --family-profile"
                    )
                root = args.repo_root.resolve()
                source_set = _source_set_from_args(root, args)
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
            if args.profile is not None:
                if args.database is not None:
                    raise WorkbenchProfileError(
                        "serve --profile cannot be combined with --database"
                    )
                resolved = resolve_workbench_profile(args.repo_root, args.profile)
                database = resolved.database
                source_root = resolved.repo_root
            else:
                if args.database is None:
                    raise WorkbenchProfileError(
                        "serve requires --profile or --database"
                    )
                database = args.database
                source_root = args.repo_root
            server = WorkbenchServer(
                database,
                source_root=source_root,
                port=args.port,
            )
            print(f"workbench_url={server.workbench_url}", flush=True)
            print("mode=read_only_no_cst", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                return 0
            return 0
        if args.command == "status":
            if args.profile is not None:
                if args.database is not None:
                    raise WorkbenchProfileError(
                        "status --profile cannot be combined with --database"
                    )
                resolved = resolve_workbench_profile(args.repo_root, args.profile)
                status = inspect_workbench_profile(resolved)
                payload = status.to_mapping()
                if resolved.database.is_file() and status.database_state != "invalid":
                    reader = RegistryReader(resolved.database)
                    payload["metadata"] = reader.metadata()
                    payload["counts"] = reader.entity_counts()
                print(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True)
                )
                return 0
            if args.database is None:
                raise WorkbenchProfileError("status requires --profile or --database")
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
        WorkbenchProfileError,
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


def _source_set_from_args(root: Path, args: argparse.Namespace) -> WorkbenchSourceSet:
    assert args.family_profile is not None
    return WorkbenchSourceSet(
        repo_root=root,
        family_profile=_resolve(root, args.family_profile),
        family_profile_validation=_resolve_optional(
            root, args.family_profile_validation
        ),
        architecture_document=_resolve_optional(root, args.architecture_document),
        literature_packages=tuple(
            _resolve(root, path) for path in args.literature_package
        ),
        review_sessions=tuple(_resolve(root, path) for path in args.review_session),
        family_grammar=_resolve_optional(root, args.family_grammar),
        instance_boundary_graphs=tuple(
            _resolve(root, path) for path in args.instance_boundary_graph
        ),
        instance_graph_diff=_resolve_optional(root, args.instance_graph_diff),
        compile_records=tuple(_resolve(root, path) for path in args.compile_record),
        family_induction_bundle=_resolve_optional(
            root, args.family_induction_bundle
        ),
        observation_contract_bundle=_resolve_optional(
            root, args.observation_contract_bundle
        ),
    )


def _reject_mixed_profile_args(args: argparse.Namespace) -> None:
    mixed = (
        args.database,
        args.family_profile,
        args.family_profile_validation,
        args.architecture_document,
        *args.literature_package,
        *args.review_session,
        args.family_grammar,
        *args.instance_boundary_graph,
        args.instance_graph_diff,
        *args.compile_record,
        args.family_induction_bundle,
        args.observation_contract_bundle,
    )
    if any(value is not None for value in mixed):
        raise WorkbenchProfileError(
            "rebuild --profile cannot be combined with explicit source arguments"
        )


__all__ = ["build_parser", "main"]
