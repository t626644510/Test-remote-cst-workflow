"""Deterministic object identity helpers for immutable R5 contracts."""

from __future__ import annotations

from typing import Any

from rf_cem.semantic.contracts import canonical_sha256

from .common import PhysicsContractError, normalized_hash, string
from .references import ContractRef


def bind_identity(
    instance: object,
    *,
    content_mapping: dict[str, Any],
    id_attribute: str,
    id_prefix: str,
    label: str,
) -> None:
    """Populate or verify one ``<prefix>.<digest>`` immutable identity."""

    content = canonical_sha256(content_mapping)
    expected_id = f"{id_prefix}.{content[:16]}"
    current_id = getattr(instance, id_attribute)
    current_hash = getattr(instance, "content_sha256")
    if current_id:
        if string(current_id, f"{label}.{id_attribute}") != expected_id:
            raise PhysicsContractError(f"{label} ID does not match canonical content")
    else:
        object.__setattr__(instance, id_attribute, expected_id)
    if current_hash:
        if normalized_hash(current_hash, f"{label}.content_sha256") != content:
            raise PhysicsContractError(f"{label} hash does not match canonical content")
    else:
        object.__setattr__(instance, "content_sha256", content)


def identity_ref(
    *,
    contract_kind: str,
    schema_version: str,
    object_id: str,
    content_sha256: str,
) -> ContractRef:
    return ContractRef(contract_kind, schema_version, object_id, content_sha256)


__all__ = ["bind_identity", "identity_ref"]
