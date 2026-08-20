"""RF-CEM Workbench W0-W3 derived registry and local read-only server."""

from .indexer import (
    REQUIRED_W0_INSTANCES,
    WorkbenchIndexError,
    WorkbenchSourceSet,
    rebuild_workbench,
)
from .registry import (
    BuildSummary,
    RegistryReader,
    WORKBENCH_SCHEMA_VERSION,
    WorkbenchRegistryError,
)
from .server import LOOPBACK_HOST, WorkbenchServer

__all__ = [
    "BuildSummary",
    "LOOPBACK_HOST",
    "REQUIRED_W0_INSTANCES",
    "RegistryReader",
    "WORKBENCH_SCHEMA_VERSION",
    "WorkbenchIndexError",
    "WorkbenchRegistryError",
    "WorkbenchServer",
    "WorkbenchSourceSet",
    "rebuild_workbench",
]
