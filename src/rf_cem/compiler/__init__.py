"""RF boundary compiler layer joining semantic and representation contracts."""

from .adapters import PreparedCompileCase, R2SourceSet, prepare_r2_cases
from .artifacts import R2Bundle, write_r2_bundle
from .contracts import (
    BaselineContract,
    BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION,
    BoundaryContinuityPolicy,
    COMPILE_RECORD_SCHEMA_VERSION,
    COMPILE_REQUEST_SCHEMA_VERSION,
    COMPILER_VERSION,
    CompileContractError,
    CompileRecord,
    CompileRequest,
    ContinuityCheck,
    ContinuityInterfaceOverride,
    ContinuityRequirement,
    ContractSourceRef,
    EndpointConstraint,
    LandmarkGeometryBinding,
    NativeArtifactRef,
    OutputArtifactRef,
    RegionRepresentationBinding,
    SourceNativeProvenance,
    default_boundary_continuity_policy,
    load_compile_record,
)
from .core import CompileResult, GeometryKernel, ProfileCompiler

ARCHITECTURE_LAYER = "compiler"

__all__ = [
    "ARCHITECTURE_LAYER",
    "BaselineContract",
    "BOUNDARY_CONTINUITY_POLICY_SCHEMA_VERSION",
    "BoundaryContinuityPolicy",
    "COMPILE_RECORD_SCHEMA_VERSION",
    "COMPILE_REQUEST_SCHEMA_VERSION",
    "COMPILER_VERSION",
    "CompileContractError",
    "CompileRecord",
    "CompileRequest",
    "CompileResult",
    "ContinuityCheck",
    "ContinuityInterfaceOverride",
    "ContinuityRequirement",
    "ContractSourceRef",
    "EndpointConstraint",
    "GeometryKernel",
    "LandmarkGeometryBinding",
    "NativeArtifactRef",
    "OutputArtifactRef",
    "PreparedCompileCase",
    "ProfileCompiler",
    "R2Bundle",
    "R2SourceSet",
    "RegionRepresentationBinding",
    "SourceNativeProvenance",
    "default_boundary_continuity_policy",
    "load_compile_record",
    "prepare_r2_cases",
    "write_r2_bundle",
]
