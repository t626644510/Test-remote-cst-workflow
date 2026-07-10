"""Shared types and file helpers for literature semantic packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml


SEMANTICS_SCHEMA_VERSION = "literature_semantics.v0"
DRAFT_PRIOR_SCHEMA_VERSION = "expert_prior.draft.v0"

REVIEW_STATUSES = {
    "pending",
    "accepted",
    "accepted_as_soft_only",
    "rejected",
    "needs_more_evidence",
}
MERGEABLE_REVIEW_STATUSES = {"accepted", "accepted_as_soft_only"}

SEMANTIC_ITEM_SECTIONS = (
    "named_features",
    "shape_motifs",
    "curve_priors",
    "parameter_ranges",
    "optimization_objectives",
    "physical_constraints",
)


@dataclass(frozen=True)
class ValidationIssue:
    """A validation issue found in an uploaded semantic package."""

    severity: str
    path: str
    message: str


class LiteratureSemanticsError(ValueError):
    """Raised when a literature semantic package cannot be consumed."""


class PriorDraftError(ValueError):
    """Raised when an expert prior draft cannot be merged."""


def read_structured_file(path: Path) -> dict[str, Any]:
    """Read a JSON/YAML mapping with UTF-8 encoding."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raise LiteratureSemanticsError(f"unsupported structured file extension: {path}")
    if not isinstance(data, dict):
        raise LiteratureSemanticsError(f"structured file must contain a mapping: {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    """Write a deterministic UTF-8 JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: object) -> None:
    """Write a UTF-8 YAML file preserving key order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def semantic_package_file(path: Path) -> Path:
    """Resolve a user-supplied package path to the semantic JSON/YAML file."""
    if path.is_dir():
        for name in ("literature_semantics.v0.json", "literature_semantics.v0.yaml", "literature_semantics.v0.yml"):
            candidate = path / name
            if candidate.exists():
                return candidate
        raise LiteratureSemanticsError(f"semantic package directory does not contain literature_semantics.v0.json: {path}")
    return path
