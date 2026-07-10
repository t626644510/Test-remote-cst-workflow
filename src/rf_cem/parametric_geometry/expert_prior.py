"""Expert prior loading and validation for RF-CEM parametric geometry."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml


PRIOR_SCHEMA_VERSION = "expert_prior.v0"
DEFAULT_PRIOR_PATH = Path(__file__).resolve().parent / "priors" / "axisymmetric_single_cell.v0.yaml"

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "model_family",
    "units",
    "target_body",
    "axis",
    "feature_mappings",
    "grammar",
    "fit_policy",
    "validation",
    "interface_policy",
    "human_notes",
}


class ExpertPriorError(ValueError):
    """Raised when an expert prior is structurally invalid."""


def load_expert_prior(*, appendix: Path | None = None, explicit_prior: Path | None = None) -> tuple[dict, dict]:
    """Load built-in prior and merge case/explicit overrides.

    Precedence is explicit prior > case prior > built-in prior. Unknown additive
    fields are preserved so future LLM-generated annotations are not lost.
    """
    built_in = _read_yaml(DEFAULT_PRIOR_PATH)
    sources = [{"kind": "built_in", "path": str(DEFAULT_PRIOR_PATH)}]
    resolved = copy.deepcopy(built_in)
    case_prior = appendix / "expert_prior.v0.yaml" if appendix is not None else None
    if case_prior is not None and case_prior.exists():
        resolved = _deep_merge(resolved, _read_yaml(case_prior))
        sources.append({"kind": "case", "path": str(case_prior)})
    if explicit_prior is not None:
        resolved = _deep_merge(resolved, _read_yaml(explicit_prior))
        sources.append({"kind": "explicit", "path": str(explicit_prior)})
    warnings = validate_expert_prior(resolved)
    return resolved, {
        "schema_version": "resolved_expert_prior_metadata.v0",
        "sources": sources,
        "warnings": warnings,
        "precedence": ["explicit", "case", "built_in"],
    }


def validate_expert_prior(prior: dict) -> list[str]:
    """Validate the v0 expert prior and return non-blocking warnings."""
    if prior.get("schema_version") != PRIOR_SCHEMA_VERSION:
        raise ExpertPriorError(f"Unsupported expert prior schema_version: {prior.get('schema_version')!r}")
    missing = sorted(REQUIRED_TOP_LEVEL - set(prior))
    if missing:
        raise ExpertPriorError(f"expert prior missing required sections: {', '.join(missing)}")
    if not isinstance(prior.get("feature_mappings"), dict) or not prior["feature_mappings"]:
        raise ExpertPriorError("expert prior feature_mappings must be a non-empty mapping")
    if not isinstance(prior.get("grammar", {}).get("segment_templates"), dict):
        raise ExpertPriorError("expert prior grammar.segment_templates must be a mapping")
    warnings = []
    for feature_type, rule in prior["feature_mappings"].items():
        if "rule_id" not in rule:
            raise ExpertPriorError(f"feature mapping {feature_type} is missing rule_id")
        if "parameter_ids" not in rule or "segment_ids" not in rule:
            raise ExpertPriorError(f"feature mapping {feature_type} must define parameter_ids and segment_ids")
        if rule.get("extraction") in {"python_eval", "eval", "code"}:
            raise ExpertPriorError(f"feature mapping {feature_type} uses forbidden extraction {rule.get('extraction')}")
    if prior.get("interface_policy", {}).get("unknown_fields") != "preserve":
        warnings.append("interface_policy.unknown_fields is not 'preserve'; v0 consumers still preserve additive fields")
    return warnings


def write_resolved_prior(base_path: Path, prior: dict, metadata: dict) -> tuple[Path, Path]:
    """Write resolved prior as YAML and JSON, returning both paths."""
    yaml_path = Path(str(base_path) + ".yaml")
    json_path = Path(str(base_path) + ".json")
    payload = {
        "resolved_prior": prior,
        "metadata": metadata,
    }
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return yaml_path, json_path


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"expert prior not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ExpertPriorError(f"expert prior must be a YAML mapping: {path}")
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    result: dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
