"""Command-line interface for no-CST family-profile construction and validation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .adapters import Rf500FamilyInstanceAdapter, Sls2FamilyInstanceAdapter
from .builder import build_family_profile, write_stage_c_bundle
from .core import (
    FAMILY_ID,
    FamilyProfileError,
    canonical_sha256,
    load_profile,
    verify_round_trip,
)


def _adapter_for_id(adapter_id: str):
    if adapter_id == Sls2FamilyInstanceAdapter.adapter_id:
        return Sls2FamilyInstanceAdapter()
    if adapter_id == Rf500FamilyInstanceAdapter.adapter_id:
        return Rf500FamilyInstanceAdapter()
    raise FamilyProfileError(f"unsupported adapter id in profile: {adapter_id}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.family_profile",
        description="Build and validate a no-CST RF-CEM family profile.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build a profile from two frozen manifests.")
    build.add_argument("--sls2-baseline-manifest", type=Path, required=True)
    build.add_argument("--rf500-instance-manifest", type=Path, required=True)
    output = build.add_mutually_exclusive_group(required=True)
    output.add_argument("--output-dir", type=Path)
    output.add_argument(
        "--proof-root",
        type=Path,
        help="Create the non-overwriting family-id/hash-prefixed proof directory below this root.",
    )
    validate = subparsers.add_parser("validate", help="Validate an existing profile JSON.")
    validate.add_argument("--profile", type=Path, required=True)
    return parser


def _run_build(args: argparse.Namespace) -> int:
    profile, roundtrip, source_bindings = build_family_profile(
        args.sls2_baseline_manifest,
        args.rf500_instance_manifest,
    )
    profile_hash = canonical_sha256(profile.to_mapping())
    if args.proof_root is not None:
        output_dir = args.proof_root / f"{FAMILY_ID}.{profile_hash[:8]}"
    else:
        output_dir = args.output_dir
    hashes = write_stage_c_bundle(output_dir, profile, roundtrip, source_bindings)
    print(f"profile={output_dir / 'family_profile.v0.json'}")
    print(f"profile_canonical_sha256={hashes['profile_canonical_sha256']}")
    print(f"profile_raw_sha256={hashes['profile_raw_sha256']}")
    print(f"instance_count={len(profile.instances)}")
    print(f"roundtrip_all_passed={roundtrip['all_passed']}")
    print(
        "family_profile_validation_canonical_sha256="
        f"{hashes['family_profile_validation_canonical_sha256']}"
    )
    print(
        "adapter_roundtrip_report_canonical_sha256="
        f"{hashes['adapter_roundtrip_report_canonical_sha256']}"
    )
    print(f"source_binding_manifest_raw_sha256={hashes['source_binding_manifest_raw_sha256']}")
    print(
        "source_binding_manifest_canonical_sha256="
        f"{hashes['source_binding_manifest_canonical_sha256']}"
    )
    print("cst=not_run")
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    roundtrip = []
    for instance in profile.instances:
        adapter = _adapter_for_id(instance.parameter_payload["adapter_id"])
        roundtrip.append(verify_round_trip(adapter, instance))
    print("OK: family profile is valid")
    print(f"family_id={profile.family_id}")
    print(f"instance_count={len(profile.instances)}")
    print(f"profile_canonical_sha256={canonical_sha256(profile.to_mapping())}")
    print(f"roundtrip_all_passed={all(item['passed'] for item in roundtrip)}")
    print("cst=not_run")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the family-profile build or validation command."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return _run_build(args)
        if args.command == "validate":
            return _run_validate(args)
    except (FamilyProfileError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
