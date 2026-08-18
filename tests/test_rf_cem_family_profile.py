"""No-CST tests for the generic RF-CEM family profile contract."""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import stat

import pytest

from rf_cem.family_profile import (
    EXCLUDED_METRICS,
    FAMILY_ID,
    FAMILY_IDENTITY,
    FamilyProfileError,
    Rf500FamilyInstanceAdapter,
    Sls2FamilyInstanceAdapter,
    canonical_sha256,
    load_family_profile_schema,
    make_family_profile,
    validate_profile_mapping,
    verify_round_trip,
)
from rf_cem.family_profile.core import FamilyInstance
from rf_cem.family_profile.cli import main as family_profile_main


pytestmark = pytest.mark.no_cst


def _evidence() -> dict[str, object]:
    return {
        "bundle_relative_path": "fixture/source.json",
        "locator": "#/fixture",
        "source_file_sha256": "a" * 64,
    }


def _instance(
    instance_id: str,
    *,
    adapter_id: str = "fixture_adapter.v0",
    native_payload: dict[str, object] | None = None,
    groups: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    payload = native_payload or {"alpha": 1.0, "beta": 2.0}
    parameter_groups = groups or {
        "fixture_parameters": {
            "values": deepcopy(payload),
            "count": len(payload),
            "scope": "fixture",
        }
    }
    counts = {name: group["count"] for name, group in parameter_groups.items()}
    counts["total"] = sum(counts.values())
    instance = {
        "schema_version": "family_instance.v0",
        "instance_id": instance_id,
        "family_id": FAMILY_ID,
        "source_binding": {
            "manifest_id": f"manifest.{instance_id}",
            "manifest_schema_version": "fixture_manifest.v0",
            "manifest_raw_sha256": "b" * 64,
            "artifacts": [
                {
                    "bundle_relative_path": "fixture/source.json",
                    "raw_sha256": "a" * 64,
                }
            ],
        },
        "native_schema": f"fixture_schema.{instance_id}",
        "native_model_type": "fixture_model",
        "native_variant": "fixture_variant",
        "native_units": {"length": "mm"},
        "parameter_payload": {
            "adapter_id": adapter_id,
            "native_schema_version": "fixture_native.v0",
            "native_payload": deepcopy(payload),
            "native_payload_locator": "fixture/source.json#/payload",
            "native_payload_canonical_sha256": canonical_sha256(payload),
            "source_artifact_raw_sha256": "a" * 64,
            "parameter_groups": parameter_groups,
            "parameter_count": counts,
            "units": {"length": "mm"},
            "scope": "fixture_parameter_scope",
            "source_refs": [_evidence()],
        },
        "geometry_artifacts": [
            {
                "role": "fixture_geometry",
                "bundle_relative_path": "fixture/geometry.step",
                "raw_sha256": "c" * 64,
            }
        ],
        "validation_layers": {
            "payload_schema_validation": {"status": "pass"},
            "parameter_validation": {"status": "pass"},
            "geometry_generation": {"status": "pending"},
            "geometry_validation": {"status": "pass"},
            "human_review": {"status": "pass"},
            "helper2_review": {"status": "partial"},
            "live_cst": {"status": "not_linked"},
            "physical_acceptance": {"status": "not_established"},
        },
        "family_assertion_evidence": {
            key: {
                "claim": claim,
                "status": "supported",
                "evidence": [_evidence()],
            }
            for key, claim in FAMILY_IDENTITY.items()
        },
        "provenance": {"fixture": True},
        "live_cst": {"status": "not_linked"},
        "physical_acceptance": {"status": "not_established"},
    }
    return instance


def _profile_mapping(*instances: dict[str, object]) -> dict[str, object]:
    profile = make_family_profile([FamilyInstance.from_mapping(item) for item in instances])
    return profile.to_mapping()


def _write_json_fixture(path: Path, value: dict[str, object]) -> tuple[str, str]:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(path.stat().st_mode & ~0o222)
    return __import__("hashlib").sha256(raw).hexdigest(), canonical_sha256(value)


def _write_bytes_fixture(path: Path, value: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    path.chmod(path.stat().st_mode & ~0o222)
    return __import__("hashlib").sha256(value).hexdigest()


def _make_rf500_source_fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "rf500_source"
    source_path = str((root / "unknown_source.step").resolve())
    payload: dict[str, object] = {
        "schema_version": "parametric_geometry.v0",
        "model_type": "fixture_axisymmetric_model",
        "variant": {"name": "fixture_variant", "selection_role": "candidate"},
        "units": {"frequency": "MHz", "length": "mm", "time": "ns"},
        "named_parameters": {
            "alpha": {"value": 1.0, "unit": "mm", "required": True},
            "beta": {"value": 2.0, "unit": "mm", "required": True},
        },
        "derived_parameters": {
            "gamma": {"value": 3.0, "unit": "mm", "parameter_role": "derived"},
        },
        "unknown_native_field": {
            "absolute_path": source_path,
            "nested": {"keep": "unchanged", "values": [1, 2, 3]},
        },
        "unknown_scalar": "must_survive",
    }
    payload_rel = "source/parametric_geometry.v0.json"
    payload_raw, payload_canonical = _write_json_fixture(root / payload_rel, payload)
    geometry_validation_raw, _ = _write_json_fixture(
        root / "source/geometry_validation.json", {"valid": True}
    )
    udsg_raw, _ = _write_json_fixture(root / "source/udsg.v0.json", {"faces": []})
    step_raw = _write_bytes_fixture(root / "source/generated_vacuum.step", b"fixture-step")
    payload_evidence = {
        "bundle_relative_path": payload_rel,
        "locator": "#/",
        "source_file_sha256": payload_raw,
        "canonical_payload_sha256": payload_canonical,
    }
    family_assertions = {}
    for key, claim in FAMILY_IDENTITY.items():
        family_assertions[key] = {
            "claim": "RF-vacuum geometry" if key == "geometry_scope" else claim,
            "evidence": [payload_evidence],
        }
    manifest: dict[str, object] = {
        "schema_version": "instance_source_manifest.v0",
        "instance_source_id": "fixture.rf500",
        "source_payload": {
            "raw_sha256": payload_raw,
            "canonical_json_sha256": payload_canonical,
            "schema_version": payload["schema_version"],
            "model_type_original": payload["model_type"],
            "named_parameter_count": len(payload["named_parameters"]),
            "derived_parameter_count": len(payload["derived_parameters"]),
            "units_original": payload["units"],
            "variant_original": payload["variant"],
        },
        "family_assertions": family_assertions,
        "validation_layers": {
            "payload_schema_validation": {"status": "pass"},
            "parameter_validation": {"status": "pass"},
            "geometry_generation": {"status": "pass"},
            "geometry_validation": {"status": "pass"},
            "human_review": {"status": "pass"},
            "helper2_review": {"status": "partial"},
            "live_cst": {"status": "not_linked"},
            "physical_acceptance": {"status": "not_established"},
        },
        "artifacts": [
            {"bundle_relative_path": payload_rel, "source_file_sha256": payload_raw, "canonical_payload_sha256": payload_canonical},
            {"bundle_relative_path": "source/generated_vacuum.step", "source_file_sha256": step_raw},
            {"bundle_relative_path": "source/geometry_validation.json", "source_file_sha256": geometry_validation_raw},
            {"bundle_relative_path": "source/udsg.v0.json", "source_file_sha256": udsg_raw},
        ],
    }
    manifest_path = root / "instance_source_manifest.v0.json"
    _write_json_fixture(manifest_path, manifest)
    return {
        "root": root,
        "manifest": manifest_path,
        "payload": payload,
        "payload_canonical": payload_canonical,
    }


def _make_sls2_source_fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "sls2_source"
    values = {"alpha": 1.0, "beta": 2.0, "gamma": 3.0}
    generation = {
        "schema_version": "generation.core.v0",
        "candidate_id": "fixture.candidate",
        "parameter_tuple": {
            "origin": "published_candidate",
            "unit": "mm",
            "values": values,
        },
        "features": {"model_type": "fixture_sls_model", "axis": "z", "feature_candidates": [{"type": "RFVacuumVolume"}]},
        "validation": {"pass": True},
    }
    semantics = {
        "request_context": {
            "operating_regime": "normal_conducting",
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
        },
        "classification": {"cell_count": "single"},
    }
    review_payload_hash = canonical_sha256({"fixture_review": True})
    session = {"revision": 1, "review_scope": {"payload_sha256": review_payload_hash}}
    artifacts: list[dict[str, object]] = []
    for relative, value in (
        ("generation.core.json", generation),
        ("review_session.v1.json", session),
        ("literature_semantics.v0.json", semantics),
        ("helper2_face_mesh.json", {"faces": []}),
    ):
        raw, canonical = _write_json_fixture(root / relative, value)
        artifacts.append(
            {
                "bundle_relative_path": relative,
                "raw_sha256": raw,
                "canonical_sha256": canonical,
            }
        )
    step_raw = _write_bytes_fixture(root / "cavity.step", b"fixture-cavity-step")
    artifacts.append({"bundle_relative_path": "cavity.step", "raw_sha256": step_raw})
    manifest: dict[str, object] = {
        "schema_version": "baseline_manifest.v0",
        "baseline_id": "fixture.sls2",
        "operating_regime": "normal_conducting",
        "revision": 1,
        "live_cst": "not_run",
        "physical_acceptance": "not_established",
        "source_binding_hashes": {"payload_sha256": review_payload_hash},
        "truth_layers": {"geometry_generation": {"generation_review_status": "pending"}},
        "frozen_files": artifacts,
    }
    manifest_path = root / "baseline_manifest.v0.json"
    _write_json_fixture(manifest_path, manifest)
    return {"root": root, "manifest": manifest_path, "values": values}


def test_schema_is_generic_and_contains_instance_definition() -> None:
    schema = load_family_profile_schema()
    text = json.dumps(schema, ensure_ascii=False, sort_keys=True)

    assert schema["$defs"]["family_instance.v0"]["type"] == "object"
    assert schema["properties"]["instances"]["minItems"] == 1
    assert "sls2.r149.6593e02e" not in text
    assert "rf500.2c27faee.b1r3" not in text
    assert "500mhz" not in text
    assert "free_equator_smooth" not in text
    assert all(f'"{name}"' not in text for name in ("L", "l", "r", "R", "a", "b"))
    assert "fixed_parameter_count" not in text


def test_schema_accepts_different_parameter_dimensions_and_native_schemas() -> None:
    first = _instance("fixture.one")
    third = _instance(
        "fixture.three",
        native_payload={"gamma": 3.0, "delta": 4.0, "epsilon": 5.0},
        groups={
            "other_group": {
                "values": {"gamma": 3.0, "delta": 4.0, "epsilon": 5.0},
                "count": 3,
                "scope": "other_scope",
            }
        },
    )
    profile = _profile_mapping(first, third)

    validate_profile_mapping(profile)
    assert profile["instances"][0]["parameter_payload"]["parameter_count"]["total"] == 2
    assert profile["instances"][1]["parameter_payload"]["parameter_count"]["other_group"] == 3


def test_native_units_and_named_derived_groups_are_preserved() -> None:
    native = {"named": {"value": 1.0}, "derived": {"value": 2.0}}
    groups = {
        "named_parameters": {"values": native["named"], "count": 1, "scope": "named"},
        "derived_parameters": {"values": native["derived"], "count": 1, "scope": "derived"},
    }
    instance = _instance("fixture.groups", native_payload=native, groups=groups)
    instance["native_units"] = {"frequency": "MHz", "length": "mm", "time": "ns"}
    instance["parameter_payload"]["units"] = {"frequency": "MHz", "length": "mm", "time": "ns"}
    FamilyInstance.from_mapping(instance).validate()
    assert instance["parameter_payload"]["parameter_groups"].keys() == groups.keys()
    assert instance["native_units"]["time"] == "ns"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["instances"].append(deepcopy(value["instances"][0])),
        lambda value: value["instances"][0].update({"family_id": "other_family"}),
        lambda value: value["instances"][0]["validation_layers"].update(
            {"geometry_generation": {"status": "unknown"}}
        ),
        lambda value: value["instances"][0].pop("source_binding"),
        lambda value: value["instances"][0]["source_binding"]["artifacts"][0].update(
            {"raw_sha256": "bad"}
        ),
        lambda value: value["scope"].update({"executable_family_objectives": ["R/Q"]}),
    ],
)
def test_invalid_profile_inputs_are_rejected(mutator) -> None:
    value = _profile_mapping(_instance("fixture.invalid"))
    mutator(value)
    with pytest.raises(FamilyProfileError):
        validate_profile_mapping(value)


def test_nan_and_infinity_are_rejected() -> None:
    value = _profile_mapping(_instance("fixture.nonfinite"))
    value["instances"][0]["parameter_payload"]["native_payload"]["alpha"] = math.nan
    with pytest.raises(FamilyProfileError, match="NaN|Infinity|canonical"):
        validate_profile_mapping(value)


def test_metric_exclusions_do_not_become_family_objectives() -> None:
    value = _profile_mapping(_instance("fixture.metrics"))
    assert set(EXCLUDED_METRICS).issubset(set(value["exclusions"]))
    assert value["scope"]["executable_family_objectives"] == []


def test_without_source_context_cannot_claim_native_round_trip() -> None:
    sls_instance = FamilyInstance.from_mapping(
        _instance("fixture.sls", adapter_id=Sls2FamilyInstanceAdapter.adapter_id)
    )
    rf_instance = FamilyInstance.from_mapping(
        _instance("fixture.rf", adapter_id=Rf500FamilyInstanceAdapter.adapter_id)
    )

    sls_result = verify_round_trip(Sls2FamilyInstanceAdapter(), sls_instance)
    rf_result = verify_round_trip(Rf500FamilyInstanceAdapter(), rf_instance)
    assert sls_result["passed"] is False
    assert rf_result["passed"] is False
    assert sls_result["source_roundtrip"] == "not_run"
    assert rf_result["source_roundtrip"] == "not_run"
    assert sls_result["portable_projection_validation"] == "passed"
    assert rf_result["portable_projection_validation"] == "passed"


def test_validate_cli_without_manifests_reports_structural_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            _profile_mapping(
                _instance("fixture.sls", adapter_id=Sls2FamilyInstanceAdapter.adapter_id),
                _instance("fixture.rf", adapter_id=Rf500FamilyInstanceAdapter.adapter_id),
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert family_profile_main(["validate", "--profile", str(profile_path)]) == 0
    output = capsys.readouterr().out
    assert "structural_validation=passed" in output
    assert "portable_projection_validation=passed" in output
    assert "source_roundtrip=not_run" in output
    assert "roundtrip_all_passed=False" in output


def test_sls2_source_adapter_round_trip_does_not_require_a_fixed_dimension_count(
    tmp_path: Path,
) -> None:
    source = _make_sls2_source_fixture(tmp_path)
    adapter = Sls2FamilyInstanceAdapter(source["manifest"])
    instance = adapter.build_instance()
    result = verify_round_trip(adapter, instance)

    assert len(instance.parameter_payload["native_payload"]) == 3
    assert result["passed"] is True
    assert result["source_backed"] is True
    assert result["input_native_payload_canonical_sha256"] == result[
        "restored_native_payload_canonical_sha256"
    ]
    assert all(result["preservation_checks"].values())


def test_rf500_source_bound_restore_is_lossless_and_keeps_projection_separate(
    tmp_path: Path,
) -> None:
    source = _make_rf500_source_fixture(tmp_path)
    adapter = Rf500FamilyInstanceAdapter(source["manifest"])
    instance = adapter.build_instance()
    result = verify_round_trip(adapter, instance)

    assert result["passed"] is True
    assert result["source_backed"] is True
    assert result["input_native_payload_canonical_sha256"] == source["payload_canonical"]
    assert result["restored_native_payload_canonical_sha256"] == source["payload_canonical"]
    assert result["portable_projection_canonical_sha256"] != source["payload_canonical"]
    assert all(result["preservation_checks"].values())
    assert instance.parameter_payload["native_payload"]["unknown_native_field"]["nested"] == {
        "keep": "unchanged",
        "values": [1, 2, 3],
    }
    assert not any(
        str(value).startswith(("C:\\", "/"))
        for value in json.dumps(instance.to_mapping(), ensure_ascii=False).split('"')
    )


@pytest.mark.parametrize("mutation", ["change", "drop"])
def test_rf500_unknown_native_projection_change_is_rejected(
    tmp_path: Path, mutation: str
) -> None:
    source = _make_rf500_source_fixture(tmp_path)
    adapter = Rf500FamilyInstanceAdapter(source["manifest"])
    instance = adapter.build_instance()
    if mutation == "change":
        instance.parameter_payload["native_payload"]["unknown_scalar"] = "changed"
    else:
        instance.parameter_payload["native_payload"].pop("unknown_native_field")

    with pytest.raises(FamilyProfileError, match="portable projection hash mismatch"):
        verify_round_trip(adapter, instance)


def test_rf500_source_canonical_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    source = _make_rf500_source_fixture(tmp_path)
    adapter = Rf500FamilyInstanceAdapter(source["manifest"])
    instance = adapter.build_instance()
    payload_path = source["root"] / "source/parametric_geometry.v0.json"
    payload = deepcopy(source["payload"])
    payload["unknown_scalar"] = "source changed"
    os.chmod(payload_path, stat.S_IREAD | stat.S_IWRITE)
    payload_path.write_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    payload_path.chmod(payload_path.stat().st_mode & ~0o222)

    with pytest.raises(FamilyProfileError, match="raw hash mismatch|canonical hash mismatch"):
        adapter.restore_native_payload(instance)
