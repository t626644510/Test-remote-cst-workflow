"""Portable, repository-relative Workbench Desktop profile contracts."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Any, Mapping, Protocol

from .registry import (
    BuildSummary,
    RegistryReader,
    WorkbenchRegistryError,
    file_sha256,
)

WORKBENCH_PROFILE_SCHEMA_VERSION = "rf_cem_workbench_profile.v0"
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


class WorkbenchProfileError(ValueError):
    """Raised when a portable profile or its resolved source set is invalid."""


class _WorkbenchSourceSetContract(Protocol):
    repo_root: Path
    family_profile: Path
    family_profile_validation: Path | None
    architecture_document: Path | None
    literature_packages: tuple[Path, ...]
    review_sessions: tuple[Path, ...]
    family_grammar: Path | None
    instance_boundary_graphs: tuple[Path, ...]
    instance_graph_diff: Path | None
    compile_records: tuple[Path, ...]
    family_induction_bundle: Path | None
    observation_contract_bundle: Path | None


@dataclass(frozen=True)
class WorkbenchProfile:
    """Strict repository-relative W0-W4 recipe with a reserved W5 input."""

    profile_id: str
    database: str
    family_profile: str
    family_profile_validation: str | None
    architecture_document: str | None
    literature_packages: tuple[str, ...]
    review_sessions: tuple[str, ...]
    family_grammar: str | None
    instance_boundary_graphs: tuple[str, ...]
    instance_graph_diff: str | None
    compile_records: tuple[str, ...]
    family_induction_bundle: str | None
    observation_contract_bundle: str | None
    optional_w5_bundle: str | None
    schema_version: str = WORKBENCH_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKBENCH_PROFILE_SCHEMA_VERSION:
            raise WorkbenchProfileError("unsupported Workbench profile schema")
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise WorkbenchProfileError("profile_id must be a non-empty string")
        _relative_path(self.database, "database")
        _relative_path(self.family_profile, "family_profile")
        for value, label in (
            (self.family_profile_validation, "family_profile_validation"),
            (self.architecture_document, "architecture_document"),
            (self.family_grammar, "family_grammar"),
            (self.instance_graph_diff, "instance_graph_diff"),
            (self.family_induction_bundle, "family_induction_bundle"),
            (self.observation_contract_bundle, "observation_contract_bundle"),
            (self.optional_w5_bundle, "optional_w5_bundle"),
        ):
            if value is not None:
                _relative_path(value, label)
        for values, label in (
            (self.literature_packages, "literature_packages"),
            (self.review_sessions, "review_sessions"),
            (self.instance_boundary_graphs, "instance_boundary_graphs"),
            (self.compile_records, "compile_records"),
        ):
            if len(values) != len(set(values)):
                raise WorkbenchProfileError(f"{label} paths must be unique")
            for value in values:
                _relative_path(value, f"{label}[]")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "database": self.database,
            "family_profile": self.family_profile,
            "family_profile_validation": self.family_profile_validation,
            "architecture_document": self.architecture_document,
            "literature_packages": list(self.literature_packages),
            "review_sessions": list(self.review_sessions),
            "family_grammar": self.family_grammar,
            "instance_boundary_graphs": list(self.instance_boundary_graphs),
            "instance_graph_diff": self.instance_graph_diff,
            "compile_records": list(self.compile_records),
            "family_induction_bundle": self.family_induction_bundle,
            "observation_contract_bundle": self.observation_contract_bundle,
            "optional_w5_bundle": self.optional_w5_bundle,
        }

    def declared_source_paths(self) -> tuple[str, ...]:
        """Return every declared W0-W5 source path, excluding the database."""

        required = (
            self.family_profile,
            *self.literature_packages,
            *self.review_sessions,
            *self.instance_boundary_graphs,
            *self.compile_records,
        )
        optional = tuple(
            value
            for value in (
                self.family_profile_validation,
                self.architecture_document,
                self.family_grammar,
                self.instance_graph_diff,
                self.family_induction_bundle,
                self.observation_contract_bundle,
                self.optional_w5_bundle,
            )
            if value is not None
        )
        return (*required, *optional)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkbenchProfile":
        mapping = _mapping(value, "workbench profile")
        required = {
            "schema_version",
            "profile_id",
            "database",
            "family_profile",
            "family_profile_validation",
            "architecture_document",
            "literature_packages",
            "review_sessions",
            "family_grammar",
            "instance_boundary_graphs",
            "instance_graph_diff",
            "compile_records",
            "family_induction_bundle",
            "observation_contract_bundle",
            "optional_w5_bundle",
        }
        if set(mapping) != required:
            raise WorkbenchProfileError(
                "Workbench profile keys mismatch; "
                f"missing={sorted(required - set(mapping))}, "
                f"extra={sorted(set(mapping) - required)}"
            )
        return cls(
            schema_version=_string(mapping["schema_version"], "schema_version"),
            profile_id=_string(mapping["profile_id"], "profile_id"),
            database=_relative_path(mapping["database"], "database"),
            family_profile=_relative_path(
                mapping["family_profile"], "family_profile"
            ),
            family_profile_validation=_optional_relative_path(
                mapping["family_profile_validation"],
                "family_profile_validation",
            ),
            architecture_document=_optional_relative_path(
                mapping["architecture_document"], "architecture_document"
            ),
            literature_packages=_relative_path_tuple(
                mapping["literature_packages"], "literature_packages"
            ),
            review_sessions=_relative_path_tuple(
                mapping["review_sessions"], "review_sessions"
            ),
            family_grammar=_optional_relative_path(
                mapping["family_grammar"], "family_grammar"
            ),
            instance_boundary_graphs=_relative_path_tuple(
                mapping["instance_boundary_graphs"],
                "instance_boundary_graphs",
            ),
            instance_graph_diff=_optional_relative_path(
                mapping["instance_graph_diff"], "instance_graph_diff"
            ),
            compile_records=_relative_path_tuple(
                mapping["compile_records"], "compile_records"
            ),
            family_induction_bundle=_optional_relative_path(
                mapping["family_induction_bundle"],
                "family_induction_bundle",
            ),
            observation_contract_bundle=_optional_relative_path(
                mapping["observation_contract_bundle"],
                "observation_contract_bundle",
            ),
            optional_w5_bundle=_optional_relative_path(
                mapping["optional_w5_bundle"], "optional_w5_bundle"
            ),
        )

    def resolve(self, repo_root: Path, *, profile_path: Path) -> "ResolvedWorkbenchProfile":
        indexer = import_module(".".join(("rf_cem", "workbench", "indexer")))
        WorkbenchSourceSet = indexer.WorkbenchSourceSet
        root = _validated_repo_root(repo_root)
        resolved_profile_path = profile_path.resolve()
        _inside(root, resolved_profile_path, "profile path")
        database = _inside(root, root / self.database, "database", must_exist=False)
        optional_w5 = (
            None
            if self.optional_w5_bundle is None
            else _inside(
                root,
                root / self.optional_w5_bundle,
                "optional W5 bundle",
                must_exist=False,
            )
        )
        sources = WorkbenchSourceSet(
            repo_root=root,
            family_profile=_source_inside(root, self.family_profile, "family profile"),
            family_profile_validation=_optional_inside(
                root,
                self.family_profile_validation,
                "family profile validation",
            ),
            architecture_document=_optional_inside(
                root, self.architecture_document, "architecture document"
            ),
            literature_packages=tuple(
                _source_inside(root, value, "literature package")
                for value in self.literature_packages
            ),
            review_sessions=tuple(
                _source_inside(root, value, "review session")
                for value in self.review_sessions
            ),
            family_grammar=_optional_inside(
                root, self.family_grammar, "family grammar"
            ),
            instance_boundary_graphs=tuple(
                _source_inside(root, value, "instance boundary graph")
                for value in self.instance_boundary_graphs
            ),
            instance_graph_diff=_optional_inside(
                root, self.instance_graph_diff, "instance graph diff"
            ),
            compile_records=tuple(
                _source_inside(root, value, "compile record")
                for value in self.compile_records
            ),
            family_induction_bundle=_optional_inside(
                root, self.family_induction_bundle, "family induction bundle"
            ),
            observation_contract_bundle=_optional_inside(
                root,
                self.observation_contract_bundle,
                "observation contract bundle",
            ),
        )
        return ResolvedWorkbenchProfile(
            profile=self,
            profile_path=resolved_profile_path,
            repo_root=root,
            database=database,
            sources=sources,
            optional_w5_bundle=optional_w5,
        )


@dataclass(frozen=True)
class ResolvedWorkbenchProfile:
    profile: WorkbenchProfile
    profile_path: Path
    repo_root: Path
    database: Path
    sources: _WorkbenchSourceSetContract
    optional_w5_bundle: Path | None

    def declared_source_paths(self) -> tuple[Path, ...]:
        values = [
            self.sources.family_profile,
            *self.sources.literature_packages,
            *self.sources.review_sessions,
            *self.sources.instance_boundary_graphs,
            *self.sources.compile_records,
        ]
        values.extend(
            item
            for item in (
                self.sources.family_profile_validation,
                self.sources.architecture_document,
                self.sources.family_grammar,
                self.sources.instance_graph_diff,
                self.sources.family_induction_bundle,
                self.sources.observation_contract_bundle,
                self.optional_w5_bundle,
            )
            if item is not None
        )
        return tuple(values)

    def missing_sources(self) -> tuple[Path, ...]:
        return tuple(path for path in self.declared_source_paths() if not path.exists())


@dataclass(frozen=True)
class WorkbenchProfileStatus:
    profile_id: str
    database: Path
    database_state: str
    source_statuses: tuple[Mapping[str, Any], ...]
    diagnostic: str

    @property
    def fresh(self) -> bool:
        return self.database_state == "fresh"

    @property
    def rebuild_required(self) -> bool:
        return self.database_state in {"missing", "stale", "invalid"}

    def to_mapping(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "database": str(self.database),
            "database_state": self.database_state,
            "fresh": self.fresh,
            "rebuild_required": self.rebuild_required,
            "source_statuses": [dict(item) for item in self.source_statuses],
            "diagnostic": self.diagnostic,
        }


def load_workbench_profile(path: Path) -> WorkbenchProfile:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkbenchProfileError(f"cannot load Workbench profile: {path}: {exc}") from exc
    return WorkbenchProfile.from_mapping(_mapping(value, "workbench profile"))


def resolve_workbench_profile(
    repo_root: Path,
    profile_path: Path,
) -> ResolvedWorkbenchProfile:
    root = _validated_repo_root(repo_root)
    candidate = profile_path if profile_path.is_absolute() else root / profile_path
    path = _inside(root, candidate, "profile path")
    return load_workbench_profile(path).resolve(root, profile_path=path)


def inspect_workbench_profile(
    resolved: ResolvedWorkbenchProfile,
) -> WorkbenchProfileStatus:
    database = resolved.database
    missing_sources = resolved.missing_sources()
    if missing_sources:
        return WorkbenchProfileStatus(
            profile_id=resolved.profile.profile_id,
            database=database,
            database_state="blocked_missing_sources",
            source_statuses=tuple(
                {
                    "display_path": path.relative_to(resolved.repo_root).as_posix(),
                    "status": "missing",
                }
                for path in missing_sources
            ),
            diagnostic=(
                "profile source(s) are missing: "
                + ", ".join(
                    path.relative_to(resolved.repo_root).as_posix()
                    for path in missing_sources
                )
            ),
        )
    if not database.is_file():
        return WorkbenchProfileStatus(
            profile_id=resolved.profile.profile_id,
            database=database,
            database_state="missing",
            source_statuses=(),
            diagnostic="database is missing; complete profile sources are ready to rebuild",
        )
    try:
        reader = RegistryReader(database)
        metadata = reader.metadata()
        statuses = tuple(reader.audit_sources(resolved.repo_root))
    except (OSError, sqlite3.Error, WorkbenchRegistryError, ValueError) as exc:
        return WorkbenchProfileStatus(
            profile_id=resolved.profile.profile_id,
            database=database,
            database_state="invalid",
            source_statuses=(),
            diagnostic=f"database cannot be read: {exc}",
        )
    stale = [item for item in statuses if item.get("status") != "fresh"]
    expected_profile_path = resolved.profile_path.relative_to(
        resolved.repo_root
    ).as_posix()
    profile_binding_fresh = (
        metadata.get("workbench_profile_path") == expected_profile_path
        and metadata.get("workbench_profile_sha256")
        == file_sha256(resolved.profile_path)
    )
    profile_status = None
    if not profile_binding_fresh:
        profile_status = {
            "display_path": expected_profile_path,
            "status": "stale_profile_recipe",
        }
        stale.append(profile_status)
    return WorkbenchProfileStatus(
        profile_id=resolved.profile.profile_id,
        database=database,
        database_state="stale" if stale else "fresh",
        source_statuses=(
            statuses if profile_status is None else (*statuses, profile_status)
        ),
        diagnostic=(
            f"{len(stale)} indexed source/profile binding(s) are stale or missing"
            if stale
            else "database and indexed sources are fresh"
        ),
    )


def rebuild_workbench_profile(
    resolved: ResolvedWorkbenchProfile,
) -> BuildSummary:
    missing = resolved.missing_sources()
    if missing:
        raise WorkbenchProfileError(
            "cannot rebuild; profile sources are missing: "
            + ", ".join(path.as_posix() for path in missing)
        )
    resolved.database.parent.mkdir(parents=True, exist_ok=True)
    profile_relative = resolved.profile_path.relative_to(resolved.repo_root).as_posix()
    rebuild_workbench = import_module(
        ".".join(("rf_cem", "workbench", "indexer"))
    ).rebuild_workbench
    return rebuild_workbench(
        resolved.database,
        resolved.sources,
        registry_metadata={
            "workbench_profile_path": profile_relative,
            "workbench_profile_sha256": file_sha256(resolved.profile_path),
            "workbench_profile_schema_version": resolved.profile.schema_version,
        },
    )


def _validated_repo_root(value: Path) -> Path:
    root = value.resolve()
    if not root.is_dir() or not (root / "pyproject.toml").is_file() or not (
        root / "src" / "rf_cem" / "workbench"
    ).is_dir():
        raise WorkbenchProfileError(f"not an RF-CEM repository root: {root}")
    return root


def _inside(
    root: Path,
    value: Path,
    label: str,
    *,
    must_exist: bool = True,
) -> Path:
    resolved = value.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkbenchProfileError(f"{label} escapes repository root") from exc
    if must_exist and not resolved.exists():
        raise WorkbenchProfileError(f"{label} is missing: {resolved}")
    return resolved


def _source_inside(root: Path, value: str, label: str) -> Path:
    return _inside(root, root / value, label, must_exist=False)


def _optional_inside(root: Path, value: str | None, label: str) -> Path | None:
    return None if value is None else _source_inside(root, value, label)


def _relative_path(value: object, label: str) -> str:
    text = _string(value, label).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or _WINDOWS_ABSOLUTE_RE.match(text) or ".." in path.parts:
        raise WorkbenchProfileError(f"{label} must be repository-relative")
    return path.as_posix()


def _optional_relative_path(value: object, label: str) -> str | None:
    return None if value is None else _relative_path(value, label)


def _relative_path_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WorkbenchProfileError(f"{label} must be an array")
    return tuple(_relative_path(item, f"{label}[]") for item in value)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkbenchProfileError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkbenchProfileError(f"{label} must be a non-empty string")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise WorkbenchProfileError(f"{label} contains control characters")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


__all__ = [
    "ResolvedWorkbenchProfile",
    "WORKBENCH_PROFILE_SCHEMA_VERSION",
    "WorkbenchProfile",
    "WorkbenchProfileError",
    "WorkbenchProfileStatus",
    "inspect_workbench_profile",
    "load_workbench_profile",
    "rebuild_workbench_profile",
    "resolve_workbench_profile",
]
