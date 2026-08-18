"""Generic no-CST RF-CEM family profile contract and frozen-source adapters."""

from .adapters import Rf500FamilyInstanceAdapter, Sls2FamilyInstanceAdapter
from .builder import (
    build_family_profile,
    build_source_binding_manifest,
    build_validation_report,
    write_stage_c_bundle,
)
from .core import (
    CANONICALIZATION_CONTRACT_ID,
    EXCLUDED_METRICS,
    FAMILY_ID,
    FAMILY_IDENTITY,
    FAMILY_INSTANCE_SCHEMA_VERSION,
    FAMILY_PROFILE_SCHEMA_VERSION,
    FamilyInstance,
    FamilyProfile,
    FamilyProfileError,
    canonical_json_bytes,
    canonical_sha256,
    load_family_profile_schema,
    load_profile,
    make_family_profile,
    validate_profile_mapping,
    verify_round_trip,
    write_profile,
)

__all__ = [
    "CANONICALIZATION_CONTRACT_ID",
    "EXCLUDED_METRICS",
    "FAMILY_ID",
    "FAMILY_IDENTITY",
    "FAMILY_INSTANCE_SCHEMA_VERSION",
    "FAMILY_PROFILE_SCHEMA_VERSION",
    "FamilyInstance",
    "FamilyProfile",
    "FamilyProfileError",
    "Rf500FamilyInstanceAdapter",
    "Sls2FamilyInstanceAdapter",
    "build_family_profile",
    "build_source_binding_manifest",
    "build_validation_report",
    "canonical_json_bytes",
    "canonical_sha256",
    "load_family_profile_schema",
    "load_profile",
    "make_family_profile",
    "validate_profile_mapping",
    "verify_round_trip",
    "write_profile",
    "write_stage_c_bundle",
]
