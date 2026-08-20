"""RF boundary compiler layer joining semantic and representation contracts."""

from .adapters import PreparedCompileCase, R2SourceSet, prepare_r2_cases
from .artifacts import R2Bundle, write_r2_bundle
from .contracts import (
    BaselineContract,
    COMPILE_RECORD_SCHEMA_VERSION,
    COMPILE_REQUEST_SCHEMA_VERSION,
    COMPILER_VERSION,
    CompileContractError,
    CompileRecord,
    CompileRequest,
    ContinuityCheck,
    ContractSourceRef,
    LandmarkGeometryBinding,
    NativeArtifactRef,
    OutputArtifactRef,
    RegionRepresentationBinding,
    SourceNativeProvenance,
    load_compile_record,
)
from .core import CompileResult, GeometryKernel, ProfileCompiler

ARCHITECTURE_LAYER = "compiler"

__all__ = [
    "ARCHITECTURE_LAYER",
    "BaselineContract",
    "COMPILE_RECORD_SCHEMA_VERSION",
    "COMPILE_REQUEST_SCHEMA_VERSION",
    "COMPILER_VERSION",
    "CompileContractError",
    "CompileRecord",
    "CompileRequest",
    "CompileResult",
    "ContinuityCheck",
    "ContractSourceRef",
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
    "load_compile_record",
    "prepare_r2_cases",
    "write_r2_bundle",
]
