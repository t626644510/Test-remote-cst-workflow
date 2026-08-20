"""Strict helpers shared by RF-CEM R5 result contracts.

The R5 contract layer is deliberately independent of CST.  It validates
captured or planned physics records, but it never starts a solver or opens a
project.
"""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

RF_UNITS = frozenset(
    {
        "1",
        "MHz",
        "ohm",
        "J",
        "MV/m",
        "mT",
        "mT/(MV/m)",
        "W",
    }
)


class PhysicsContractError(ValueError):
    """Raised when an R5 result, mode, field, or provenance contract is invalid."""


def mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhysicsContractError(f"{path} must be an object")
    return value


def sequence(value: object, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PhysicsContractError(f"{path} must be an array")
    return value


def exact_keys(value: Mapping[str, Any], required: set[str], path: str) -> None:
    actual = set(value)
    if actual != required:
        raise PhysicsContractError(
            f"{path} keys mismatch; missing={sorted(required - actual)}, "
            f"extra={sorted(actual - required)}"
        )


def string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhysicsContractError(f"{path} must be a non-empty string")
    return value


def optional_string(value: object, path: str) -> str | None:
    return None if value is None else string(value, path)


def boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise PhysicsContractError(f"{path} must be boolean")
    return value


def number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PhysicsContractError(f"{path} must be finite")
    return result


def optional_number(value: object, path: str) -> float | None:
    return None if value is None else number(value, path)


def positive(value: object, path: str) -> float:
    result = number(value, path)
    if result <= 0.0:
        raise PhysicsContractError(f"{path} must be positive")
    return result


def non_negative(value: object, path: str) -> float:
    result = number(value, path)
    if result < 0.0:
        raise PhysicsContractError(f"{path} must be non-negative")
    return result


def integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PhysicsContractError(f"{path} must be an integer")
    return value


def positive_integer(value: object, path: str) -> int:
    result = integer(value, path)
    if result <= 0:
        raise PhysicsContractError(f"{path} must be positive")
    return result


def optional_positive_integer(value: object, path: str) -> int | None:
    return None if value is None else positive_integer(value, path)


def normalized_hash(value: object, path: str) -> str:
    result = string(value, path)
    if not _HASH_RE.fullmatch(result):
        raise PhysicsContractError(f"{path} must be a lowercase SHA-256")
    return result


def relative_path(value: object, path: str) -> str:
    result = string(value, path)
    pure = PurePosixPath(result)
    if pure.is_absolute() or ".." in pure.parts or "\\" in result or result != pure.as_posix():
        raise PhysicsContractError(
            f"{path} must be a normalized repository-relative POSIX path"
        )
    return result


def enum(value: object, allowed: set[str] | frozenset[str], path: str) -> str:
    result = string(value, path)
    if result not in allowed:
        raise PhysicsContractError(f"{path} has unsupported value: {result}")
    return result


def unit(value: object, path: str) -> str:
    return enum(value, RF_UNITS, path)


def string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(string(item, f"{path}[]") for item in sequence(value, path))


def finite_json(value: object, path: str) -> None:
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PhysicsContractError(
            f"{path} must contain only finite JSON-compatible values"
        ) from exc


def read_json_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_constant(token, label),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PhysicsContractError(f"cannot read {label}: {path}") from exc
    return mapping(value, label)


def resolve_inside(root: Path, relative: str, label: str) -> Path:
    """Resolve one normalized contract path without allowing root escape."""

    root = root.resolve()
    value = relative_path(relative, label)
    candidate = (root / Path(*PurePosixPath(value).parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:  # pragma: no cover - defensive after lexical check
        raise PhysicsContractError(f"{label} escapes its declared root") from exc
    return candidate


def _reject_constant(token: str, label: str) -> None:
    raise PhysicsContractError(f"{label} contains invalid constant: {token}")


__all__ = [
    "PhysicsContractError",
    "RF_UNITS",
    "boolean",
    "enum",
    "exact_keys",
    "finite_json",
    "integer",
    "mapping",
    "non_negative",
    "normalized_hash",
    "number",
    "optional_number",
    "optional_positive_integer",
    "optional_string",
    "positive",
    "positive_integer",
    "read_json_mapping",
    "relative_path",
    "resolve_inside",
    "sequence",
    "string",
    "string_tuple",
    "unit",
]
