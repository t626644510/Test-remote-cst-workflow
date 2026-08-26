"""No-CST contract tests for the RF-CEM Workbench W0 read model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
from typing import Iterator

import pytest

from rf_cem.family_profile import (
    FAMILY_ID,
    FAMILY_IDENTITY,
    canonical_sha256,
    make_family_profile,
)
from rf_cem.family_profile.core import FamilyInstance
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchIndexError,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)
from rf_cem.workbench.cli import main as workbench_main


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "workbench-test-token-0123456789"


@pytest.fixture
def repository_source_dir() -> Iterator[Path]:
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workbench-test-", dir=scratch) as value:
        yield Path(value)
    try:
        scratch.rmdir()
    except OSError:
        pass


@pytest.fixture
def source_set(repository_source_dir: Path) -> WorkbenchSourceSet:
    profile_path = repository_source_dir / "family_profile.v0.json"
    semantics_path = repository_source_dir / "literature_semantics.v0.json"
    review_path = repository_source_dir / "review_session.v1.json"
    _write_json(
        profile_path,
        _profile_mapping(
            _instance("sls2.r149.6593e02e"),
            _instance("rf500.2c27faee.b1r3"),
        ),
    )
    _write_json(semantics_path, _semantic_package())
    _write_json(review_path, _review_session())
    return WorkbenchSourceSet(
        repo_root=ROOT,
        family_profile=profile_path,
        literature_packages=(semantics_path,),
        review_sessions=(review_path,),
    )


def test_rebuild_is_deterministic_and_indexes_w0_catalog(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    database = tmp_path / "workbench.sqlite"
    first = rebuild_workbench(database, source_set)
    first_snapshot = RegistryReader(database).snapshot()
    second = rebuild_workbench(database, source_set)
    second_snapshot = RegistryReader(database).snapshot()

    assert first.input_set_sha256 == second.input_set_sha256
    assert first_snapshot == second_snapshot
    entities = {
        (item["entity_kind"], item["entity_id"]): item
        for item in second_snapshot["entities"]
    }
    assert ("family", FAMILY_ID) in entities
    assert ("instance", "sls2.r149.6593e02e") in entities
    assert ("instance", "rf500.2c27faee.b1r3") in entities
    assert ("compile_record", "legacy:sls2.r149.6593e02e") in entities
    assert ("compile_record", "legacy:rf500.2c27faee.b1r3") in entities
    assert any(key[0] == "semantic" and "helper2" in key[1] for key in entities)
    assert ("semantic", "literature:paper1:classification") in entities
    assert any(key[0] == "representation" for key in entities)
    assert any(key[0] == "algorithm" for key in entities)
    assert any(key[0] == "roadmap_gate" for key in entities)
    assert any(key[0] == "capability" for key in entities)
    assert entities[("roadmap_gate", "R0B.no_cst_regression")]["status"] == "passed"
    assert entities[("roadmap_phase", "R4")]["status"] == (
        "hard_gate_passed_merged"
    )
    assert entities[("roadmap_phase", "R5")]["status"] == (
        "paused_or_deferred_by_user"
    )
    for capability_id in (
        "technical_debt.td1_continuity",
        "technical_debt.td2_spline_approx",
        "technical_debt.td3_grammar_ablation",
        "workbench.desktop.v0",
    ):
        assert entities[("capability", capability_id)]["status"] == (
            "implemented_no_cst"
        )
    r2_evidence = entities[("roadmap_gate", "R2.landmark_and_continuity")][
        "payload"
    ]["evidence"]
    assert "boundary_continuity_policy.v0" in r2_evidence
    assert "compile_record.v1" in r2_evidence
    r3_evidence = entities[("roadmap_gate", "R3.optional_nose_proposal")][
        "payload"
    ]["evidence"]
    assert "family_extension_proposal.v1" in r3_evidence
    assert "r3_family_induction_ablation.59db0a7b5f8e158c" in r3_evidence
    assert entities[("roadmap_gate", "R4.phase_closeout")]["status"] == "passed"


def test_source_hash_change_is_reported_stale(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    database = tmp_path / "workbench.sqlite"
    rebuild_workbench(database, source_set)
    assert {item["status"] for item in RegistryReader(database).audit_sources(ROOT)} == {
        "fresh"
    }

    session_path = source_set.review_sessions[0]
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session["revision"] = 8
    _write_json(session_path, session)

    status = RegistryReader(database).audit_sources(ROOT)
    changed = [item for item in status if item["display_path"].endswith("review_session.v1.json")]
    assert len(changed) == 1
    assert changed[0]["status"] == "stale"
    assert changed[0]["stored_raw_sha256"] != changed[0]["actual_raw_sha256"]


def test_missing_source_is_reported_without_mutating_registry(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    database = tmp_path / "workbench.sqlite"
    rebuild_workbench(database, source_set)
    session_path = source_set.review_sessions[0]
    session_path.unlink()

    status = RegistryReader(database).audit_sources(ROOT)
    missing = [
        item
        for item in status
        if item["display_path"].endswith("review_session.v1.json")
    ]
    assert len(missing) == 1
    assert missing[0]["status"] == "missing"
    assert missing[0]["actual_raw_sha256"] is None


def test_rebuild_requires_both_real_instance_ids(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    incomplete_profile = source_set.family_profile.parent / "incomplete_profile.json"
    _write_json(incomplete_profile, _profile_mapping(_instance("sls2.r149.6593e02e")))
    incomplete = WorkbenchSourceSet(
        repo_root=source_set.repo_root,
        family_profile=incomplete_profile,
        literature_packages=source_set.literature_packages,
        review_sessions=source_set.review_sessions,
    )

    with pytest.raises(WorkbenchIndexError, match="rf500.2c27faee.b1r3"):
        rebuild_workbench(tmp_path / "workbench.sqlite", incomplete)


def test_rebuild_refuses_sources_outside_repository(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    outside_profile = tmp_path / "outside_profile.json"
    _write_json(
        outside_profile,
        _profile_mapping(
            _instance("sls2.r149.6593e02e"),
            _instance("rf500.2c27faee.b1r3"),
        ),
    )
    outside = WorkbenchSourceSet(
        repo_root=source_set.repo_root,
        family_profile=outside_profile,
        literature_packages=source_set.literature_packages,
        review_sessions=source_set.review_sessions,
    )

    with pytest.raises(WorkbenchIndexError, match="inside the declared repository"):
        rebuild_workbench(tmp_path / "workbench.sqlite", outside)


def test_w2_requires_two_compile_records_and_the_complete_w1_proof_set(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    one_record = replace(
        source_set,
        compile_records=(source_set.family_profile,),
    )
    with pytest.raises(WorkbenchIndexError, match="exactly two"):
        rebuild_workbench(tmp_path / "one.sqlite", one_record)

    no_w1 = replace(
        source_set,
        compile_records=(
            source_set.family_profile,
            source_set.literature_packages[0],
        ),
    )
    with pytest.raises(WorkbenchIndexError, match="complete W1"):
        rebuild_workbench(tmp_path / "no-w1.sqlite", no_w1)

    no_w2 = replace(
        source_set,
        family_induction_bundle=source_set.family_profile.parent,
    )
    with pytest.raises(WorkbenchIndexError, match="complete W2"):
        rebuild_workbench(tmp_path / "no-w2.sqlite", no_w2)


def test_server_is_loopback_authenticated_read_only_and_fixed_route(
    tmp_path: Path, source_set: WorkbenchSourceSet
) -> None:
    database = tmp_path / "workbench.sqlite"
    rebuild_workbench(database, source_set)

    with WorkbenchServer(database, source_root=ROOT, token=TOKEN) as server:
        assert server.host == "127.0.0.1"
        assert server.base_url.startswith("http://127.0.0.1:")
        status, headers, body = _request(server, "GET", f"/?token={TOKEN}")
        assert status == 200
        assert "RF-CEM Workbench W0" in body
        assert "access-control-allow-origin" not in headers
        assert "no-store" in headers["cache-control"]

        for path, title in (
            ("/families", "Families"),
            ("/instances", "Instances"),
            ("/semantics", "Semantics"),
            ("/semantic-graphs", "Semantic Graphs / W1"),
            ("/representations", "Representations"),
            ("/algorithms", "Algorithms"),
            ("/reviews", "Reviews"),
            ("/validation", "Validation"),
            ("/roadmap", "Roadmap / Gates"),
            ("/coverage", "Capability Coverage"),
            ("/compile-records", "Compile Records"),
            ("/family-induction", "Family Induction / W3"),
        ):
            status, _, body = _request(server, "GET", f"{path}?token={TOKEN}")
            assert status == 200
            assert title in body
        status, _, instances = _request(
            server, "GET", f"/instances?token={TOKEN}"
        )
        assert status == 200
        assert "sls2.r149.6593e02e" in instances
        assert "rf500.2c27faee.b1r3" in instances

        status, _, _ = _request(server, "GET", "/")
        assert status == 403
        status, _, payload = _request(
            server,
            "GET",
            "/api/catalog",
            headers={"X-Workbench-Token": TOKEN},
        )
        assert status == 200
        assert json.loads(payload)["ok"] is True
        status, _, _ = _request(
            server,
            "GET",
            "/api/catalog",
            headers={"X-Workbench-Token": TOKEN, "Origin": "https://attacker.example"},
        )
        assert status == 403
        status, _, _ = _request(
            server,
            "GET",
            "/api/catalog",
            headers={"X-Workbench-Token": TOKEN, "Host": "attacker.example"},
        )
        assert status == 403
        status, _, _ = _request(
            server,
            "POST",
            "/api/catalog",
            headers={"X-Workbench-Token": TOKEN},
            body="{}",
        )
        assert status == 405
        for forbidden in ("/api/shell", "/api/files", "/api/cst", "/../secrets"):
            status, _, _ = _request(
                server,
                "GET",
                forbidden,
                headers={"X-Workbench-Token": TOKEN},
            )
            assert status == 404


def test_cli_rebuild_and_status(
    tmp_path: Path, source_set: WorkbenchSourceSet, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "cli.sqlite"
    assert (
        workbench_main(
            [
                "rebuild",
                "--database",
                str(database),
                "--repo-root",
                str(ROOT),
                "--family-profile",
                str(source_set.family_profile),
                "--literature-package",
                str(source_set.literature_packages[0]),
                "--review-session",
                str(source_set.review_sessions[0]),
            ]
        )
        == 0
    )
    rebuild_output = json.loads(capsys.readouterr().out)
    assert rebuild_output["entity_count"] > 20
    assert workbench_main(
        ["status", "--database", str(database), "--repo-root", str(ROOT)]
    ) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert status_output["counts"]["instance"] == 2
    assert {item["status"] for item in status_output["sources"]} == {"fresh"}


def _request(
    server: WorkbenchServer,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> tuple[int, dict[str, str], str]:
    connection = HTTPConnection(server.host, server.port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read().decode("utf-8")
    result_headers = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return response.status, result_headers, payload


def _evidence() -> dict[str, object]:
    return {
        "bundle_relative_path": "fixture/source.json",
        "locator": "#/fixture",
        "source_file_sha256": "a" * 64,
    }


def _instance(instance_id: str) -> dict[str, object]:
    native_payload = {"alpha": 1.0, "beta": 2.0}
    groups = {
        "fixture_parameters": {
            "values": deepcopy(native_payload),
            "count": len(native_payload),
            "scope": "fixture",
        }
    }
    return {
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
            "adapter_id": "fixture_adapter.v0",
            "native_schema_version": "fixture_native.v0",
            "native_payload": deepcopy(native_payload),
            "native_payload_locator": "fixture/source.json#/payload",
            "native_payload_canonical_sha256": canonical_sha256(native_payload),
            "source_artifact_raw_sha256": "a" * 64,
            "parameter_groups": groups,
            "parameter_count": {"fixture_parameters": 2, "total": 2},
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
            key: {"claim": claim, "status": "supported", "evidence": [_evidence()]}
            for key, claim in FAMILY_IDENTITY.items()
        },
        "provenance": {"fixture": True},
        "live_cst": {"status": "not_linked"},
        "physical_acceptance": {"status": "not_established"},
    }


def _profile_mapping(*instances: dict[str, object]) -> dict[str, object]:
    return make_family_profile(
        [FamilyInstance.from_mapping(item) for item in instances]
    ).to_mapping()


def _semantic_package() -> dict[str, object]:
    applicability = {
        "operating_regime": "normal_conducting",
        "cavity_family": "elliptical",
    }
    reviewed = {
        "source_refs": ["txt1"],
        "confidence": 0.8,
        "scope": "fixture",
        "applicability": applicability,
        "human_review_status": "accepted",
    }
    return {
        "schema_version": "literature_semantics.v0",
        "request_context": {
            "design_intent": "500 MHz normal-conducting single-cell cavity",
            "frequency_target_mhz": 500.0,
            "operating_regime": "normal_conducting",
            "geometry_scope": "axisymmetric_single_cell_rf_vacuum",
            "exclude": ["HOM", "coupler", "thermal", "structural", "multipacting"],
        },
        "evidence_sources": [
            {
                "id": "paper1",
                "source_type": "paper",
                "title": "Fixture cavity design note",
                "year": 2024,
                "venue": "fixture",
                "license": "fixture",
            }
        ],
        "text_evidence": [
            {
                "id": "txt1",
                "paper_id": "paper1",
                "page": 1,
                "section": "design",
                "short_excerpt": "The cavity has an equator.",
                "excerpt_hash": "sha256:text1",
            }
        ],
        "image_evidence": [],
        "classification": {
            "cavity_family": "elliptical",
            "cell_count": "single",
            "beta_class": "beta_1",
            "frequency_band_mhz": {"min": 450.0, "max": 550.0},
            "confidence": 0.9,
            "evidence_refs": ["txt1"],
        },
        "named_features": [
            {
                "feature_name": "equator",
                "aliases": ["equator radius"],
                "presence": True,
                **reviewed,
            }
        ],
        "shape_motifs": [{"name": "smooth_equator", "polarity": "preferred", **reviewed}],
        "curve_priors": [
            {
                "curve_region": "equator",
                "allowed_curve_types": ["ellipse", "local_spline"],
                "preferred_forms": ["ellipse"],
                "forbidden_forms": [],
                **reviewed,
            }
        ],
        "parameter_ranges": [],
        "optimization_objectives": [],
        "physical_constraints": [],
    }


def _review_session() -> dict[str, object]:
    return {
        "schema_version": "review_session.v1",
        "revision": 7,
        "review_scope": {"paper_id": "paper1"},
        "review_decisions": {
            "paper1::semantics::named_features::equator": {
                "status": "accepted",
                "revision": 4,
                "review_note": "fixture",
            }
        },
        "helper2_reviews": {
            "fixture.projection": {
                "revision": 7,
                "review": {
                    "schema_version": "helper2_review_session.v1",
                    "geometry": {"F0001": {"status": "accepted"}},
                    "candidates": {
                        "equator_candidate_01": {
                            "type": "EquatorRegion",
                            "status": "confirmed",
                            "geometry_refs": ["face:F0001"],
                        }
                    },
                    "bindings": {
                        "bind_equator": {
                            "status": "accepted",
                            "feature_id": "equator_candidate_01",
                            "geometry_node_id": "face:F0001",
                            "deleted": False,
                        }
                    },
                },
            }
        },
    }


def _write_json(path: Path, value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()
