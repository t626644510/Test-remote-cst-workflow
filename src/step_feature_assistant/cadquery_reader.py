"""CadQuery/OCP backend wrapper for STEP geometry manifests.

CadQuery 2.5.2 imports successfully on the target Windows/Python 3.9
environment, but importing ``cadquery.occ_impl`` can crash the interpreter at
normal shutdown on this machine.  The public reader therefore runs the CAD
kernel code in a short-lived worker process that exits via ``os._exit(0)`` after
writing JSON.  The main CLI process never imports CadQuery directly.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Optional

from .step_reader import read_step_topology
from .topology_analyzer import build_geometry_manifest


class CadQueryBackendError(RuntimeError):
    """Raised when the CadQuery backend cannot produce a manifest."""


def build_geometry_manifest_for_backend(
    step_file: Path,
    axis: str,
    backend: str,
    mesh_output: Optional[Path] = None,
) -> dict:
    """Build a geometry manifest using the selected backend."""
    backend_l = backend.lower()
    if backend_l == "fallback":
        return build_geometry_manifest(read_step_topology(step_file), axis)
    if backend_l == "cadquery":
        return read_cadquery_geometry_manifest(step_file, axis, mesh_output)
    if backend_l == "auto":
        try:
            manifest = read_cadquery_geometry_manifest(step_file, axis, mesh_output)
            manifest.setdefault("reader", {}).setdefault("backend_notes", []).append(
                "auto backend selected cadquery_ocp"
            )
            return manifest
        except CadQueryBackendError as exc:
            manifest = build_geometry_manifest(read_step_topology(step_file), axis)
            reader = manifest.setdefault("reader", {})
            reader.setdefault("backend_notes", []).append(
                f"auto backend fell back to step_ap242_text_fallback after CadQuery failure: {exc}"
            )
            return manifest
    raise ValueError(f"Unsupported STEP backend: {backend}")


def read_cadquery_geometry_manifest(
    step_file: Path,
    axis: str,
    mesh_output: Optional[Path] = None,
) -> dict:
    """Read a STEP file through a CadQuery worker and return a manifest."""
    with tempfile.TemporaryDirectory(prefix="step_feature_cq_") as temp_dir:
        output_path = Path(temp_dir) / "geometry_manifest.json"
        command = [
            sys.executable,
            "-m",
            "step_feature_assistant.cadquery_worker",
            "--step-file",
            str(step_file),
            "--axis",
            axis,
            "--output",
            str(output_path),
        ]
        if mesh_output is not None:
            command.extend(["--mesh-output", str(mesh_output)])
        result = subprocess.run(
            command,
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            message = _format_worker_error(result.returncode, result.stdout, result.stderr)
            raise CadQueryBackendError(message)
        if not output_path.exists():
            message = _format_worker_error(result.returncode, result.stdout, result.stderr)
            raise CadQueryBackendError(f"CadQuery worker did not write output. {message}")
        return json.loads(output_path.read_text(encoding="utf-8"))


def _format_worker_error(returncode: int, stdout: Optional[str], stderr: Optional[str]) -> str:
    parts = [f"returncode={returncode}"]
    if stdout:
        parts.append(f"stdout={stdout.strip()}")
    if stderr:
        parts.append(f"stderr={stderr.strip()}")
    return "; ".join(parts)
