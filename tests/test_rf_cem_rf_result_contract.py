"""No-CST contract, replay, and fail-closed tests for RF-CEM R5."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from rf_cem.physics import (
    BoundaryAssignment,
    ContractRef,
    ExternalArtifactRef,
    FieldBundle,
    FieldComponent,
    GeometryBinding,
    MaterialAssignment,
    MeshConvergence,
    MeshConvergenceSample,
    MeshDefinition,
    MetricContract,
    MetricObservation,
    ModeFingerprint,
    ModeIdentity,
    PhysicsCase,
    PhysicsContractError,
    ResultProvenance,
    SolverDefinition,
    assess_comparability,
    build_initial_metric_contracts,
    evaluate_mesh_convergence,
    load_r5_bundle,
)
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
R5_OUTPUT_ROOT = ROOT / "analysis_outputs/rf_cem_rf_result_contract"
R5_DEV_OUTPUT_ROOT = ROOT / "analysis_outputs/rf_cem_rf_result_contract_dev"


def _hash(character: str) -> str:
    return character * 64


def _ref(kind: str, schema: str, object_id: str, character: str) -> ContractRef:
    return ContractRef(kind, schema, object_id, _hash(character))


def _geometry() -> GeometryBinding:
    instance = "rf500.fixture"
    return GeometryBinding(
        family_id="nc_axisymmetric_single_cell_rf_vacuum",
        instance_id=instance,
        instance_graph_ref=_ref(
            "instance_boundary_graph",
            "instance_boundary_graph.v0",
            f"{instance}.boundary_graph.v0",
            "1",
        ),
        compile_record_ref=_ref(
            "compile_record",
            "compile_record.v0",
            f"{instance}.compile.fixture",
            "2",
        ),
        exact_geometry_ref=_ref(
            "exact_geometry_reference",
            "exact_geometry_reference.v0",
            f"{instance}.exact_geometry.fixture",
            "3",
        ),
    )


def _solver(*, established: bool = True) -> SolverDefinition:
    return SolverDefinition(
        product="CST Studio Suite",
        version="2026",
        build="2026.01-fixture" if established else None,
        solver_name="Solver_HF_TET_E",
        interface="fixture verified wrapper",
        settings_status="established" if established else "planned",
    )


def _case(
    *,
    mesh_id: str = "mesh.nominal",
    material_name: str = "Copper (annealed)",
    boundary: str = "electric",
    status: str = "completed",
) -> PhysicsCase:
    established = status == "completed"
    setting = "established" if established else "planned"
    return PhysicsCase(
        geometry=_geometry(),
        solver=_solver(established=established),
        solver_recipe="fixture eigenmode recipe",
        materials=(
            MaterialAssignment(
                "conductor",
                "background",
                material_name,
                5.8e7,
                setting,
            ),
            MaterialAssignment("vacuum", "RFVacuumVolume", "Vacuum", None, setting),
        ),
        boundaries=(BoundaryAssignment("global", boundary, setting),),
        mesh=MeshDefinition(
            mesh_id,
            mesh_id.rsplit(".", 1)[-1],
            "tetrahedral",
            {"cells_target": 100_000},
            setting,
        ),
        requested_mode_count=1,
        case_status=status,
        authorization_status="authorized" if established else "not_requested",
        limitations=(),
    )


def _mode(case: PhysicsCase, *, role: str = "fundamental_accelerating_mode") -> tuple[ModeFingerprint, ModeIdentity]:
    fingerprint = ModeFingerprint(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        fingerprint_status="established",
        frequency_mhz=500.0,
        r_over_q_ohm=420.0,
        symmetry_signature=("axisymmetric", "monopole", "longitudinal_e_on_axis"),
        field_signature_artifacts=(),
        fingerprint_method="fixture scalar and symmetry fingerprint",
    )
    mode = ModeIdentity(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        fingerprint_ref=fingerprint.identity_ref(),
        mode_family="monopole",
        mode_role=role,
        solver_result_locator=r"2D/3D Results\Modes\Mode 1",
        solver_mode_index=1,
        determination_status="auto_matched",
        determination_method="frequency + R/Q + symmetry fingerprint",
    )
    return fingerprint, mode


def _observation(
    case: PhysicsCase,
    mode: ModeIdentity,
    metric: MetricContract,
    *,
    provenance_character: str,
    value: float = 500.0,
    normalization: str | None = None,
) -> MetricObservation:
    provenance = _ref(
        "result_provenance",
        "result_provenance.v0",
        f"{case.geometry.instance_id}.result_provenance.{provenance_character}",
        provenance_character,
    )
    return MetricObservation(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        mode_identity_ref=mode.identity_ref(),
        metric_contract_ref=metric.identity_ref(),
        provenance_ref=provenance,
        result_locator=metric.result_locator_template.format(mode_index=1),
        unit=metric.unit,
        extraction_method=metric.extraction_method,
        normalization=normalization or metric.normalization,
        value=value,
        validation_status="replayed",
        validation_messages=("fixture replay passed",),
    )


def test_initial_metric_registry_is_complete_unit_bound_and_preserves_q_semantics() -> None:
    metrics = build_initial_metric_contracts()
    assert [item.metric_key for item in metrics] == [
        "eigenfrequency",
        "r_over_q",
        "q_perturbation",
        "stored_energy",
        "epk",
        "bpk",
        "epk_over_eacc",
        "bpk_over_eacc",
        "surface_loss",
    ]
    assert [item.unit for item in metrics] == [
        "MHz",
        "ohm",
        "1",
        "J",
        "MV/m",
        "mT",
        "1",
        "mT/(MV/m)",
        "W",
    ]
    q = metrics[2]
    assert q.native_quantity_name == "Q-Factor (Perturbation)"
    assert "not" in " ".join(q.semantic_safeguards).lower()
    assert "q0" in " ".join(q.semantic_safeguards).lower()
    assert all(MetricContract.from_mapping(item.to_mapping()) == item for item in metrics)
    assert [item.extraction_support for item in metrics[:3]] == [
        "repository_verified_locator"
    ] * 3
    assert all(item.extraction_support == "not_established" for item in metrics[3:])


def test_q_perturbation_cannot_be_relabelled_q0() -> None:
    q = build_initial_metric_contracts()[2]
    with pytest.raises(PhysicsContractError, match="preserve the native CST"):
        replace(q, native_quantity_name="Q0", metric_contract_id="", content_sha256="")


def test_physics_case_round_trip_binds_geometry_solver_material_boundary_and_mesh() -> None:
    case = _case()
    assert PhysicsCase.from_mapping(case.to_mapping()) == case
    payload = case.to_mapping()
    assert payload["geometry"]["instance_graph_ref"]["schema_version"] == "instance_boundary_graph.v0"
    assert payload["geometry"]["compile_record_ref"]["schema_version"] == "compile_record.v0"
    assert payload["geometry"]["exact_geometry_ref"]["schema_version"] == "exact_geometry_reference.v0"
    assert payload["solver"]["version"] == "2026"
    assert payload["materials"][0]["material_name"] == "Copper (annealed)"
    assert payload["boundaries"][0]["condition"] == "electric"
    assert payload["mesh"]["mesh_id"] == "mesh.nominal"


def test_completed_case_fails_without_authorization_or_established_settings() -> None:
    case = _case()
    with pytest.raises(PhysicsContractError, match="requires authorization"):
        replace(case, authorization_status="not_authorized", physics_case_id="", content_sha256="")
    with pytest.raises(PhysicsContractError, match="solver version/build"):
        replace(
            case,
            solver=_solver(established=False),
            physics_case_id="",
            content_sha256="",
        )


def test_mode_identity_requires_more_than_a_bare_index() -> None:
    case = _case(status="planned_not_run")
    fingerprint = ModeFingerprint(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        fingerprint_status="not_established",
        frequency_mhz=None,
        r_over_q_ohm=None,
        symmetry_signature=(),
        field_signature_artifacts=(),
        fingerprint_method="not established",
    )
    with pytest.raises(PhysicsContractError, match="bare solver mode index"):
        ModeIdentity(
            geometry=case.geometry,
            physics_case_ref=case.identity_ref(),
            fingerprint_ref=fingerprint.identity_ref(),
            mode_family="unknown",
            mode_role="candidate",
            solver_result_locator="not_established",
            solver_mode_index=1,
            determination_status="not_established",
            determination_method="bare index",
        )


def test_established_mode_fingerprint_requires_frequency_rq_and_field_or_symmetry() -> None:
    case = _case()
    with pytest.raises(PhysicsContractError, match="frequency and R/Q"):
        ModeFingerprint(
            geometry=case.geometry,
            physics_case_ref=case.identity_ref(),
            fingerprint_status="established",
            frequency_mhz=500.0,
            r_over_q_ohm=None,
            symmetry_signature=("monopole",),
            field_signature_artifacts=(),
            fingerprint_method="incomplete",
        )
    with pytest.raises(PhysicsContractError, match="symmetry or field"):
        ModeFingerprint(
            geometry=case.geometry,
            physics_case_ref=case.identity_ref(),
            fingerprint_status="established",
            frequency_mhz=500.0,
            r_over_q_ohm=420.0,
            symmetry_signature=(),
            field_signature_artifacts=(),
            fingerprint_method="incomplete",
        )


def test_metric_observation_rejects_values_without_established_validation() -> None:
    case = _case()
    _, mode = _mode(case)
    metric = build_initial_metric_contracts()[0]
    observation = _observation(case, mode, metric, provenance_character="4")
    assert MetricObservation.from_mapping(observation.to_mapping()) == observation
    with pytest.raises(PhysicsContractError, match="cannot contain a value"):
        replace(
            observation,
            validation_status="not_established",
            metric_observation_id="",
            content_sha256="",
        )
    with pytest.raises(PhysicsContractError, match="must be finite"):
        replace(
            observation,
            value=float("nan"),
            metric_observation_id="",
            content_sha256="",
        )


def test_field_bundle_keeps_payload_external_and_detects_tampering(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest_path = repo / "results/field_manifest.json"
    data_path = repo / "results/e_field.bin"
    manifest_path.parent.mkdir()
    manifest_path.write_text('{"shape":[2,2]}\n', encoding="utf-8")
    data_path.write_bytes(b"field-data-fixture")
    case = _case()
    _, mode = _mode(case)
    provenance = _ref(
        "result_provenance",
        "result_provenance.v0",
        "rf500.fixture.result_provenance.fixture",
        "5",
    )
    bundle = FieldBundle(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        mode_identity_ref=mode.identity_ref(),
        provenance_ref=provenance,
        field_status="established",
        coordinate_system="cartesian_xyz",
        normalization="1 J stored energy",
        components=(FieldComponent("E_z", "electric field", "MV/m", "fixture:E_z", True),),
        artifacts=(
            ExternalArtifactRef.from_file(
                repo_root=repo,
                path=manifest_path,
                role="field_manifest",
                media_type="application/json",
            ),
            ExternalArtifactRef.from_file(
                repo_root=repo,
                path=data_path,
                role="field_data_e",
                media_type="application/octet-stream",
            ),
        ),
        extraction_method="fixture verified field exporter",
    )
    payload = bundle.to_mapping()
    assert payload["inline_field_payload"] is False
    assert "data" not in payload
    assert FieldBundle.from_mapping(payload) == bundle
    assert bundle.validate_external_artifacts(repo) == (manifest_path, data_path)
    data_path.write_bytes(b"tampered")
    with pytest.raises(PhysicsContractError, match="size mismatch|hash mismatch"):
        bundle.validate_external_artifacts(repo)


def test_mesh_convergence_computes_three_level_relative_change_and_round_trips() -> None:
    geometry = _geometry()
    metric = build_initial_metric_contracts()[0]
    samples = tuple(
        MeshConvergenceSample(
            mesh_level=level,
            mesh_id=f"mesh.{level}",
            mesh_cells=cells,
            physics_case_ref=_ref(
                "physics_case",
                "physics_case.v0",
                f"rf500.fixture.physics_case.{level}",
                character,
            ),
            mode_identity_ref=_ref(
                "mode_identity",
                "mode_identity.v0",
                f"rf500.fixture.mode_identity.{level}",
                str(int(character) + 3),
            ),
            metric_observation_ref=_ref(
                "metric_observation",
                "metric_observation.v0",
                f"rf500.fixture.metric_observation.{level}",
                str(int(character) + 6),
            ),
            value=value,
            unit="MHz",
        )
        for level, cells, value, character in (
            ("coarse", 100_000, 500.2, "1"),
            ("nominal", 200_000, 500.02, "2"),
            ("fine", 400_000, 500.0, "3"),
        )
    )
    result = evaluate_mesh_convergence(
        geometry=geometry,
        metric_contract_ref=metric.identity_ref(),
        samples=samples,
        relative_tolerance=1.0e-4,
    )
    assert result.convergence_status == "converged"
    assert result.relative_changes[-1] == pytest.approx(4.0e-5)
    assert MeshConvergence.from_mapping(result.to_mapping()) == result
    with pytest.raises(PhysicsContractError, match="do not match"):
        replace(
            result,
            relative_changes=(0.1, 0.1),
            convergence_id="",
            content_sha256="",
        )
    duplicate_level = replace(
        samples[1],
        mesh_level=samples[0].mesh_level,
        mesh_id="mesh.duplicate",
    )
    with pytest.raises(PhysicsContractError, match="must be unique"):
        evaluate_mesh_convergence(
            geometry=geometry,
            metric_contract_ref=metric.identity_ref(),
            samples=(samples[0], duplicate_level, samples[2]),
            relative_tolerance=1.0e-4,
        )


def test_direct_comparability_is_default_deny_for_case_normalization_and_mode_changes() -> None:
    metric = build_initial_metric_contracts()[0]
    left_case = _case()
    left_fingerprint, left_mode = _mode(left_case)
    left = _observation(left_case, left_mode, metric, provenance_character="a")
    right = _observation(left_case, left_mode, metric, provenance_character="b")
    comparable = assess_comparability(
        left_observation=left,
        right_observation=right,
        left_case=left_case,
        right_case=left_case,
        left_mode=left_mode,
        right_mode=left_mode,
        left_fingerprint=left_fingerprint,
        right_fingerprint=left_fingerprint,
        left_metric=metric,
        right_metric=metric,
    )
    assert comparable.decision == "comparable"
    assert comparable.reason_codes == ()

    changed_case = _case(material_name="Copper fixture B", mesh_id="mesh.fine")
    changed_fingerprint, changed_mode = _mode(changed_case, role="higher_order_mode")
    changed = _observation(
        changed_case,
        changed_mode,
        metric,
        provenance_character="c",
        normalization="different normalization",
    )
    denied = assess_comparability(
        left_observation=left,
        right_observation=changed,
        left_case=left_case,
        right_case=changed_case,
        left_mode=left_mode,
        right_mode=changed_mode,
        left_fingerprint=left_fingerprint,
        right_fingerprint=changed_fingerprint,
        left_metric=metric,
        right_metric=metric,
    )
    assert denied.decision == "not_comparable"
    assert {
        "material_assignment_differs",
        "mesh_definition_differs",
        "normalization_differs",
        "mode_identity_differs",
    }.issubset(denied.reason_codes)


def test_mesh_comparison_allows_only_mesh_difference_and_still_requires_established_modes() -> None:
    metric = build_initial_metric_contracts()[0]
    left_case = _case(mesh_id="mesh.coarse")
    right_case = _case(mesh_id="mesh.fine")
    left_fp, left_mode = _mode(left_case)
    right_fp, right_mode = _mode(right_case)
    left = _observation(left_case, left_mode, metric, provenance_character="d", value=500.1)
    right = _observation(right_case, right_mode, metric, provenance_character="e", value=500.0)
    assessment = assess_comparability(
        left_observation=left,
        right_observation=right,
        left_case=left_case,
        right_case=right_case,
        left_mode=left_mode,
        right_mode=right_mode,
        left_fingerprint=left_fp,
        right_fingerprint=right_fp,
        left_metric=metric,
        right_metric=metric,
        comparison_purpose="mesh_convergence",
    )
    assert assessment.decision == "comparable"
    assert "mesh_definition_differs" not in assessment.reason_codes


def test_comparability_rejects_objects_that_do_not_match_observation_references() -> None:
    metric = build_initial_metric_contracts()[0]
    source_case = _case()
    fingerprint, mode = _mode(source_case)
    left = _observation(source_case, mode, metric, provenance_character="6")
    right = _observation(source_case, mode, metric, provenance_character="7")
    substituted_case = replace(
        source_case,
        limitations=("different case identity",),
        physics_case_id="",
        content_sha256="",
    )
    assessment = assess_comparability(
        left_observation=left,
        right_observation=right,
        left_case=source_case,
        right_case=substituted_case,
        left_mode=mode,
        right_mode=mode,
        left_fingerprint=fingerprint,
        right_fingerprint=fingerprint,
        left_metric=metric,
        right_metric=metric,
    )
    assert assessment.decision == "not_comparable"
    assert "right_contract_chain_mismatch" in assessment.reason_codes


def test_completed_provenance_requires_authorization_timestamps_artifact_and_exact_build(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    project = repo / "capture/project.cst"
    project.parent.mkdir()
    project.write_bytes(b"fixture cst capture")
    case = _case()
    provenance = ResultProvenance(
        geometry=case.geometry,
        physics_case_ref=case.identity_ref(),
        solver=case.solver,
        run_status="completed",
        authorization_status="authorized",
        execution_id="bounded-live-fixture",
        started_at="2026-08-20T10:00:00+08:00",
        completed_at="2026-08-20T10:10:00+08:00",
        extraction_software="fixture extractor",
        source_artifacts=(
            ExternalArtifactRef.from_file(
                repo_root=repo,
                path=project,
                role="cst_project_with_results",
                media_type="application/vnd.cst.project",
            ),
        ),
        log_artifacts=(),
        replay_command="fixture replay command",
        limitations=("fixture only",),
    )
    assert ResultProvenance.from_mapping(provenance.to_mapping()) == provenance
    with pytest.raises(PhysicsContractError, match="requires authorization"):
        replace(
            provenance,
            authorization_status="not_authorized",
            provenance_id="",
            content_sha256="",
        )


def _materialized_bundle() -> Path | None:
    candidates = [
        *(R5_OUTPUT_ROOT.glob("r5_rf_result_readiness.*") if R5_OUTPUT_ROOT.exists() else ()),
        *(
            R5_DEV_OUTPUT_ROOT.glob("r5_rf_result_readiness.*")
            if R5_DEV_OUTPUT_ROOT.exists()
            else ()
        ),
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def test_materialized_readiness_bundle_replays_and_contains_no_rf_values() -> None:
    path = _materialized_bundle()
    if path is None:
        pytest.skip("ignored R5 readiness proof is not materialized")
    bundle = load_r5_bundle(path, repo_root=ROOT)
    assert bundle.manifest["live_cst_status"] == "not_run"
    assert bundle.manifest["live_cst_authorization"] == "not_requested"
    assert len(bundle.cases) == 3
    assert len(bundle.metric_contracts) == 9
    assert sum(len(item.metric_observations) for item in bundle.cases) == 27
    assert all(
        observation.value is None
        and observation.validation_status == "not_established"
        for case in bundle.cases
        for observation in case.metric_observations
    )
    assert next(
        item.link_status for item in bundle.links if item.geometry.instance_id.startswith("sls2.")
    ) == "not_linked"
    assert all(item.decision == "not_comparable" for item in bundle.comparability)


def _copy_bundle_and_declared_sources(source: Path, tmp_path: Path) -> tuple[Path, Path]:
    manifest = json.loads((source / "source_binding_manifest.v0.json").read_text(encoding="utf-8"))
    repo = tmp_path / "repo"
    bundle_copy = repo / source.relative_to(ROOT)
    shutil.copytree(source, bundle_copy)
    for item in manifest["sources"]:
        source_path = ROOT / item["path"]
        target_path = repo / item["path"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    r4_manifest_item = next(
        item
        for item in manifest["sources"]
        if item["path"].endswith(
            "r4_observation_contract.d06695921d941eee/source_binding_manifest.v0.json"
        )
    )
    r4_source_root = (ROOT / r4_manifest_item["path"]).parent
    r4_target_root = (repo / r4_manifest_item["path"]).parent
    shutil.copytree(r4_source_root, r4_target_root, dirs_exist_ok=True)
    r4_manifest = json.loads(
        (r4_source_root / "source_binding_manifest.v0.json").read_text(encoding="utf-8")
    )
    for item in r4_manifest["sources"]:
        source_path = ROOT / item["path"]
        target_path = repo / item["path"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    return repo, bundle_copy


def test_materialized_bundle_fails_closed_when_contract_is_tampered(tmp_path: Path) -> None:
    source = _materialized_bundle()
    if source is None:
        pytest.skip("ignored R5 readiness proof is not materialized")
    manifest = json.loads((source / "source_binding_manifest.v0.json").read_text(encoding="utf-8"))
    repo, bundle_copy = _copy_bundle_and_declared_sources(source, tmp_path)
    artifact = bundle_copy / manifest["artifacts"][0]["path"]
    artifact.write_bytes(artifact.read_bytes() + b" ")
    with pytest.raises(PhysicsContractError, match="artifact is missing or changed|hash mismatch"):
        load_r5_bundle(bundle_copy, repo_root=repo)


def test_materialized_bundle_rejects_manifest_claim_and_orphan_contract(
    tmp_path: Path,
) -> None:
    source = _materialized_bundle()
    if source is None:
        pytest.skip("ignored R5 readiness proof is not materialized")
    repo, bundle_copy = _copy_bundle_and_declared_sources(source, tmp_path)
    manifest_path = bundle_copy / "source_binding_manifest.v0.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["live_cst_authorization"] = "authorized"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PhysicsContractError, match="cannot claim live-CST authorization"):
        load_r5_bundle(bundle_copy, repo_root=repo)

    repo, bundle_copy = _copy_bundle_and_declared_sources(source, tmp_path / "orphan")
    manifest_path = bundle_copy / "source_binding_manifest.v0.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = next(
        item
        for item in manifest["artifacts"]
        if item["schema_version"] == "metric_observation.v0"
    )
    orphan_relative = "orphan/duplicate.metric_observation.v0.json"
    orphan_path = bundle_copy / orphan_relative
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle_copy / original["path"], orphan_path)
    manifest["artifacts"].append({**original, "path": orphan_relative})
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PhysicsContractError, match="metric observation inventory"):
        load_r5_bundle(bundle_copy, repo_root=repo)


def test_materialized_bundle_indexes_deterministic_w5_and_renders_readiness(
    tmp_path: Path,
) -> None:
    r5 = _materialized_bundle()
    sources = _canonical_workbench_sources(r5) if r5 is not None else None
    if sources is None:
        pytest.skip("canonical R1-R5 ignored proof sources are not materialized")
    database = tmp_path / "w5.sqlite"
    first = rebuild_workbench(database, sources)
    first_snapshot = RegistryReader(database).snapshot()
    second = rebuild_workbench(database, sources)
    assert first.input_set_sha256 == second.input_set_sha256
    assert first_snapshot == RegistryReader(database).snapshot()
    reader = RegistryReader(database)
    counts = reader.entity_counts()
    assert counts["physics_link_status"] == 2
    assert counts["physics_case"] == 3
    assert counts["result_provenance"] == 3
    assert counts["mode_fingerprint"] == 3
    assert counts["mode_identity"] == 3
    assert counts["metric_contract"] == 9
    assert counts["metric_observation"] == 27
    assert counts["field_bundle"] == 3
    assert counts["mesh_convergence"] == 1
    assert counts["result_comparability"] == 2
    metadata = reader.metadata()
    assert metadata["roadmap_phase"] == "R5"
    assert metadata["w5_rf_result_contract"] == "indexed"
    assert metadata["r5_live_cst_status"] == "not_run"
    with WorkbenchServer(
        database,
        source_root=ROOT,
        token="r5-workbench-test-token-0123456789",
    ) as server:
        from http.client import HTTPConnection

        connection = HTTPConnection(server.host, server.port, timeout=3)
        connection.request(
            "GET",
            "/rf-results?token=r5-workbench-test-token-0123456789",
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
    assert response.status == 200
    assert "R5 readiness boundary" in body
    assert "explicit authorization pending" in body
    assert "Mode identity (never a bare index)" in body
    assert "SLS-2" not in body or "not_linked" in body
    assert "505.583944055" not in body
    assert body.index("/ coarse mesh") < body.index("/ nominal mesh") < body.index("/ fine mesh")


def _canonical_workbench_sources(r5_bundle: Path | None) -> WorkbenchSourceSet | None:
    if r5_bundle is None:
        return None
    profile_root = ROOT / (
        "analysis_outputs/rf_cem_family_profiles/"
        "nc_axisymmetric_single_cell_rf_vacuum.00414d4f"
    )
    r1 = ROOT / "analysis_outputs/rf_cem_semantic_core/r1_semantic_core.28e8d6fa9efa221f"
    r2 = ROOT / "analysis_outputs/rf_cem_boundary_compiler/r2_boundary_compiler.aa66a3e90125437b"
    r3 = ROOT / "analysis_outputs/rf_cem_family_induction/r3_family_induction.2f6c02557798e606"
    r4 = ROOT / "analysis_outputs/rf_cem_observation_contract/r4_observation_contract.d06695921d941eee"
    required = (
        profile_root / "family_profile.v0.json",
        profile_root / "family_profile_validation.v0.json",
        r1 / "family_grammar.v0.json",
        r1 / "instance_graph_diff.v0.json",
        r1 / "instances/rf500.2c27faee.b1r3.instance_boundary_graph.v0.json",
        r1 / "instances/sls2.r149.6593e02e.instance_boundary_graph.v0.json",
        r2 / "records/rf500.2c27faee.b1r3.compile_record.v0.json",
        r2 / "records/sls2.r149.6593e02e.compile_record.v0.json",
        r3,
        r4,
        r5_bundle,
    )
    if not all(path.exists() for path in required):
        return None
    return WorkbenchSourceSet(
        repo_root=ROOT,
        family_profile=required[0],
        family_profile_validation=required[1],
        architecture_document=ROOT / "docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md",
        family_grammar=required[2],
        instance_boundary_graphs=(required[4], required[5]),
        instance_graph_diff=required[3],
        compile_records=(required[6], required[7]),
        family_induction_bundle=r3,
        observation_contract_bundle=r4,
        rf_result_bundle=r5_bundle,
    )
