"""No-CST RF result, mode, field, convergence, and provenance contracts."""

from .artifacts import (
    MANIFEST_FILE,
    R5Bundle,
    R5CaseArtifacts,
    R5ReadinessSourceSet,
    R5_BUNDLE_PREFIX,
    R5_BUNDLE_SCHEMA_VERSION,
    R5_MANIFEST_SCHEMA_VERSION,
    load_r5_bundle,
    write_r5_readiness_bundle,
)
from .contracts import *  # noqa: F403 - contract package is the public surface
from .contracts import __all__ as _contract_exports


ARCHITECTURE_LAYER = "physics"

__all__ = [
    "ARCHITECTURE_LAYER",
    "MANIFEST_FILE",
    "R5Bundle",
    "R5CaseArtifacts",
    "R5ReadinessSourceSet",
    "R5_BUNDLE_PREFIX",
    "R5_BUNDLE_SCHEMA_VERSION",
    "R5_MANIFEST_SCHEMA_VERSION",
    "load_r5_bundle",
    "write_r5_readiness_bundle",
    *_contract_exports,
]
