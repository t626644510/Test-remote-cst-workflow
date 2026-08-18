"""No-CST tests for the generic RF-CEM family profile contract."""

from __future__ import annotations

from copy import deepcopy
import json
import math

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


def test_sls2_and_rf500_adapter_round_trip_contract_on_portable_instances() -> None:
    sls_instance = FamilyInstance.from_mapping(
        _instance("fixture.sls", adapter_id=Sls2FamilyInstanceAdapter.adapter_id)
    )
    rf_instance = FamilyInstance.from_mapping(
        _instance("fixture.rf", adapter_id=Rf500FamilyInstanceAdapter.adapter_id)
    )

    sls_result = verify_round_trip(Sls2FamilyInstanceAdapter(), sls_instance)
    rf_result = verify_round_trip(Rf500FamilyInstanceAdapter(), rf_instance)
    assert sls_result["passed"] is True
    assert rf_result["passed"] is True
    assert sls_result["input_native_payload_canonical_sha256"] == sls_result[
        "restored_native_payload_canonical_sha256"
    ]
    assert rf_result["input_native_payload_canonical_sha256"] == rf_result[
        "restored_native_payload_canonical_sha256"
    ]
