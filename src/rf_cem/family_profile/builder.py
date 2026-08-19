"""Build deterministic two-instance family profiles and proof reports."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from .adapters import Rf500FamilyInstanceAdapter, Sls2FamilyInstanceAdapter
from .core import (
    FAMILY_ID,
    FAMILY_IDENTITY,
    FamilyInstance,
    FamilyProfile,
    FamilyProfileError,
    canonical_sha256,
    make_family_profile,
    verify_round_trip,
    write_profile,
)


def build_family_profile(
    sls2_baseline_manifest: Path,
    rf500_instance_manifest: Path,
) -> tuple[FamilyProfile, dict[str, Any], dict[str, Any]]:
    """Build the generic profile from the two supplied frozen manifests.

    JSON Schema remains open to one or more instances.  This Stage C builder
    deliberately requires two independently adapted inputs so the real proof
    demonstrates cross-native-schema reuse.
    """

    sls2_adapter = Sls2FamilyInstanceAdapter(sls2_baseline_manifest)
    rf500_adapter = Rf500FamilyInstanceAdapter(rf500_instance_manifest)
    instances = [sls2_adapter.build_instance(), rf500_adapter.build_instance()]
    if len({item.instance_id for item in instances}) != len(instances):
        raise FamilyProfileError("Stage C source instances must have unique IDs")
    if any(item.family_id != FAMILY_ID for item in instances):
        raise FamilyProfileError("Stage C source instances do not share the canonical family ID")
    profile = make_family_profile(instances)
    roundtrip = {
        "schema_version": "adapter_roundtrip_report.v0",
        "profile_family_id": FAMILY_ID,
        "instances": [
            verify_round_trip(sls2_adapter, instances[0]),
            verify_round_trip(rf500_adapter, instances[1]),
        ],
        "all_passed": False,
    }
    roundtrip["all_passed"] = all(item["passed"] for item in roundtrip["instances"])
    roundtrip["source_roundtrip"] = (
        "passed" if roundtrip["all_passed"] else "failed"
    )
    source_bindings = build_source_binding_manifest(profile)
    return profile, roundtrip, source_bindings


def build_source_binding_manifest(profile: FamilyProfile) -> dict[str, Any]:
    """Return a deterministic portable manifest of all consumed source hashes."""

    profile.validate()
    return {
        "schema_version": "source_binding_manifest.v0",
        "family_id": profile.family_id,
        "family_identity": deepcopy(profile.family_identity),
        "instances": [
            {
                "instance_id": instance.instance_id,
                "manifest_id": instance.source_binding["manifest_id"],
                "manifest_schema_version": instance.source_binding["manifest_schema_version"],
                "manifest_raw_sha256": instance.source_binding["manifest_raw_sha256"],
                "artifacts": deepcopy(instance.source_binding["artifacts"]),
            }
            for instance in profile.instances
        ],
    }


def build_validation_report(
    profile: FamilyProfile,
    roundtrip: dict[str, Any],
    *,
    profile_raw_sha256: str,
    profile_canonical_sha256: str,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return validation evidence for a built profile.

    The profile remains deterministic; execution metadata is intentionally
    optional and belongs only in this report because it may contain a time.
    """

    profile.validate()
    if len(profile.instances) != 2:
        raise FamilyProfileError("Stage C validation report requires exactly two real instances")
    instance_checks = []
    for instance in profile.instances:
        instance_checks.append(
            {
                "instance_id": instance.instance_id,
                "family_id": instance.family_id,
                "family_identity": deepcopy(FAMILY_IDENTITY),
                "family_assertion_evidence": deepcopy(instance.family_assertion_evidence),
                "parameter_count": deepcopy(instance.parameter_payload["parameter_count"]),
                "native_units": deepcopy(instance.native_units),
                "geometry_artifact_count": len(instance.geometry_artifacts),
                "validation_layer_names": list(instance.validation_layers),
                "live_cst": instance.live_cst["status"],
                "physical_acceptance": instance.physical_acceptance["status"],
                "native_payload_canonical_sha256": instance.parameter_payload[
                    "native_payload_canonical_sha256"
                ],
                "source_payload_canonical_sha256": instance.parameter_payload.get(
                    "source_payload_canonical_sha256"
                ),
                "portable_projection_canonical_sha256": instance.parameter_payload.get(
                    "portable_projection_canonical_sha256"
                ),
            }
        )
    report = {
        "schema_version": "family_profile_validation.v0",
        "family_id": FAMILY_ID,
        "family_identity": deepcopy(FAMILY_IDENTITY),
        "profile_instance_count": len(profile.instances),
        "profile_raw_sha256": profile_raw_sha256,
        "profile_canonical_sha256": profile_canonical_sha256,
        "adapter_roundtrip_all_passed": bool(roundtrip.get("all_passed")),
        "checks": {
            "two_real_instances": True,
            "shared_family_id": len({item.family_id for item in profile.instances}) == 1,
            "shared_family_identity": all(
                set(item.family_assertion_evidence) == set(FAMILY_IDENTITY)
                for item in profile.instances
            ),
            "native_units_present": all(
                bool(item.native_units) and bool(item.parameter_payload["units"])
                for item in profile.instances
            ),
            "geometry_artifact_binding_present": all(
                bool(item.geometry_artifacts) for item in profile.instances
            ),
            "validation_layers_preserved": all(
                len(item.validation_layers) == 8 for item in profile.instances
            ),
            "live_or_physical_acceptance_not_upgraded": all(
                item.live_cst["status"] in {"not_run", "not_linked"}
                and item.physical_acceptance["status"] == "not_established"
                for item in profile.instances
            ),
            "metric_contract_excluded": profile.metric_contract_status
            == "excluded_pending_definition",
            "source_roundtrip_all_passed": bool(roundtrip.get("all_passed"))
            and all(
                item.get("source_backed") is True
                and item.get("source_roundtrip") == "passed"
                for item in roundtrip.get("instances", [])
            ),
        },
        "instances": instance_checks,
        "source_inputs": [
            {
                "instance_id": instance.instance_id,
                "manifest_id": instance.source_binding["manifest_id"],
                "manifest_raw_sha256": instance.source_binding["manifest_raw_sha256"],
                "native_payload_locator": instance.parameter_payload[
                    "native_payload_locator"
                ],
                "input_native_payload_canonical_sha256": next(
                    item["input_native_payload_canonical_sha256"]
                    for item in roundtrip["instances"]
                    if item["instance_id"] == instance.instance_id
                ),
                "restored_native_payload_canonical_sha256": next(
                    item["restored_native_payload_canonical_sha256"]
                    for item in roundtrip["instances"]
                    if item["instance_id"] == instance.instance_id
                ),
                "source_backed": next(
                    item["source_backed"]
                    for item in roundtrip["instances"]
                    if item["instance_id"] == instance.instance_id
                ),
                "passed": next(
                    item["passed"]
                    for item in roundtrip["instances"]
                    if item["instance_id"] == instance.instance_id
                ),
            }
            for instance in profile.instances
        ],
    }
    if execution is not None:
        report["execution"] = deepcopy(execution)
    return report


def write_json_report(path: Path, payload: dict[str, Any]) -> str:
    """Write a deterministic proof report and return its raw SHA-256."""

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def write_stage_c_bundle(
    output_dir: Path,
    profile: FamilyProfile,
    roundtrip: dict[str, Any],
    source_bindings: dict[str, Any],
    *,
    execution: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write the four proof files into a new directory without overwriting."""

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FamilyProfileError(f"proof output directory already exists: {output_dir.name}")
    output_dir.mkdir(parents=True)
    profile_raw, profile_canonical = write_profile(output_dir / "family_profile.v0.json", profile)
    validation = build_validation_report(
        profile,
        roundtrip,
        profile_raw_sha256=profile_raw,
        profile_canonical_sha256=profile_canonical,
        execution=execution,
    )
    validation_raw = write_json_report(
        output_dir / "family_profile_validation.v0.json", validation
    )
    roundtrip_raw = write_json_report(
        output_dir / "adapter_roundtrip_report.v0.json", roundtrip
    )
    proof_manifest = deepcopy(source_bindings)
    proof_manifest["proof_files"] = [
        {
            "bundle_relative_path": "family_profile.v0.json",
            "raw_sha256": profile_raw,
            "canonical_sha256": profile_canonical,
        },
        {
            "bundle_relative_path": "family_profile_validation.v0.json",
            "raw_sha256": validation_raw,
            "canonical_sha256": canonical_sha256(validation),
        },
        {
            "bundle_relative_path": "adapter_roundtrip_report.v0.json",
            "raw_sha256": roundtrip_raw,
            "canonical_sha256": canonical_sha256(roundtrip),
        },
    ]
    proof_manifest["self_hash_policy"] = (
        "raw and canonical SHA-256 for this manifest are reported outside the file "
        "to avoid self-reference"
    )
    source_raw = write_json_report(
        output_dir / "source_binding_manifest.v0.json", proof_manifest
    )
    source_canonical = canonical_sha256(proof_manifest)
    for path in output_dir.iterdir():
        if path.is_file():
            try:
                path.chmod(path.stat().st_mode & ~0o222)
            except OSError:
                pass
    return {
        "profile_raw_sha256": profile_raw,
        "profile_canonical_sha256": profile_canonical,
        "family_profile_validation_raw_sha256": validation_raw,
        "family_profile_validation_canonical_sha256": canonical_sha256(validation),
        "adapter_roundtrip_report_raw_sha256": roundtrip_raw,
        "adapter_roundtrip_report_canonical_sha256": canonical_sha256(roundtrip),
        "source_binding_manifest_raw_sha256": source_raw,
        "source_binding_manifest_canonical_sha256": source_canonical,
    }


__all__ = [
    "build_family_profile",
    "build_source_binding_manifest",
    "build_validation_report",
    "write_json_report",
    "write_stage_c_bundle",
]
