"""Command-line entry points for the no-CST R1 semantic core."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .adapters import R1SourceSet, build_r1_contracts
from .artifacts import write_r1_bundle
from .contracts import (
    SemanticContractError,
    canonical_json_bytes,
    canonical_sha256,
    diff_instance_graphs,
    load_family_grammar,
    load_instance_boundary_graph,
    validate_graph_against_grammar,
)


def build_parser() -> argparse.ArgumentParser:
    """Return the R1 semantic-core CLI parser."""

    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.semantic",
        description="Build, validate, and diff RF-CEM semantic topology contracts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="build a deterministic R1 proof bundle from reviewed sources"
    )
    build.add_argument("--repo-root", type=Path, required=True)
    build.add_argument("--family-profile", type=Path, required=True)
    build.add_argument("--sls2-generation", type=Path, required=True)
    build.add_argument("--sls2-semantics", type=Path, required=True)
    build.add_argument("--sls2-review", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="validate one or more instance graphs against a grammar"
    )
    validate.add_argument("--grammar", type=Path, required=True)
    validate.add_argument(
        "--graph", type=Path, action="append", required=True, dest="graphs"
    )

    diff = subparsers.add_parser(
        "diff", help="derive a semantic/topology diff for two instance graphs"
    )
    diff.add_argument("--left", type=Path, required=True)
    diff.add_argument("--right", type=Path, required=True)
    diff.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the semantic-core CLI and return a process status code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            contracts = build_r1_contracts(
                R1SourceSet(
                    repo_root=args.repo_root,
                    family_profile=args.family_profile,
                    sls2_generation=args.sls2_generation,
                    sls2_semantics=args.sls2_semantics,
                    sls2_review=args.sls2_review,
                )
            )
            bundle = write_r1_bundle(contracts, args.output_root)
            _emit(
                {
                    "status": "pass",
                    "bundle_id": bundle.bundle_id,
                    "content_sha256": bundle.content_sha256,
                    "bundle_path": str(bundle.path),
                }
            )
            return 0
        if args.command == "validate":
            grammar = load_family_grammar(args.grammar)
            graphs = [load_instance_boundary_graph(path) for path in args.graphs]
            for graph in graphs:
                validate_graph_against_grammar(grammar, graph)
            _emit(
                {
                    "status": "pass",
                    "grammar_id": grammar.grammar_id,
                    "grammar_sha256": canonical_sha256(grammar.to_mapping()),
                    "validated_graph_ids": [graph.graph_id for graph in graphs],
                }
            )
            return 0
        if args.command == "diff":
            left = load_instance_boundary_graph(args.left)
            right = load_instance_boundary_graph(args.right)
            mapping = diff_instance_graphs(left, right).to_mapping()
            if args.output is None:
                _emit(mapping)
            else:
                output = args.output.resolve()
                if output.exists():
                    raise FileExistsError(f"semantic graph diff already exists: {output}")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(canonical_json_bytes(mapping) + b"\n")
                _emit(
                    {
                        "status": "pass",
                        "output": str(output),
                        "canonical_payload_sha256": canonical_sha256(mapping),
                    }
                )
            return 0
    except (OSError, SemanticContractError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 2


def _emit(value: object) -> None:
    print(canonical_json_bytes(value).decode("utf-8"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
