"""Shared strict helpers for RF-CEM R4 observation contracts."""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_UNITS = frozenset(
    {
        "1",
        "bool",
        "count",
        "mm",
        "mm^2",
        "mm^3",
        "1/mm",
        "deg",
    }
)


class ObservationContractError(ValueError):
    """Raised when an R4 observation or descriptor violates its contract."""


class ConstraintContractError(ObservationContractError):
    """Raised when an R4 engineering constraint is invalid or unevaluable."""


def mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ObservationContractError(f"{path} must be an object")
    return value


def sequence(value: object, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ObservationContractError(f"{path} must be an array")
    return value


def exact_keys(value: Mapping[str, Any], required: set[str], path: str) -> None:
    actual = set(value)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise ObservationContractError(
            f"{path} keys mismatch; missing={missing}, extra={extra}"
        )


def string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationContractError(f"{path} must be a non-empty string")
    return value


def optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return string(value, path)


def number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationContractError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ObservationContractError(f"{path} must be finite")
    return result


def non_negative(value: object, path: str) -> float:
    result = number(value, path)
    if result < 0.0:
        raise ObservationContractError(f"{path} must be non-negative")
    return result


def positive(value: object, path: str) -> float:
    result = number(value, path)
    if result <= 0.0:
        raise ObservationContractError(f"{path} must be positive")
    return result


def integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationContractError(f"{path} must be an integer")
    return value


def non_negative_integer(value: object, path: str) -> int:
    result = integer(value, path)
    if result < 0:
        raise ObservationContractError(f"{path} must be non-negative")
    return result


def boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ObservationContractError(f"{path} must be boolean")
    return value


def normalized_hash(value: object, path: str) -> str:
    result = string(value, path)
    if not _HASH_RE.fullmatch(result):
        raise ObservationContractError(f"{path} must be a lowercase SHA-256")
    return result


def relative_path(value: object, path: str) -> str:
    result = string(value, path)
    pure = PurePosixPath(result)
    if pure.is_absolute() or ".." in pure.parts or "\\" in result:
        raise ObservationContractError(
            f"{path} must be a normalized repository-relative POSIX path"
        )
    return result


def unit(value: object, path: str) -> str:
    result = string(value, path)
    if result not in SUPPORTED_UNITS:
        raise ObservationContractError(f"{path} has unsupported unit: {result}")
    return result


def string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(string(item, f"{path}[]") for item in sequence(value, path))


def finite_json(value: object, path: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ObservationContractError(
            f"{path} must contain only finite JSON-compatible values"
        ) from exc


def read_json_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_constant(token, label),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ObservationContractError(f"cannot read {label}: {path}") from exc
    return mapping(value, label)


def _reject_constant(token: str, label: str) -> None:
    raise ObservationContractError(f"{label} contains invalid constant: {token}")


__all__ = [
    "ConstraintContractError",
    "ObservationContractError",
    "SUPPORTED_UNITS",
    "boolean",
    "exact_keys",
    "finite_json",
    "integer",
    "mapping",
    "non_negative",
    "non_negative_integer",
    "normalized_hash",
    "number",
    "optional_string",
    "positive",
    "read_json_mapping",
    "relative_path",
    "sequence",
    "string",
    "string_tuple",
    "unit",
]
