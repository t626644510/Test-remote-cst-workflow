"""CadQuery/OCP worker wrapper for parametric geometry generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


class CadQueryGeometryError(RuntimeError):
    """Raised when the isolated CadQuery worker fails."""


class CadQueryGeometryBackend:
    """Run CadQuery/OCP operations in a short-lived worker process."""

    def __init__(self, python_executable: str | None = None) -> None:
        self.python_executable = python_executable or sys.executable

    def recover(
        self,
        *,
        step_file: Path,
        output_step: Path,
        axis: str,
        body_index: int,
        profile_points: list[tuple[float, float]],
        profile_segments: list[dict] | None = None,
        deflection_mm: float,
    ) -> dict:
        """Rebuild a profile while retaining metrics from a seed STEP."""
        return self._run_worker(
            step_file=step_file,
            output_step=output_step,
            axis=axis,
            body_index=body_index,
            profile_points=profile_points,
            profile_segments=profile_segments,
            deflection_mm=deflection_mm,
        )

    def generate(
        self,
        *,
        output_step: Path,
        axis: str,
        profile_points: list[tuple[float, float]],
        profile_segments: list[dict] | None = None,
        deflection_mm: float,
    ) -> dict:
        """Generate a profile without importing a seed STEP."""
        return self._run_worker(
            step_file=None,
            output_step=output_step,
            axis=axis,
            body_index=0,
            profile_points=profile_points,
            profile_segments=profile_segments,
            deflection_mm=deflection_mm,
        )

    def _run_worker(
        self,
        *,
        step_file: Path | None,
        output_step: Path,
        axis: str,
        body_index: int,
        profile_points: list[tuple[float, float]],
        profile_segments: list[dict] | None,
        deflection_mm: float,
    ) -> dict:
        with tempfile.TemporaryDirectory(prefix="rf_cem_cq_") as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            report_path = Path(temp_dir) / "kernel_report.json"
            request_path.write_text(
                json.dumps(
                    {
                        "step_file": str(step_file) if step_file is not None else None,
                        "output_step": str(output_step),
                        "axis": axis,
                        "body_index": body_index,
                        "profile_points": profile_points,
                        "profile_segments": profile_segments or [],
                        "deflection_mm": deflection_mm,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            command = [
                self.python_executable,
                "-m",
                "rf_cem.parametric_geometry.core.cadquery_worker",
                "--request",
                str(request_path),
                "--output",
                str(report_path),
            ]
            env = dict(os.environ)
            src_path = str(Path.cwd() / "src")
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
            result = subprocess.run(
                command,
                cwd=str(Path.cwd()),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0 or not report_path.exists():
                parts = [f"returncode={result.returncode}"]
                if result.stdout:
                    parts.append(f"stdout={result.stdout.strip()}")
                if result.stderr:
                    parts.append(f"stderr={result.stderr.strip()}")
                raise CadQueryGeometryError("; ".join(parts))
            return json.loads(report_path.read_text(encoding="utf-8"))
