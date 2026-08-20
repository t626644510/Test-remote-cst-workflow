"""Command-line entry points for the no-CST R2 boundary compiler."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from rf_cem.semantic.contracts import canonical_json_bytes, file_sha256

from .adapters import R2SourceSet
from .artifacts import write_r2_bundle
from .contracts import CompileContractError, load_compile_record


def build_parser() -> argparse.ArgumentParser:
    """Return the R2 compiler CLI parser."""

    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.compiler",
        description="Build and validate RF-CEM R2 compile records without CST.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser(
        "build", help="compile both canonical instances into one immutable R2 bundle"
    )
    build.add_argument("--repo-root", type=Path, required=True)
    build.add_argument("--family-profile", type=Path, required=True)
    build.add_argument("--family-grammar", type=Path, required=True)
    build.add_argument(
        "--instance-boundary-graph",
        type=Path,
        action="append",
        required=True,
        dest="instance_graphs",
    )
    build.add_argument("--sls2-generation", type=Path, required=True)
    build.add_argument("--sls2-baseline-step", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="strictly validate compile records and their output artifact hashes"
    )
    validate.add_argument(
        "--record", type=Path, action="append", required=True, dest="records"
    )
    validate.add_argument("--bundle-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the compiler CLI and return a process status code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            bundle = write_r2_bundle(
                R2SourceSet(
                    repo_root=args.repo_root,
                    family_profile=args.family_profile,
                    family_grammar=args.family_grammar,
                    instance_graphs=tuple(args.instance_graphs),
                    sls2_generation=args.sls2_generation,
                    sls2_baseline_step=args.sls2_baseline_step,
                ),
                args.output_root,
            )
            _emit(
                {
                    "status": "pass",
                    "bundle_id": bundle.bundle_id,
                    "input_sha256": bundle.input_sha256,
                    "bundle_path": str(bundle.path),
                    "compile_records": [
                        {
                            "instance_id": record.instance_id,
                            "compile_id": record.compile_id,
                            "content_sha256": record.content_sha256,
                            "region_count": len(record.region_geometries),
                            "patch_count": record.patch_count,
                        }
                        for record in bundle.records
                    ],
                    "live_cst_status": "not_run",
                }
            )
            return 0
        if args.command == "validate":
            root = args.bundle_root.resolve()
            records = [load_compile_record(path) for path in args.records]
            for record in records:
                for artifact in record.output_artifacts:
                    path = (root / Path(artifact.path)).resolve()
                    try:
                        path.relative_to(root)
                    except ValueError as exc:
                        raise CompileContractError(
                            "compile artifact path escapes bundle root"
                        ) from exc
                    if not path.is_file():
                        raise CompileContractError(
                            f"compile output artifact is missing: {artifact.path}"
                        )
                    if file_sha256(path) != artifact.raw_sha256:
                        raise CompileContractError(
                            f"compile output artifact raw hash mismatch: {artifact.path}"
                        )
                    if path.stat().st_size != artifact.size_bytes:
                        raise CompileContractError(
                            f"compile output artifact size mismatch: {artifact.path}"
                        )
            _emit(
                {
                    "status": "pass",
                    "validated_compile_ids": [record.compile_id for record in records],
                    "validated_artifact_count": sum(
                        len(record.output_artifacts) for record in records
                    ),
                    "live_cst_status": "not_run",
                }
            )
            return 0
    except (OSError, CompileContractError, FileExistsError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 2


def _emit(value: object) -> None:
    print(canonical_json_bytes(value).decode("utf-8"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
