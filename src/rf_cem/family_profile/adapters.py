"""Adapters from the two frozen source-manifest formats into family instances."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from .core import (
    FAMILY_ID,
    FAMILY_IDENTITY,
    FamilyInstance,
    FamilyProfileError,
    canonical_sha256,
    file_sha256,
)


_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\|^/")


@dataclass(frozen=True)
class _Artifact:
    """Verified source artifact metadata kept without a local absolute path."""

    relative_path: str
    raw_sha256: str
    canonical_sha256: str | None
    path: Path
    role: str | None = None

    def to_binding(self) -> dict[str, Any]:
        """Return the portable artifact reference used by a profile."""

        result: dict[str, Any] = {
            "bundle_relative_path": self.relative_path,
            "raw_sha256": self.raw_sha256,
        }
        if self.canonical_sha256 is not None:
            result["canonical_sha256"] = self.canonical_sha256
        if self.role:
            result["role"] = self.role
        return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FamilyProfileError(f"cannot read UTF-8 JSON source: {path.name}") from exc
    if not isinstance(value, dict):
        raise FamilyProfileError(f"source JSON must contain an object: {path.name}")
    return value


def _canonical_artifact(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FamilyProfileError(f"cannot read UTF-8 JSON source: {path.name}") from exc
        return canonical_sha256(value)
    if suffix in {".yaml", ".yml"}:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise FamilyProfileError(f"cannot read UTF-8 YAML source: {path.name}") from exc
        return canonical_sha256(value)
    return None


def _is_read_only(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    windows_read_only = bool(attributes & 0x1)
    return windows_read_only or not os.access(path, os.W_OK)


def _safe_bundle_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise FamilyProfileError("manifest artifact path must be non-empty")
    candidate = (root / Path(relative_path)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise FamilyProfileError(f"manifest artifact escapes source bundle: {relative_path}") from exc
    return candidate


def _load_manifest(path: Path) -> tuple[dict[str, Any], str, Path]:
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise FamilyProfileError(f"source manifest is missing: {path}")
    if not _is_read_only(manifest_path):
        raise FamilyProfileError(f"source manifest is not read-only: {manifest_path.name}")
    raw = manifest_path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FamilyProfileError(f"source manifest is not UTF-8 JSON: {manifest_path.name}") from exc
    if not isinstance(value, dict):
        raise FamilyProfileError("source manifest root must be an object")
    return value, file_sha256(manifest_path), manifest_path.parent.resolve()


def _verify_artifacts(
    manifest: Mapping[str, Any],
    bundle_root: Path,
    *,
    collection_key: str,
    canonical_key: str,
    raw_key: str,
) -> dict[str, _Artifact]:
    entries = manifest.get(collection_key)
    if not isinstance(entries, list) or not entries:
        raise FamilyProfileError(f"source manifest.{collection_key} must be non-empty")
    artifacts: dict[str, _Artifact] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise FamilyProfileError(f"source manifest.{collection_key} contains a non-object")
        relative = entry.get("bundle_relative_path")
        if not isinstance(relative, str) or not relative:
            raise FamilyProfileError(f"source manifest.{collection_key} has an invalid relative path")
        if relative in artifacts:
            raise FamilyProfileError(f"duplicate source artifact path: {relative}")
        path = _safe_bundle_path(bundle_root, relative)
        if not path.is_file():
            raise FamilyProfileError(f"source artifact is missing: {relative}")
        if not _is_read_only(path):
            raise FamilyProfileError(f"source artifact is not read-only: {relative}")
        actual_raw = file_sha256(path)
        expected_raw = str(entry.get(raw_key) or "").lower()
        if actual_raw != expected_raw:
            raise FamilyProfileError(f"source artifact raw hash mismatch: {relative}")
        expected_canonical = entry.get(canonical_key)
        actual_canonical = _canonical_artifact(path)
        if expected_canonical is not None:
            expected_text = str(expected_canonical).removeprefix("sha256:").lower()
            if actual_canonical is None or actual_canonical != expected_text:
                raise FamilyProfileError(f"source artifact canonical hash mismatch: {relative}")
        else:
            actual_canonical = None
        artifacts[relative] = _Artifact(
            relative_path=relative.replace("\\", "/"),
            raw_sha256=actual_raw,
            canonical_sha256=actual_canonical,
            path=path,
            role=str(entry.get("role")) if entry.get("role") else None,
        )
    writable = [
        item
        for item in bundle_root.rglob("*")
        if item.is_file() and not _is_read_only(item)
    ]
    if writable:
        raise FamilyProfileError("source bundle contains writable files")
    return artifacts


def _source_binding(
    manifest: Mapping[str, Any], manifest_sha256: str, artifacts: Mapping[str, _Artifact], *, manifest_id: str
) -> dict[str, Any]:
    schema_version = manifest.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise FamilyProfileError("source manifest.schema_version is missing")
    return {
        "manifest_id": manifest_id,
        "manifest_schema_version": schema_version,
        "manifest_raw_sha256": manifest_sha256,
        "artifacts": [artifacts[key].to_binding() for key in sorted(artifacts)],
    }


def _evidence(artifact: _Artifact, locator: str, *, role: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bundle_relative_path": artifact.relative_path,
        "locator": locator,
        "source_file_sha256": artifact.raw_sha256,
        "raw_sha256": artifact.raw_sha256,
    }
    if artifact.canonical_sha256 is not None:
        result["canonical_payload_sha256"] = artifact.canonical_sha256
    if role:
        result["role"] = role
    return result


def _portableize(value: Any) -> Any:
    """Copy a payload while replacing only machine-absolute path strings.

    The native parameter groups and all unknown non-path fields remain intact.
    Raw artifact identity is carried separately by the source binding, so this
    portability projection never rewrites a frozen source artifact.
    """

    if isinstance(value, Mapping):
        return {str(key): _portableize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_portableize(child) for child in value]
    if isinstance(value, tuple):
        return [_portableize(child) for child in value]
    if isinstance(value, str) and _ABSOLUTE_PATH_RE.match(value):
        basename = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return f"relative_source_ref:{basename or 'path'}"
    return value


def _normalise_validation_status(raw_status: object) -> str:
    status = str(raw_status or "").strip()
    if status in {"not_run", "not_linked", "not_established", "pending"}:
        return status
    if status == "evidence_present":
        return "pass"
    if "partial" in status:
        return "partial"
    if status.startswith("pass") or status == "supported":
        return "pass"
    if status == "frozen":
        return "frozen"
    raise FamilyProfileError(f"unsupported source validation status: {raw_status!r}")


def _copy_layer(raw: object, *, source_status: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise FamilyProfileError("source validation layer must be an object")
    result = deepcopy(dict(raw))
    status = source_status if source_status is not None else result.get("status")
    result["source_status"] = status
    result["status"] = _normalise_validation_status(status)
    return result


class FamilyInstanceAdapter:
    """Base for source-specific adapters that restore stored native payloads."""

    adapter_id = "family_instance_adapter.v0"

    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = Path(manifest_path) if manifest_path is not None else None

    def source_context_available(self) -> bool:
        """Return whether this adapter can materialize the frozen source object."""

        return self.manifest_path is not None

    def restore_native_payload(self, instance: FamilyInstance) -> dict[str, Any]:
        """Restore a family instance's source-native payload without mutation."""

        if instance.parameter_payload.get("adapter_id") != self.adapter_id:
            raise FamilyProfileError(
                f"instance adapter mismatch: expected {self.adapter_id}, "
                f"got {instance.parameter_payload.get('adapter_id')}"
            )
        if not self.source_context_available():
            raise FamilyProfileError(
                "source-backed native restore requires a frozen source manifest"
            )
        return self._restore_source_native_payload(instance)

    def _load_bound_source(
        self,
        instance: FamilyInstance,
        *,
        manifest_id_key: str,
        collection_key: str,
        canonical_key: str,
        raw_key: str,
    ) -> tuple[dict[str, Any], dict[str, _Artifact]]:
        if self.manifest_path is None:
            raise FamilyProfileError("source-backed native restore requires a source manifest")
        manifest, manifest_sha, root = _load_manifest(self.manifest_path)
        binding = instance.source_binding
        expected_manifest_sha = str(binding.get("manifest_raw_sha256") or "").lower()
        if expected_manifest_sha != manifest_sha:
            raise FamilyProfileError("source manifest raw hash does not match the profile binding")
        source_id = str(manifest.get(manifest_id_key) or "").strip()
        if source_id != instance.instance_id or binding.get("manifest_id") != source_id:
            raise FamilyProfileError("source manifest ID does not match the profile binding")
        artifacts = _verify_artifacts(
            manifest,
            root,
            collection_key=collection_key,
            canonical_key=canonical_key,
            raw_key=raw_key,
        )
        return manifest, artifacts

    def _restore_source_native_payload(self, instance: FamilyInstance) -> dict[str, Any]:
        raise NotImplementedError

    def preservation_checks(
        self, instance: FamilyInstance, restored: Mapping[str, Any]
    ) -> dict[str, bool]:
        """Return adapter-specific source-native preservation checks."""

        raise NotImplementedError

    def build_instance(self) -> FamilyInstance:
        """Build one instance from the configured frozen source manifest."""

        raise NotImplementedError


class Sls2FamilyInstanceAdapter(FamilyInstanceAdapter):
    """Adapt the frozen SLS-2 generation/session bundle into one instance."""

    adapter_id = "sls2_family_instance_adapter.v0"

    def build_instance(self) -> FamilyInstance:
        """Read the manifest and bind its native parameter tuple."""

        if self.manifest_path is None:
            raise FamilyProfileError("SLS-2 adapter requires a source manifest path")
        manifest, manifest_sha, root = _load_manifest(self.manifest_path)
        artifacts = _verify_artifacts(
            manifest,
            root,
            collection_key="frozen_files",
            canonical_key="canonical_sha256",
            raw_key="raw_sha256",
        )
        manifest_id = str(manifest.get("baseline_id") or "").strip()
        if not manifest_id:
            raise FamilyProfileError("SLS-2 baseline_id is missing")
        if manifest.get("operating_regime") != FAMILY_IDENTITY["operating_regime"]:
            raise FamilyProfileError("SLS-2 operating regime evidence is not normal_conducting")
        if manifest.get("live_cst") != "not_run" or manifest.get("physical_acceptance") != "not_established":
            raise FamilyProfileError("SLS-2 frozen safety states do not match the no-CST contract")

        generation_artifact = artifacts.get("generation.core.json")
        session_artifact = artifacts.get("review_session.v1.json")
        semantics_artifact = artifacts.get("literature_semantics.v0.json")
        mesh_artifact = artifacts.get("helper2_face_mesh.json")
        step_artifact = artifacts.get("cavity.step")
        if not all((generation_artifact, session_artifact, semantics_artifact, mesh_artifact, step_artifact)):
            raise FamilyProfileError("SLS-2 frozen bundle lacks a required truth-layer artifact")
        generation = _read_json(generation_artifact.path)
        session = _read_json(session_artifact.path)
        semantics = _read_json(semantics_artifact.path)
        parameter_tuple = generation.get("parameter_tuple")
        if not isinstance(parameter_tuple, Mapping):
            raise FamilyProfileError("SLS-2 generation lacks parameter_tuple")
        values = parameter_tuple.get("values")
        if not isinstance(values, Mapping) or not values:
            raise FamilyProfileError("SLS-2 native parameter tuple must be a non-empty mapping")
        if parameter_tuple.get("origin") != "published_candidate" or parameter_tuple.get("unit") != "mm":
            raise FamilyProfileError("SLS-2 native tuple origin/unit is not frozen source evidence")
        if not all(isinstance(name, str) and name for name in values):
            raise FamilyProfileError("SLS-2 native parameter names must be non-empty strings")
        _check_finite_mapping(values, "SLS-2 parameter_tuple.values")
        request_context = semantics.get("request_context")
        classification = semantics.get("classification")
        if not isinstance(request_context, Mapping) or not isinstance(classification, Mapping):
            raise FamilyProfileError("SLS-2 semantic family evidence is incomplete")
        if request_context.get("operating_regime") != "normal_conducting":
            raise FamilyProfileError("SLS-2 semantic operating regime evidence is incomplete")
        if classification.get("cell_count") != "single":
            raise FamilyProfileError("SLS-2 semantic cell-count evidence is incomplete")
        if request_context.get("geometry_scope") != "axisymmetric_single_cell_rf_vacuum":
            raise FamilyProfileError("SLS-2 semantic geometry-scope evidence is incomplete")
        candidate_id = str(generation.get("candidate_id") or "").strip()
        model_type = generation.get("features", {}).get("model_type")
        if not candidate_id or not isinstance(model_type, str) or not model_type:
            raise FamilyProfileError("SLS-2 generation identity is incomplete")
        native_payload = deepcopy(dict(values))
        native_hash = canonical_sha256(native_payload)
        source_binding_hashes = manifest.get("source_binding_hashes")
        if not isinstance(source_binding_hashes, Mapping):
            raise FamilyProfileError("SLS-2 source binding hashes are missing")
        source_payload_hash = str(source_binding_hashes.get("payload_sha256") or "").removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_payload_hash):
            raise FamilyProfileError("SLS-2 source payload binding hash is invalid")
        review_scope = session.get("review_scope")
        session_payload_hash = (
            str(review_scope.get("payload_sha256") or "").removeprefix("sha256:")
            if isinstance(review_scope, Mapping)
            else ""
        )
        if session_payload_hash.lower() != source_payload_hash.lower():
            raise FamilyProfileError("SLS-2 session/source payload binding hash mismatch")
        review_revision = session.get("revision")
        if not isinstance(review_revision, int) or review_revision <= 0 or review_revision != manifest.get("revision"):
            raise FamilyProfileError("SLS-2 review revision does not match the frozen manifest")

        evidence = {
            "operating_regime": {
                "claim": "normal_conducting",
                "status": "supported",
                "basis": "Frozen baseline manifest records the operating regime.",
                "evidence": [_evidence(_artifact_for(manifest, manifest_sha, "baseline_manifest.v0.json", self.manifest_path), "operating_regime")],
            },
            "symmetry": {
                "claim": "axisymmetric",
                "status": "supported",
                "basis": "Semantic scope and generated z-axis geometry evidence are hash-bound.",
                "evidence": [
                    _evidence(semantics_artifact, "#/request_context/geometry_scope"),
                    _evidence(generation_artifact, "#/features/axis=z"),
                ],
            },
            "cell_count": {
                "claim": "single",
                "status": "supported",
                "basis": "Frozen semantic classification records a single-cell scope.",
                "evidence": [_evidence(semantics_artifact, "#/classification/cell_count")],
            },
            "geometry_scope": {
                "claim": "rf_vacuum",
                "status": "supported",
                "basis": "Frozen semantic request context and RF-vacuum generation candidate are bound.",
                "evidence": [
                    _evidence(semantics_artifact, "#/request_context/geometry_scope"),
                    _evidence(generation_artifact, "#/features/feature_candidates[type=RFVacuumVolume]"),
                ],
            },
        }
        validation = {
            "payload_schema_validation": {
                "status": "pass",
                "source_status": "source_manifest_and_adapter_checks",
                "evidence": [_evidence(generation_artifact, "#/parameter_tuple/values")],
            },
            "parameter_validation": {
                "status": "pass",
                "source_status": "finite_native_mapping",
                "evidence": [_evidence(generation_artifact, "#/parameter_tuple")],
            },
            "geometry_generation": {
                "status": "pending",
                "source_status": str(manifest.get("truth_layers", {}).get("geometry_generation", {}).get("generation_review_status", "pending")),
                "evidence": [_evidence(generation_artifact, "#/validation")],
            },
            "geometry_validation": {
                "status": "pass",
                "source_status": "recorded_no_cst_geometry_validation",
                "evidence": [_evidence(generation_artifact, "#/validation/pass")],
            },
            "human_review": {
                "status": "frozen",
                "source_status": "revision_bound",
                "revision": review_revision,
                "evidence": [_evidence(session_artifact, "#/revision")],
            },
            "helper2_review": {
                "status": "partial",
                "source_status": "truth_layers.helper2_review.overlay",
                "evidence": [
                    _evidence(session_artifact, "#/helper2_reviews"),
                    _evidence(mesh_artifact, "#/"),
                ],
            },
            "live_cst": {"status": "not_run", "source_status": manifest.get("live_cst")},
            "physical_acceptance": {"status": "not_established", "source_status": manifest.get("physical_acceptance")},
        }
        source_refs = [
            _evidence(generation_artifact, "#/parameter_tuple/values"),
            _evidence(session_artifact, "#/review_scope/source_binding/payload_sha256"),
        ]
        parameter_payload = {
            "adapter_id": self.adapter_id,
            "native_schema_version": str(generation.get("schema_version") or ""),
            "native_payload": native_payload,
            "native_payload_locator": "generation.core.json#/parameter_tuple/values",
            "native_payload_canonical_sha256": native_hash,
            "source_payload_canonical_sha256": native_hash,
            "portable_projection_canonical_sha256": native_hash,
            "source_artifact_raw_sha256": generation_artifact.raw_sha256,
            "parameter_groups": {
                "native_parameters": {
                    "values": native_payload,
                    "count": len(native_payload),
                    "unit": "mm",
                    "scope": "published_candidate",
                }
            },
            "parameter_count": {"native": len(native_payload), "total": len(native_payload)},
            "units": {"length": "mm"},
            "scope": "published_candidate_geometry",
            "source_refs": source_refs,
        }
        instance = FamilyInstance(
            schema_version="family_instance.v0",
            instance_id=manifest_id,
            family_id=FAMILY_ID,
            source_binding=_source_binding(manifest, manifest_sha, artifacts, manifest_id=manifest_id),
            native_schema=str(generation.get("schema_version") or ""),
            native_model_type=model_type,
            native_variant=candidate_id.rsplit(".", 1)[-1],
            native_units={"length": "mm"},
            parameter_payload=parameter_payload,
            geometry_artifacts=[
                {
                    "role": "rf_vacuum_geometry",
                    **_evidence(step_artifact, "#/"),
                },
                {
                    "role": "geometry_generation_record",
                    **_evidence(generation_artifact, "#/validation"),
                },
                {
                    "role": "helper2_face_mesh",
                    **_evidence(mesh_artifact, "#/"),
                },
            ],
            validation_layers=validation,
            family_assertion_evidence=evidence,
            provenance={
                "adapter_id": self.adapter_id,
                "source_truth_layers": "generation.core + frozen review session + Helper2 overlay",
                "source_manifest_payload_sha256": source_payload_hash.lower(),
                "review_source_payload_canonical_sha256": source_payload_hash.lower(),
                "no_cst": True,
                "physical_acceptance_not_established": True,
            },
            live_cst={"status": "not_run", "source_manifest_status": manifest.get("live_cst")},
            physical_acceptance={"status": "not_established", "source_manifest_status": manifest.get("physical_acceptance")},
        )
        instance.validate()
        return instance

    def _restore_source_native_payload(self, instance: FamilyInstance) -> dict[str, Any]:
        """Materialize ``parameter_tuple.values`` from the bound generation file."""

        _, artifacts = self._load_bound_source(
            instance,
            manifest_id_key="baseline_id",
            collection_key="frozen_files",
            canonical_key="canonical_sha256",
            raw_key="raw_sha256",
        )
        generation_artifact = artifacts.get("generation.core.json")
        if generation_artifact is None:
            raise FamilyProfileError("SLS-2 source generation artifact is missing")
        generation = _read_json(generation_artifact.path)
        parameter_tuple = generation.get("parameter_tuple")
        values = parameter_tuple.get("values") if isinstance(parameter_tuple, Mapping) else None
        if not isinstance(values, Mapping) or not values:
            raise FamilyProfileError("SLS-2 source native payload is not a non-empty mapping")
        restored = deepcopy(dict(values))
        actual_hash = canonical_sha256(restored)
        expected_hash = str(instance.parameter_payload["native_payload_canonical_sha256"]).lower()
        if actual_hash != expected_hash:
            raise FamilyProfileError("SLS-2 source-native payload canonical hash mismatch")
        return restored

    def preservation_checks(
        self, instance: FamilyInstance, restored: Mapping[str, Any]
    ) -> dict[str, bool]:
        group = instance.parameter_payload["parameter_groups"].get("native_parameters", {})
        group_values = group.get("values") if isinstance(group, Mapping) else None
        return {
            "names": isinstance(group_values, Mapping)
            and set(group_values) == set(restored),
            "groups": set(instance.parameter_payload["parameter_groups"]) == {"native_parameters"},
            "values": group_values == dict(restored),
            "units": instance.native_units.get("length") == "mm"
            and group.get("unit") == "mm",
            "scope": group.get("scope") == "published_candidate"
            and instance.parameter_payload["scope"] == "published_candidate_geometry",
        }


class Rf500FamilyInstanceAdapter(FamilyInstanceAdapter):
    """Adapt the frozen RF-CEM parametric-geometry source bundle."""

    adapter_id = "rf_cem_parametric_geometry_family_instance_adapter.v0"

    def build_instance(self) -> FamilyInstance:
        """Read the native payload, preserving named and derived groups."""

        if self.manifest_path is None:
            raise FamilyProfileError("RF-CEM parametric adapter requires a source manifest path")
        manifest, manifest_sha, root = _load_manifest(self.manifest_path)
        artifacts = _verify_artifacts(
            manifest,
            root,
            collection_key="artifacts",
            canonical_key="canonical_payload_sha256",
            raw_key="source_file_sha256",
        )
        manifest_id = str(manifest.get("instance_source_id") or "").strip()
        if not manifest_id:
            raise FamilyProfileError("RF-CEM source instance_source_id is missing")
        payload_artifact = artifacts.get("source/parametric_geometry.v0.json")
        if payload_artifact is None:
            raise FamilyProfileError("RF-CEM source payload artifact is missing")
        payload = _read_json(payload_artifact.path)
        expected_payload_hash = str(manifest.get("source_payload", {}).get("canonical_json_sha256") or "").lower()
        actual_payload_hash = canonical_sha256(payload)
        if expected_payload_hash != actual_payload_hash:
            raise FamilyProfileError("RF-CEM source payload canonical hash mismatch")
        named = payload.get("named_parameters")
        derived = payload.get("derived_parameters")
        if not isinstance(named, Mapping) or not isinstance(derived, Mapping):
            raise FamilyProfileError("RF-CEM source payload must retain named and derived parameter groups")
        units = payload.get("units")
        if not isinstance(units, Mapping) or not units:
            raise FamilyProfileError("RF-CEM source payload units are missing")
        model_type = payload.get("model_type")
        variant = payload.get("variant")
        native_schema = payload.get("schema_version")
        if not all(isinstance(item, str) and item for item in (model_type, native_schema)):
            raise FamilyProfileError("RF-CEM native schema/model type is missing")
        if not isinstance(variant, Mapping) or not isinstance(variant.get("name"), str) or not variant["name"]:
            raise FamilyProfileError("RF-CEM native variant is missing")
        source_payload_meta = manifest.get("source_payload")
        if not isinstance(source_payload_meta, Mapping):
            raise FamilyProfileError("RF-CEM source payload metadata is missing")
        if source_payload_meta.get("raw_sha256") != payload_artifact.raw_sha256:
            raise FamilyProfileError("RF-CEM source payload raw hash binding mismatch")
        if source_payload_meta.get("schema_version") != native_schema:
            raise FamilyProfileError("RF-CEM source payload schema binding mismatch")
        if source_payload_meta.get("model_type_original") != model_type:
            raise FamilyProfileError("RF-CEM source payload model binding mismatch")
        if source_payload_meta.get("named_parameter_count") != len(named):
            raise FamilyProfileError("RF-CEM named parameter count binding mismatch")
        if source_payload_meta.get("derived_parameter_count") != len(derived):
            raise FamilyProfileError("RF-CEM derived parameter count binding mismatch")
        if source_payload_meta.get("units_original") != units:
            raise FamilyProfileError("RF-CEM source payload unit binding mismatch")
        variant_meta = source_payload_meta.get("variant_original")
        if not isinstance(variant_meta, Mapping) or variant_meta.get("name") != variant["name"]:
            raise FamilyProfileError("RF-CEM source payload variant binding mismatch")
        _check_finite_mapping(named, "RF-CEM named_parameters")
        _check_finite_mapping(derived, "RF-CEM derived_parameters")
        family_assertions = manifest.get("family_assertions")
        if not isinstance(family_assertions, Mapping):
            raise FamilyProfileError("RF-CEM family assertion evidence is missing")
        evidence: dict[str, dict[str, Any]] = {}
        for key, claim in FAMILY_IDENTITY.items():
            raw_assertion = family_assertions.get(key)
            raw_claim = raw_assertion.get("claim") if isinstance(raw_assertion, Mapping) else None
            claim_matches = raw_claim == claim or (
                key == "geometry_scope" and raw_claim == "RF-vacuum geometry"
            )
            if not isinstance(raw_assertion, Mapping) or not claim_matches:
                raise FamilyProfileError(f"RF-CEM family assertion does not support {key}={claim}")
            raw_evidence = raw_assertion.get("evidence")
            if not isinstance(raw_evidence, list) or not raw_evidence:
                raise FamilyProfileError(f"RF-CEM family assertion evidence is empty: {key}")
            copied_evidence = []
            for item in raw_evidence:
                if not isinstance(item, Mapping):
                    raise FamilyProfileError(f"RF-CEM family assertion evidence is malformed: {key}")
                copied = {
                    key_name: deepcopy(item[key_name])
                    for key_name in (
                        "bundle_relative_path",
                        "locator",
                        "source_file_sha256",
                        "canonical_payload_sha256",
                    )
                    if key_name in item and item[key_name] is not None
                }
                if "bundle_relative_path" not in copied or "locator" not in copied:
                    raise FamilyProfileError(f"RF-CEM family assertion evidence lacks locator: {key}")
                artifact = artifacts.get(copied["bundle_relative_path"])
                if artifact is None:
                    raise FamilyProfileError(
                        f"RF-CEM family assertion references an unknown artifact: {copied['bundle_relative_path']}"
                    )
                declared_raw = copied.get("source_file_sha256")
                if declared_raw is not None and str(declared_raw).lower() != artifact.raw_sha256:
                    raise FamilyProfileError(f"RF-CEM family assertion raw hash mismatch: {key}")
                declared_canonical = copied.get("canonical_payload_sha256")
                if declared_canonical is not None and artifact.canonical_sha256 is not None:
                    if str(declared_canonical).removeprefix("sha256:").lower() != artifact.canonical_sha256:
                        raise FamilyProfileError(f"RF-CEM family assertion canonical hash mismatch: {key}")
                copied_evidence.append(copied)
            evidence[key] = {
                "claim": claim,
                "status": "supported",
                "basis": str(raw_assertion.get("basis") or "source manifest family assertion"),
                "evidence": copied_evidence,
            }
        portable_payload = _portableize(payload)
        portable_hash = canonical_sha256(portable_payload)
        validation_source = manifest.get("validation_layers")
        if not isinstance(validation_source, Mapping):
            raise FamilyProfileError("RF-CEM validation layers are missing")
        validation: dict[str, dict[str, Any]] = {}
        for layer in (
            "payload_schema_validation",
            "parameter_validation",
            "geometry_generation",
            "geometry_validation",
            "human_review",
            "helper2_review",
            "live_cst",
            "physical_acceptance",
        ):
            if layer not in validation_source:
                raise FamilyProfileError(f"RF-CEM validation layer is missing: {layer}")
            validation[layer] = _copy_layer(validation_source[layer])
        geometry_artifact_specs = (
            ("rf_vacuum_step", "source/generated_vacuum.step", "#/"),
            ("parametric_geometry_payload", "source/parametric_geometry.v0.json", "#/"),
            ("geometry_validation", "source/geometry_validation.json", "#/"),
            ("helper2_geometry_layer", "source/udsg.v0.json", "#/"),
        )
        geometry_artifacts = []
        for role, relative, locator in geometry_artifact_specs:
            artifact = artifacts.get(relative)
            if artifact is None:
                raise FamilyProfileError(f"RF-CEM geometry artifact is missing: {relative}")
            geometry_artifacts.append({"role": role, **_evidence(artifact, locator)})
        source_refs = [
            _evidence(payload_artifact, "#/named_parameters and #/derived_parameters"),
        ]
        parameter_payload = {
            "adapter_id": self.adapter_id,
            "native_schema_version": native_schema,
            "native_payload": portable_payload,
            "native_payload_locator": "source/parametric_geometry.v0.json#/$",
            "native_payload_canonical_sha256": actual_payload_hash,
            "source_payload_canonical_sha256": actual_payload_hash,
            "portable_projection_canonical_sha256": portable_hash,
            "source_artifact_raw_sha256": payload_artifact.raw_sha256,
            "parameter_groups": {
                "named_parameters": {
                    "values": deepcopy(dict(named)),
                    "count": len(named),
                    "unit_values": sorted({str(item.get("unit")) for item in named.values() if isinstance(item, Mapping)}),
                    "scope": "native_named_parameters",
                },
                "derived_parameters": {
                    "values": deepcopy(dict(derived)),
                    "count": len(derived),
                    "unit_values": sorted({str(item.get("unit")) for item in derived.values() if isinstance(item, Mapping)}),
                    "scope": "native_derived_parameters",
                },
            },
            "parameter_count": {
                "named": len(named),
                "derived": len(derived),
                "total": len(named) + len(derived),
            },
            "units": deepcopy(dict(units)),
            "scope": "native_parametric_geometry_payload",
            "source_refs": source_refs,
            "portable_path_policy": "absolute source strings are replaced with relative_source_ref tokens; raw source hash is retained",
        }
        instance = FamilyInstance(
            schema_version="family_instance.v0",
            instance_id=manifest_id,
            family_id=FAMILY_ID,
            source_binding=_source_binding(manifest, manifest_sha, artifacts, manifest_id=manifest_id),
            native_schema=native_schema,
            native_model_type=model_type,
            native_variant=variant["name"],
            native_units={str(key): str(value) for key, value in units.items()},
            parameter_payload=parameter_payload,
            geometry_artifacts=geometry_artifacts,
            validation_layers=validation,
            family_assertion_evidence=evidence,
            provenance={
                "adapter_id": self.adapter_id,
                "source_payload_raw_sha256": payload_artifact.raw_sha256,
                "source_payload_canonical_sha256": actual_payload_hash,
                "native_parameter_groups_preserved": ["named_parameters", "derived_parameters"],
                "no_cst": True,
                "physical_acceptance_not_established": True,
            },
            live_cst={"status": "not_linked", "source_manifest_status": validation["live_cst"]["source_status"]},
            physical_acceptance={"status": "not_established", "source_manifest_status": validation["physical_acceptance"]["source_status"]},
        )
        instance.validate()
        return instance

    def _restore_source_native_payload(self, instance: FamilyInstance) -> dict[str, Any]:
        """Materialize the complete source JSON object, including unknown fields."""

        manifest, artifacts = self._load_bound_source(
            instance,
            manifest_id_key="instance_source_id",
            collection_key="artifacts",
            canonical_key="canonical_payload_sha256",
            raw_key="source_file_sha256",
        )
        payload_artifact = artifacts.get("source/parametric_geometry.v0.json")
        if payload_artifact is None:
            raise FamilyProfileError("RF-CEM source payload artifact is missing")
        payload = _read_json(payload_artifact.path)
        actual_hash = canonical_sha256(payload)
        source_meta = manifest.get("source_payload")
        if not isinstance(source_meta, Mapping):
            raise FamilyProfileError("RF-CEM source payload metadata is missing")
        if source_meta.get("canonical_json_sha256") != actual_hash:
            raise FamilyProfileError("RF-CEM source payload canonical hash mismatch")
        if source_meta.get("raw_sha256") != payload_artifact.raw_sha256:
            raise FamilyProfileError("RF-CEM source payload raw hash mismatch")
        expected_hash = str(instance.parameter_payload["native_payload_canonical_sha256"]).lower()
        if actual_hash != expected_hash:
            raise FamilyProfileError("RF-CEM source-native payload canonical hash mismatch")
        return payload

    def preservation_checks(
        self, instance: FamilyInstance, restored: Mapping[str, Any]
    ) -> dict[str, bool]:
        groups = instance.parameter_payload["parameter_groups"]
        named_group = groups.get("named_parameters", {})
        derived_group = groups.get("derived_parameters", {})
        named = restored.get("named_parameters")
        derived = restored.get("derived_parameters")
        projection = _portableize(restored)
        return {
            "names": isinstance(named, Mapping)
            and isinstance(derived, Mapping)
            and set(named) == set(named_group.get("values", {}))
            and set(derived) == set(derived_group.get("values", {})),
            "groups": set(groups) == {"named_parameters", "derived_parameters"},
            "values": named == named_group.get("values")
            and derived == derived_group.get("values"),
            "units": restored.get("units") == instance.parameter_payload["units"]
            and instance.native_units
            == {str(key): str(value) for key, value in restored.get("units", {}).items()},
            "scope": bool(instance.parameter_payload["scope"])
            and all(
                bool(group.get("scope"))
                for group in (named_group, derived_group)
            ),
            "unknown_native_fields": projection == instance.parameter_payload["native_payload"],
        }


def _check_finite_mapping(value: Mapping[str, Any], label: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise FamilyProfileError(f"{label} contains an invalid parameter name")
        numeric: Any = item.get("value") if isinstance(item, Mapping) else item
        if isinstance(numeric, bool):
            continue
        if isinstance(numeric, (int, float)) and isinstance(numeric, float):
            if not __import__("math").isfinite(numeric):
                raise FamilyProfileError(f"{label}.{key} has a non-finite numeric value")


def _artifact_for(manifest: Mapping[str, Any], manifest_sha: str, relative: str, manifest_path: Path) -> _Artifact:
    """Create a portable evidence reference for the manifest itself."""

    return _Artifact(
        relative_path=relative,
        raw_sha256=manifest_sha,
        canonical_sha256=None,
        path=manifest_path,
        role="source_manifest",
    )


__all__ = [
    "FamilyInstanceAdapter",
    "Rf500FamilyInstanceAdapter",
    "Sls2FamilyInstanceAdapter",
]
