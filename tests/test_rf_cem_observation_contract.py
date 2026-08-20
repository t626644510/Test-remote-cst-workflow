"""No-CST R4 observation, descriptor, constraint, proof, and W4 gates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import json
import math
from pathlib import Path
import tempfile

import pytest

from rf_cem.compiler import CompileRecord, load_compile_record
from rf_cem.observation import (
    ConstraintContractError,
    ConstraintEvaluation,
    EngineeringConstraint,
    ExactGeometryReference,
    GeometryArtifactIdentity,
    LandmarkObservation,
    ObservationBundle,
    ObservationContractError,
    R4SourceSet,
    RegionCurveInput,
    ScalarDescriptorDefinition,
    ScalarDescriptorRegistry,
    SemanticShapeObservation,
    build_default_descriptor_registry,
    build_demonstration_constraints,
    build_exact_geometry_reference,
    build_observation_bundle,
    evaluate_constraints,
    load_r4_bundle,
    observe_compiled_geometry,
    observe_region_curves,
    region_curves_from_compiled,
    write_r4_bundle,
)
from rf_cem.observation.cli import main as observation_main
from rf_cem.representation import (
    CircularArcRepresentation,
    CompositeRegionRepresentation,
    LineRepresentation,
    Point2D,
    SplineNurbsRepresentation,
)
from rf_cem.semantic import EvidenceRef, load_instance_boundary_graph
from rf_cem.semantic.contracts import canonical_json_bytes, file_sha256
from rf_cem.workbench import (
    RegistryReader,
    WorkbenchServer,
    WorkbenchSourceSet,
    rebuild_workbench,
)


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
R1_ROOT = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_semantic_core"
    / "r1_semantic_core.28e8d6fa9efa221f"
)
R2_ROOT = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_boundary_compiler"
    / "r2_boundary_compiler.aa66a3e90125437b"
)
R3_ROOT = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_family_induction"
    / "r3_family_induction.2f6c02557798e606"
)
FAMILY_PROFILE = (
    ROOT
    / "analysis_outputs"
    / "rf_cem_family_profiles"
    / "nc_axisymmetric_single_cell_rf_vacuum.00414d4f"
    / "family_profile.v0.json"
)
ROADMAP = ROOT / "docs" / "RF_CEM_ROADMAP_AND_ARCHITECTURE.md"


def test_real_compiled_instances_produce_separate_strict_observation_layers() -> None:
    inputs = _real_inputs_or_skip()
    registry = _registry()
    observed_instances = set()
    for record_path, graph_path in inputs:
        record = load_compile_record(record_path)
        graph = load_instance_boundary_graph(graph_path)
        exact = build_exact_geometry_reference(ROOT, record_path, record=record)
        shape = observe_compiled_geometry(exact, record, graph)
        bundle = build_observation_bundle(exact, shape, registry)
        observed_instances.add(record.instance_id)

        assert ExactGeometryReference.from_mapping(exact.to_mapping()) == exact
        assert SemanticShapeObservation.from_mapping(shape.to_mapping()) == shape
        assert ObservationBundle.from_mapping(bundle.to_mapping()) == bundle
        assert exact.identity_ref() == shape.exact_geometry_ref
        assert bundle.exact_geometry_ref == exact.identity_ref()
        assert bundle.shape_observation_ref == shape.identity_ref()
        assert bundle.descriptor_registry_ref == registry.identity_ref()
        assert {item.role for item in exact.geometry_artifacts} == {
            "compiled_rf_vacuum_step",
            "compiled_profile",
        }
        assert shape.observation_status == "pass_no_cst"
        assert shape.samples_per_region == 65
        assert len(shape.regions) == len(graph.regions)
        assert all(len(item.samples) == 65 for item in shape.regions)
        assert shape.to_mapping()["native_parameter_names_read"] is False
        assert b"native_payload_locator" not in canonical_json_bytes(shape.to_mapping())

        globals_by_id = {
            item.descriptor_id: item
            for item in bundle.descriptor_values
            if item.scope_kind == "global"
        }
        assert globals_by_id["global.total_cavity_length"].unit == "mm"
        assert globals_by_id["global.vacuum_volume"].unit == "mm^3"
        assert globals_by_id["global.surface_area"].unit == "mm^2"
        assert globals_by_id["global.semantic_region_count"].value == len(graph.regions)
        assert globals_by_id["global.nose_present"].value == any(
            item.region_type == "NoseRegion" for item in graph.regions
        )
        assert bundle.geometry_mutation_status == "not_performed"
        assert bundle.live_cst_status == "not_run"
        assert bundle.rf_metric_status == "not_defined_r4"
        assert bundle.physical_acceptance_status == "not_established"
    assert observed_instances == {
        "rf500.2c27faee.b1r3",
        "sls2.r149.6593e02e",
    }


def test_unknown_units_non_finite_values_and_invalid_landmarks_fail_closed() -> None:
    registry = _registry()
    definition = registry.definitions[0]
    with pytest.raises(ObservationContractError, match="unsupported unit"):
        replace(definition, unit="cm")
    with pytest.raises(ObservationContractError, match="finite"):
        replace(definition, equivalence_absolute_tolerance=math.nan)

    record_path, graph_path = _real_inputs_or_skip()[0]
    record = load_compile_record(record_path)
    graph = load_instance_boundary_graph(graph_path)
    exact = build_exact_geometry_reference(ROOT, record_path, record=record)
    curves = region_curves_from_compiled(record.region_geometries, graph)
    shape = observe_compiled_geometry(exact, record, graph)
    with pytest.raises(ObservationContractError, match="invalid landmark"):
        observe_region_curves(
            family_id=record.family_id,
            instance_id=record.instance_id,
            exact_geometry=exact,
            region_curves=curves,
            landmarks=shape.landmarks[1:],
        )
    mapping = shape.to_mapping()
    mapping["native_parameter_names_read"] = True
    with pytest.raises(ObservationContractError, match="native parameters"):
        SemanticShapeObservation.from_mapping(mapping)

    constraint = build_demonstration_constraints(registry, _provenance())[0]
    with pytest.raises(ObservationContractError, match="unsupported unit"):
        replace(constraint, unit="inch")
    bundle = build_observation_bundle(exact, shape, registry)
    with pytest.raises(ConstraintContractError, match="unknown descriptor"):
            evaluate_constraints(
                (
                    replace(
                        constraint,
                        descriptor_id="global.unknown",
                        constraint_id="",
                        content_sha256="",
                    ),
                ),
            bundle,
            registry,
        )


def test_equivalent_geometry_with_different_representation_and_patching_matches() -> None:
    exact = _fixture_exact_geometry()
    arc = CircularArcRepresentation(
        "fixture.arc",
        center=Point2D(0.0, 20.0),
        radius_mm=10.0,
        start_angle_rad=-math.pi / 2.0,
        end_angle_rad=0.0,
        sample_count=33,
    )
    line = LineRepresentation(
        "fixture.line", Point2D(10.0, 20.0), Point2D(20.0, 10.0)
    )
    spline = SplineNurbsRepresentation(
        "fixture.collinear_spline",
        degree=2,
        fit_points=(
            Point2D(10.0, 20.0),
            Point2D(15.0, 15.0),
            Point2D(20.0, 10.0),
        ),
    )
    patched = CompositeRegionRepresentation(
        "fixture.two_patch_line",
        (
            LineRepresentation(
                "fixture.line.left", Point2D(10.0, 20.0), Point2D(15.0, 15.0)
            ),
            LineRepresentation(
                "fixture.line.right", Point2D(15.0, 15.0), Point2D(20.0, 10.0)
            ),
        ),
    )
    landmarks = _fixture_landmarks()
    common_arc = _curve_input(
        arc,
        region_id="fixture.region.arc",
        region_order=0,
        region_type="EquatorRegion",
        side="center",
        start_landmark_id="fixture.landmark.left",
        end_landmark_id="fixture.landmark.join",
    )
    shapes = []
    for representation in (line, spline, patched):
        before = canonical_json_bytes(representation.to_mapping())
        curves = (
            common_arc,
            _curve_input(
                representation,
                region_id="fixture.region.exit",
                region_order=1,
                region_type="BeamPipeRegion",
                side="right",
                start_landmark_id="fixture.landmark.join",
                end_landmark_id="fixture.landmark.right",
            ),
        )
        shapes.append(
            observe_region_curves(
                family_id=exact.family_id,
                instance_id=exact.instance_id,
                exact_geometry=exact,
                region_curves=curves,
                landmarks=landmarks,
            )
        )
        assert canonical_json_bytes(representation.to_mapping()) == before
    assert line.representation_type != spline.representation_type
    assert len(patched.components) == 2

    registry = _registry()
    bundles = [build_observation_bundle(exact, shape, registry) for shape in shapes]
    reference = _descriptor_map(bundles[0])
    definitions = registry.by_id
    for bundle in bundles[1:]:
        candidate = _descriptor_map(bundle)
        assert set(candidate) == set(reference)
        for key, expected in reference.items():
            actual = candidate[key]
            if expected is None:
                assert actual is None
            elif isinstance(expected, bool):
                assert actual is expected
            else:
                tolerance = definitions[key[0]].equivalence_absolute_tolerance
                assert float(actual) == pytest.approx(float(expected), abs=tolerance)


def test_constraints_cover_all_kinds_both_instances_and_do_not_mutate_sources() -> None:
    registry = _registry()
    constraints = build_demonstration_constraints(registry, _provenance())
    assert {item.constraint_kind for item in constraints} == {
        "hard",
        "soft",
        "advisory",
        "diagnostic",
    }
    for constraint in constraints:
        assert EngineeringConstraint.from_mapping(constraint.to_mapping()) == constraint
        assert constraint.physical_acceptance_status == "not_established"
    results = {}
    for record_path, graph_path in _real_inputs_or_skip():
        before = record_path.read_bytes()
        record = load_compile_record(record_path)
        graph = load_instance_boundary_graph(graph_path)
        exact = build_exact_geometry_reference(ROOT, record_path, record=record)
        shape = observe_compiled_geometry(exact, record, graph)
        bundle = build_observation_bundle(exact, shape, registry)
        evaluations = evaluate_constraints(constraints, bundle, registry)
        assert len(evaluations) == 6
        assert {item.constraint_kind for item in evaluations} == {
            "hard",
            "soft",
            "advisory",
            "diagnostic",
        }
        assert all(item.geometry_mutation_status == "not_performed" for item in evaluations)
        assert all(item.live_cst_status == "not_run" for item in evaluations)
        assert all(
            ConstraintEvaluation.from_mapping(item.to_mapping()) == item
            for item in evaluations
        )
        results[record.instance_id] = evaluations
        assert record_path.read_bytes() == before
    assert any(
        item.result == "violation"
        for evaluations in results.values()
        for item in evaluations
    )
    assert any(
        item.constraint_kind == "diagnostic" and item.result == "violation"
        for item in results["sls2.r149.6593e02e"]
    )
    assert any(
        item.constraint_kind == "hard" and item.blocks_progression
        for evaluations in results.values()
        for item in evaluations
    )


def test_real_r4_bundle_is_deterministic_tamper_evident_and_w4_visible() -> None:
    _real_inputs_or_skip()
    if not R3_ROOT.is_dir() or not FAMILY_PROFILE.is_file():
        pytest.skip("ignored W0-W3 canonical proof sources are not materialized")
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="r4-a-", dir=scratch) as first_dir:
            with tempfile.TemporaryDirectory(prefix="r4-b-", dir=scratch) as second_dir:
                first = write_r4_bundle(_r4_sources(), Path(first_dir))
                second = write_r4_bundle(_r4_sources(), Path(second_dir))
                assert first.bundle_id == second.bundle_id
                assert first.input_sha256 == second.input_sha256
                assert _bundle_files(first.path) == _bundle_files(second.path)
                with pytest.raises(FileExistsError, match="already exists"):
                    write_r4_bundle(_r4_sources(), Path(first_dir))
                loaded = load_r4_bundle(first.path, repo_root=ROOT)
                assert len(loaded.instances) == 2
                assert len(loaded.constraints) == 6
                assert sum(len(item.evaluations) for item in loaded.instances) == 12
                assert loaded.manifest["validation_mode"] == (
                    "no_cst_read_only_compiled_geometry"
                )
                assert observation_main(
                    [
                        "validate",
                        "--root",
                        str(ROOT),
                        "--bundle",
                        str(first.path),
                    ]
                ) == 0

                database = Path(first_dir) / "workbench-w4.sqlite"
                source_set = _workbench_sources(first.path)
                summary = rebuild_workbench(database, source_set)
                snapshot = RegistryReader(database).snapshot()
                second_summary = rebuild_workbench(database, source_set)
                assert summary.input_set_sha256 == second_summary.input_set_sha256
                assert snapshot == RegistryReader(database).snapshot()
                reader = RegistryReader(database)
                counts = reader.entity_counts()
                assert reader.metadata()["indexer_version"] == "r5.w5.v0"
                assert reader.metadata()["roadmap_phase"] == "R4"
                assert counts["descriptor_registry"] == 1
                assert counts["descriptor_definition"] == 21
                assert counts["exact_geometry_reference"] == 2
                assert counts["semantic_shape_observation"] == 2
                assert counts["observation_bundle"] == 2
                assert counts["engineering_constraint"] == 6
                assert counts["constraint_evaluation"] == 12
                assert counts["constraint_finding"] == 12
                assert counts["scalar_descriptor"] > 200
                entities = {
                    (item["entity_kind"], item["entity_id"]): item
                    for item in reader.snapshot()["entities"]
                }
                assert entities[
                    ("validation", "w4.observation-contract-hard-gate")
                ]["status"] == "pass"
                assert {item["status"] for item in reader.audit_sources(ROOT)} == {
                    "fresh"
                }
                with WorkbenchServer(
                    database,
                    source_root=ROOT,
                    token="r4-workbench-test-token",
                ) as server:
                    connection = HTTPConnection(server.host, server.port, timeout=5)
                    connection.request(
                        "GET", "/observations?token=r4-workbench-test-token"
                    )
                    response = connection.getresponse()
                    body = response.read().decode("utf-8")
                    connection.close()
                assert response.status == 200
                for text in (
                    "Observations &amp; Constraints / W4",
                    "Three-layer geometry contract",
                    "Exact native geometry",
                    "Semantic shape observation",
                    "2 normalized instance observations",
                    "Scalar engineering descriptors",
                    "Engineering constraints",
                    "Constraint violations and locations",
                    "Geometry mutation: <b>not_performed</b>",
                    "RF metrics: <b>not_defined_r4</b>",
                    "No live CST",
                ):
                    assert text in body

                tampered = second.path / "scalar_descriptor_registry.v0.json"
                original_registry = tampered.read_bytes()
                tampered.write_bytes(b"tampered\n")
                with pytest.raises(ObservationContractError, match="artifact hash mismatch"):
                    load_r4_bundle(second.path, repo_root=ROOT)
                tampered.write_bytes(original_registry)
                manifest_path = second.path / "source_binding_manifest.v0.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["samples_per_region"] = 66
                manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
                with pytest.raises(ObservationContractError, match="input SHA-256"):
                    load_r4_bundle(second.path, repo_root=ROOT)
    finally:
        try:
            scratch.rmdir()
        except OSError:
            pass


def _real_inputs_or_skip() -> tuple[tuple[Path, Path], ...]:
    record_paths = tuple(sorted((R2_ROOT / "records").glob("*.compile_record.v0.json")))
    graph_paths = tuple(
        sorted((R1_ROOT / "instances").glob("*.instance_boundary_graph.v0.json"))
    )
    if len(record_paths) != 2 or len(graph_paths) != 2:
        pytest.skip("ignored canonical R1/R2 proof sources are not materialized")
    graph_by_instance = {
        load_instance_boundary_graph(path).instance_id: path for path in graph_paths
    }
    return tuple(
        (path, graph_by_instance[load_compile_record(path).instance_id])
        for path in record_paths
    )


def _provenance() -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source_kind="architecture_roadmap",
            source_path=ROADMAP.relative_to(ROOT).as_posix(),
            source_raw_sha256=file_sha256(ROADMAP),
            locator="#R4",
            relation="defines_r4_descriptor_and_constraint_requirements",
        ),
    )


def _registry() -> ScalarDescriptorRegistry:
    registry = build_default_descriptor_registry(_provenance())
    assert ScalarDescriptorRegistry.from_mapping(registry.to_mapping()) == registry
    return registry


def _fixture_exact_geometry() -> ExactGeometryReference:
    return ExactGeometryReference(
        family_id="fixture.family",
        instance_id="fixture.instance",
        compile_id="fixture.compile",
        compile_content_sha256=_sha("compile"),
        compiler_version="fixture.compiler.v0",
        compile_record_source=EvidenceRef(
            source_kind="fixture_compile",
            source_path="fixtures/compile_record.v0.json",
            source_raw_sha256=_sha("compile-record"),
            locator="#",
            relation="defines_exact_compiled_geometry",
        ),
        geometry_artifacts=(
            GeometryArtifactIdentity(
                "compiled_profile",
                "geometry/profile.json",
                "application/json",
                _sha("profile"),
                10,
            ),
            GeometryArtifactIdentity(
                "compiled_rf_vacuum_step",
                "geometry/profile.step",
                "model/step",
                _sha("step"),
                10,
            ),
        ),
    )


def _fixture_landmarks() -> tuple[LandmarkObservation, ...]:
    return (
        LandmarkObservation(
            "fixture.landmark.left",
            "AxialApertureLandmark",
            "left",
            0.0,
            10.0,
            ("fixture.region.arc",),
        ),
        LandmarkObservation(
            "fixture.landmark.join",
            "RegionJunctionLandmark",
            "center",
            10.0,
            20.0,
            ("fixture.region.arc", "fixture.region.exit"),
        ),
        LandmarkObservation(
            "fixture.landmark.right",
            "AxialApertureLandmark",
            "right",
            20.0,
            10.0,
            ("fixture.region.exit",),
        ),
    )


def _curve_input(
    representation: object,
    *,
    region_id: str,
    region_order: int,
    region_type: str,
    side: str,
    start_landmark_id: str,
    end_landmark_id: str,
) -> RegionCurveInput:
    return RegionCurveInput(
        region_id=region_id,
        region_order=region_order,
        region_type=region_type,
        side=side,
        motif_id=None,
        start_landmark_id=start_landmark_id,
        end_landmark_id=end_landmark_id,
        points=representation.sample(),
        start_tangent=representation.start_tangent(),
        end_tangent=representation.end_tangent(),
        start_curvature_per_mm=representation.start_curvature_per_mm(),
        end_curvature_per_mm=representation.end_curvature_per_mm(),
    )


def _descriptor_map(bundle: ObservationBundle) -> dict[tuple[str, str], object]:
    return {
        (item.descriptor_id, item.scope_id): item.value
        for item in bundle.descriptor_values
    }


def _r4_sources() -> R4SourceSet:
    inputs = _real_inputs_or_skip()
    return R4SourceSet(
        repo_root=ROOT,
        compile_records=tuple(item[0] for item in inputs),
        instance_graphs=tuple(item[1] for item in inputs),
        architecture_document=ROADMAP,
    )


def _workbench_sources(r4_bundle: Path) -> WorkbenchSourceSet:
    inputs = _real_inputs_or_skip()
    return WorkbenchSourceSet(
        repo_root=ROOT,
        family_profile=FAMILY_PROFILE,
        architecture_document=ROADMAP,
        family_grammar=R1_ROOT / "family_grammar.v0.json",
        instance_boundary_graphs=tuple(item[1] for item in inputs),
        instance_graph_diff=R1_ROOT / "instance_graph_diff.v0.json",
        compile_records=tuple(item[0] for item in inputs),
        family_induction_bundle=R3_ROOT,
        observation_contract_bundle=r4_bundle,
    )


def _bundle_files(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
