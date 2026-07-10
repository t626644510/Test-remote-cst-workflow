"""Project reviewed semantic features onto profile parameters and segments."""

from __future__ import annotations

from statistics import median

from rf_cem.parametric_geometry.core.types import FeatureBinding
from rf_cem.parametric_geometry.expert_prior import load_expert_prior
from rf_cem.parametric_geometry.analysis.profile_primitives import extract_profile_primitives


def build_feature_bindings(labels: dict, prior: dict | None = None) -> list[FeatureBinding]:
    """Build deterministic feature bindings from reviewed labels."""
    prior = prior or load_expert_prior()[0]
    mappings = prior.get("feature_mappings", {})
    confirmed = labels.get("confirmed_features", {}) if isinstance(labels, dict) else {}
    bindings: list[FeatureBinding] = []
    for feature_id, feature in sorted(confirmed.items()):
        feature_type = str(feature.get("type"))
        geometry_refs = [str(ref) for ref in feature.get("geometry_refs", [])]
        rule = mappings.get(feature_type, {})
        parameter_ids = [str(item) for item in rule.get("parameter_ids", [])]
        segment_ids = [str(item) for item in rule.get("segment_ids", [])]
        bindings.append(
            FeatureBinding(
                feature_id=str(feature_id),
                feature_type=feature_type,
                geometry_refs=geometry_refs,
                parameter_ids=parameter_ids,
                segment_ids=segment_ids,
                confidence=float(rule.get("confidence", 0.9)),
                provenance=f"reviewed_feature_labels.yaml::{rule.get('rule_id', feature_type)}",
            )
        )
    return bindings


def derive_key_parameters(manifest: dict, labels: dict, prior: dict | None = None) -> dict:
    """Derive first-pass single-cell parameters from reviewed feature refs."""
    prior = prior or load_expert_prior()[0]
    faces = {face["face_id"]: face for face in manifest.get("faces", [])}
    confirmed = labels.get("confirmed_features", {}) if isinstance(labels, dict) else {}

    def refs(feature_type: str) -> list[dict]:
        found = []
        for feature in confirmed.values():
            if feature.get("type") == feature_type:
                for ref in feature.get("geometry_refs", []):
                    if str(ref).startswith("face:"):
                        face = faces.get(str(ref).split(":", 1)[1])
                        if face:
                            found.append(face)
        return found

    bbox = manifest.get("model_summary", {}).get("bbox", {})
    zmin = float(bbox["zmin"])
    zmax = float(bbox["zmax"])
    parameters: dict[str, dict] = {}
    feature_mappings = prior.get("feature_mappings", {})
    for feature_type, rule in feature_mappings.items():
        feature_faces = refs(str(feature_type))
        feature_ids = [
            str(feature_id)
            for feature_id, feature in confirmed.items()
            if feature.get("type") == feature_type
        ]
        _apply_extraction(
            parameters,
            feature_type=str(feature_type),
            rule=rule,
            feature_faces=feature_faces,
            feature_ids=feature_ids,
            bbox=bbox,
        )
    _ensure_default_parameters(parameters, bbox)
    parameters["_profile_control"] = _profile_controls(parameters, manifest, labels, prior)
    parameters["_profile_primitives"] = extract_profile_primitives(manifest, labels)
    return parameters


def _apply_extraction(
    parameters: dict,
    *,
    feature_type: str,
    rule: dict,
    feature_faces: list[dict],
    feature_ids: list[str],
    bbox: dict,
) -> None:
    extraction = str(rule.get("extraction", "semantic_only"))
    if extraction == "semantic_only":
        return
    if extraction == "bbox_span":
        zmin = float(bbox["zmin"])
        zmax = float(bbox["zmax"])
        values = {
            "cell_length": zmax - zmin,
            "half_cell_span_left": abs(zmin),
            "half_cell_span_right": abs(zmax),
        }
    elif extraction == "median_radius_and_max_z_span":
        radius = _median_radius(feature_faces)
        z_span = max((_z_span(face) for face in feature_faces), default=0.0)
        values = {}
        for parameter_id in rule.get("parameter_ids", []):
            parameter_id_s = str(parameter_id)
            if parameter_id_s.endswith("_radius_left") or parameter_id_s.endswith("_radius_right"):
                values[parameter_id_s] = radius
            elif parameter_id_s.endswith("_length_left") or parameter_id_s.endswith("_length_right"):
                values[parameter_id_s] = z_span
    elif extraction == "median_radius":
        value = _median_radius(feature_faces)
        values = {str(parameter_id): value for parameter_id in rule.get("parameter_ids", [])}
    elif extraction == "max_radial_extent":
        value = max((_face_rmax(face) for face in feature_faces), default=abs(float(bbox.get("xmax", 0.0))))
        values = {str(parameter_id): value for parameter_id in rule.get("parameter_ids", [])}
    elif extraction == "half_local_radial_span":
        value = max((_face_rmax(face) - _face_rmin(face) for face in feature_faces), default=0.0) / 2.0
        values = {str(parameter_id): value for parameter_id in rule.get("parameter_ids", [])}
    else:
        raise ValueError(f"Unsupported expert prior extraction: {extraction} for {feature_type}")

    for parameter_id, value in values.items():
        if value is None:
            continue
        parameters[parameter_id] = _param(
            float(value),
            feature_ids,
            extraction,
            rule_id=str(rule.get("rule_id", feature_type)),
            affects_generated_step=bool(rule.get("affects_generated_step", False)),
            affects_translator=bool(rule.get("affects_translator", False)),
            confidence=float(rule.get("confidence", 0.85)),
        )


def _ensure_default_parameters(parameters: dict, bbox: dict) -> None:
    zmin = float(bbox["zmin"])
    zmax = float(bbox["zmax"])
    defaults = {
        "beam_pipe_radius_left": 44.0,
        "beam_pipe_radius_right": 44.0,
        "beam_pipe_length_left": 0.0,
        "beam_pipe_length_right": 0.0,
        "iris_radius": parameters.get("beam_pipe_radius_left", {}).get("value", 44.0),
        "equator_radius": abs(float(bbox.get("xmax", 232.193))),
        "cell_length": zmax - zmin,
        "half_cell_span_left": abs(zmin),
        "half_cell_span_right": abs(zmax),
        "nose_radius_left": 10.0,
        "nose_radius_right": 10.0,
        "blend_radius_left": 37.5,
        "blend_radius_right": 37.5,
        "transition_length_left": 65.0,
        "transition_length_right": 65.0,
    }
    for parameter_id, value in defaults.items():
        parameters.setdefault(
            parameter_id,
            _param(value, [], "emergency_fallback", rule_id="fallback", affects_generated_step=False, affects_translator=False, confidence=0.2),
        )


def _profile_controls(parameters: dict, manifest: dict, labels: dict, prior: dict) -> dict:
    controls = {}
    bbox = manifest.get("model_summary", {}).get("bbox", {})
    for name, spec in prior.get("grammar", {}).get("profile_controls", {}).items():
        controls[str(name)] = _resolve_control(spec, parameters, manifest, labels, bbox)
    return controls


def _resolve_control(spec: dict, parameters: dict, manifest: dict, labels: dict, bbox: dict) -> float:
    source = str(spec.get("source"))
    if source.startswith("bbox."):
        return float(bbox[source.split(".", 1)[1]])
    if source == "parameter":
        return float(parameters[str(spec["parameter"])]["value"])
    if source == "literal":
        return float(spec["value"])
    if source == "radial_inner_bound_above":
        threshold = float(parameters[str(spec["above_parameter"])]["value"])
        faces = _faces_for_types(manifest, labels, [str(item) for item in spec.get("feature_types", [])])
        candidates = [_face_rmin(face) for face in faces if _face_rmin(face) > threshold]
        if candidates:
            return float(min(candidates))
        fallback_value = float(parameters[str(spec["fallback_scale_of"])]["value"])
        return fallback_value * float(spec.get("fallback_scale", 1.0))
    raise ValueError(f"Unsupported profile control source: {source}")


def _faces_for_types(manifest: dict, labels: dict, feature_types: list[str]) -> list[dict]:
    faces = {face["face_id"]: face for face in manifest.get("faces", [])}
    confirmed = labels.get("confirmed_features", {}) if isinstance(labels, dict) else {}
    found = []
    for feature in confirmed.values():
        if feature.get("type") in feature_types:
            for ref in feature.get("geometry_refs", []):
                if str(ref).startswith("face:"):
                    face = faces.get(str(ref).split(":", 1)[1])
                    if face:
                        found.append(face)
    return found


def _median_radius(faces: list[dict]) -> float | None:
    radii = [float(face.get("radius")) for face in faces if face.get("radius") is not None]
    return float(median(radii)) if radii else None


def _face_rmax(face: dict) -> float:
    bbox = face.get("bbox", {})
    return max(abs(float(bbox.get(key, 0.0))) for key in ("xmin", "xmax", "ymin", "ymax"))


def _face_rmin(face: dict) -> float:
    relation = face.get("axis_relation", {})
    if isinstance(relation.get("r_range"), list):
        return float(relation["r_range"][0])
    return 0.0


def _z_span(face: dict) -> float:
    bbox = face.get("bbox", {})
    return abs(float(bbox.get("zmax", 0.0)) - float(bbox.get("zmin", 0.0)))


def _param(
    value: float,
    feature_refs: list[str],
    provenance: str,
    *,
    rule_id: str,
    affects_generated_step: bool,
    affects_translator: bool,
    confidence: float,
) -> dict:
    return {
        "value": float(value),
        "unit": "mm",
        "provenance": provenance,
        "feature_refs": feature_refs,
        "prior_rule_id": rule_id,
        "affects_generated_step": affects_generated_step,
        "affects_translator": affects_translator,
        "confidence": confidence,
        "required": True,
    }
