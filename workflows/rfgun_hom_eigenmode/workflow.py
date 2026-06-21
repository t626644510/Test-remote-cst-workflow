"""Workflow 4 campaign orchestration."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cst_optimization.core.cleanup import remove_lock_file, remove_result_folder
from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.solver import SolverRunner

from .adapter import (
    EigenmodeResultAdapter,
    read_native_results,
    write_native_results,
)
from .config import Workflow4Config
from .fields import (
    archive_changed_files,
    changed_files,
    read_complex_line_npz,
    read_complex_ez_line,
    resolve_field_file,
    sha256_file,
    snapshot_directory,
    write_artifact_index,
)
from .models import (
    EigenmodeCandidate,
    NativeModeResult,
    SolverWindow,
    TargetCluster,
)
from .output import (
    write_eigenmode_results,
    write_json,
    write_match_outputs,
    write_solver_windows,
    write_target_clusters,
)
from .physics import (
    REQUIRED_FIELD_POINTS,
    apply_transverse_metrics,
    calculate_transverse_metrics,
    deduplicate_modes,
)
from .planning import (
    build_solver_windows,
    cluster_targets,
    load_target_records,
    saturation_followups,
)
from .state import CampaignState

_logger = logging.getLogger(__name__)


def _git_commit(project_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            text=True,
            timeout=10,
        ).strip()
    except Exception:
        return ""


def _safe_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) != sha256_file(destination):
            raise FileExistsError(
                f"existing file differs from requested immutable copy: {destination}"
            )
        return
    shutil.copy2(source, destination)


class Workflow4Campaign:
    """Execute and post-process one HOM eigenmode target campaign."""

    def __init__(
        self,
        config: Workflow4Config,
        campaign_dir: str | Path,
        *,
        resume: bool = False,
    ) -> None:
        self.config = config
        self.campaign_dir = Path(campaign_dir).resolve()
        self.resume = resume
        self.project_root = Path(__file__).resolve().parents[2]
        self.working_project = (
            self.campaign_dir / "model" / f"{config.template_path.stem}_working.cst"
        )
        self.state = CampaignState(self.campaign_dir / "campaign_state.json")
        self.records = load_target_records(config.input_csv)
        self.clusters = cluster_targets(self.records)
        self.clusters_by_id = {
            cluster.target_cluster_id: cluster for cluster in self.clusters
        }
        self.windows = build_solver_windows(
            self.clusters,
            search_half_width_mhz=config.search_half_width_mhz,
            guard_mhz=config.guard_mhz,
            max_clusters_per_window=config.max_clusters_per_window,
            split_overlap_mhz=config.split_overlap_mhz,
        )
        self._connection: CSTConnection | None = None

    @property
    def hashes(self) -> dict[str, str]:
        return {
            "input_hash": sha256_file(self.config.input_csv),
            "template_hash": sha256_file(self.config.template_path),
            "config_hash": sha256_file(self.config.source_config_path),
        }

    def initialize(
        self,
        *,
        require_template: bool = True,
        allow_config_change: bool = False,
    ) -> None:
        if not self.config.input_csv.is_file():
            raise FileNotFoundError(f"input CSV not found: {self.config.input_csv}")
        if require_template and not self.config.template_path.is_file():
            raise FileNotFoundError(
                f"CST template not found: {self.config.template_path}"
            )
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        hashes = self.hashes
        loaded = self.state.load()
        if self.resume:
            if not loaded:
                raise FileNotFoundError(
                    f"resume requested but campaign state is missing: {self.state.path}"
                )
            if not self.state.hashes_match(**hashes):
                input_template_match = (
                    self.state.data.get("input_hash") == hashes["input_hash"]
                    and self.state.data.get("template_hash")
                    == hashes["template_hash"]
                )
                if allow_config_change and input_template_match:
                    self.state.data["config_hash"] = hashes["config_hash"]
                    self.state.save()
                else:
                    raise RuntimeError(
                        "resume refused: input, template, or config hash changed"
                    )
        else:
            if loaded:
                raise FileExistsError(
                    f"campaign already initialized: {self.campaign_dir}"
                )
            self.state.initialize(**hashes)

        if require_template and not self.working_project.exists():
            _safe_copy(self.config.template_path, self.working_project)
        self._restore_dynamic_windows()
        self.write_plan_outputs()
        self._write_manifest()
        for window in self.windows:
            if not self.state.get_window(window.solver_window_id):
                self.state.set_window(
                    window.solver_window_id,
                    "pending",
                    window=window.to_dict(),
                )

    def _restore_dynamic_windows(self) -> None:
        known = {window.solver_window_id for window in self.windows}
        for window_id, record in self.state.data.get("windows", {}).items():
            data = record.get("window")
            if data and window_id not in known:
                self.windows.append(SolverWindow(**data))
                known.add(window_id)
        self.windows.sort(key=lambda item: (item.search_min_hz, item.solver_window_id))

    def write_plan_outputs(self) -> None:
        write_target_clusters(
            self.campaign_dir / "hom_target_clusters.csv", self.clusters
        )
        write_solver_windows(
            self.campaign_dir / "hom_solver_windows.csv", self.windows
        )

    def _write_manifest(self) -> None:
        hashes = self.hashes
        payload = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workflow": "workflow_4_hom_eigenmode",
            "input_csv": str(self.config.input_csv.resolve()),
            "template_path": str(self.config.template_path.resolve()),
            "working_project": str(self.working_project.resolve()),
            "config_path": str(self.config.source_config_path.resolve()),
            **hashes,
            "git_commit": _git_commit(self.project_root),
            "parameter": {
                "name": self.config.parameter_name,
                "unit": "MHz",
                "search_half_width_mhz": self.config.search_half_width_mhz,
            },
            "solver": {
                "max_modes": self.config.max_modes,
                "timeout_s": self.config.solver_timeout_s,
                "settle_s": self.config.solver_settle_s,
            },
            "physics": {
                "beta": self.config.beta,
                "offset_mm": self.config.offset_mm,
                "longitudinal_voltage": "integral Ez*exp(+j*omega*z/(beta*c)) dz",
                "longitudinal_r_over_q": "|V_parallel|^2/(omega*U)",
                "dipole_coefficient": "|grad_transverse(V_parallel)|^2/(omega*U)",
                "dipole_coefficient_unit": "ohm/m^2",
                "transverse_conversions": ["ohm/m^2", "ohm/m", "ohm"],
                "kick_factor": "c*A/4",
                "native_crosscheck_relative_tolerance": (
                    self.config.validation_tolerance
                ),
            },
            "boundary_description": self.config.boundary_description,
            "result_contract": {
                "paths": self.config.result_contract.paths,
                "units": self.config.result_contract.units,
                "regional_q_paths": self.config.result_contract.regional_q_paths,
                "q0_components": list(
                    self.config.result_contract.q0_components
                ),
                "required": list(self.config.result_contract.required),
            },
            "field_contract": {
                "export_dir": str(
                    self.config.field_contract.export_dir.resolve()
                ),
                "patterns": self.config.field_contract.patterns,
                "line_result_paths": (
                    self.config.field_contract.line_result_paths
                ),
                "field_dataset": self.config.field_contract.field_dataset,
                "z_dataset": self.config.field_contract.z_dataset,
                "field_component": self.config.field_contract.field_component,
            },
            "measurement_q_policy": (
                "kept per source row; never averaged into simulated R/Q"
            ),
            "fallback_policy": "no automatic driven-mode or wakefield fallback",
        }
        write_json(self.campaign_dir / "hom_solver_manifest.json", payload)

    def audit_results(self, project_path: Path | None = None) -> dict[str, Any]:
        from cst_optimization.core import init_cst_path

        init_cst_path(str(self.config.cst_library_path))
        adapter = EigenmodeResultAdapter(
            project_path or self.config.template_path,
            self.config.result_contract,
            max_modes=self.config.max_modes,
            allow_interactive=True,
        )
        audit = adapter.audit(self.config.field_contract)
        write_json(self.campaign_dir / "result_contract_audit.json", audit)
        return audit

    def _ensure_connection(self) -> CSTConnection:
        if self._connection is None or not self._connection.is_connected:
            self._connection = CSTConnection(
                library_path=str(self.config.cst_library_path),
                mode=self.config.connect_mode,
            )
            self._connection.connect()
            self._connection.set_quiet_mode(True)
            self._record_cst_version()
        return self._connection

    def _record_cst_version(self) -> None:
        manifest_path = self.campaign_dir / "hom_solver_manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["cst_version"] = CSTConnection.version()
            write_json(manifest_path, payload)
        except Exception:
            _logger.warning("Could not record CST version", exc_info=True)

    def _reset_connection(self) -> None:
        if self._connection is not None:
            self._connection.close(force=True)
            self._connection = None
        time.sleep(self.config.retry_cooldown_s)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close(force=False)
            self._connection = None

    def _runtime_export_dir(self) -> Path:
        """Return the working-copy export directory when CST creates one."""

        working_export = (
            self.working_project.with_suffix("") / "Export" / "3d"
        )
        if working_export.exists():
            return working_export
        return self.config.field_contract.export_dir

    def _next_attempt_number(self, window: SolverWindow) -> int:
        root = self.campaign_dir / "windows" / window.solver_window_id
        existing = [
            int(path.name.split("_")[-1])
            for path in root.glob("attempt_*")
            if path.is_dir() and path.name.split("_")[-1].isdigit()
        ]
        return max(existing, default=0) + 1

    def run(self, *, window_id: str = "") -> list[EigenmodeCandidate]:
        selected_ids = {window_id} if window_id else None
        queue = [
            window
            for window in self.windows
            if selected_ids is None or window.solver_window_id in selected_ids
        ]
        if selected_ids and not queue:
            raise KeyError(f"unknown solver window: {window_id}")

        queued_ids = {window.solver_window_id for window in queue}
        index = 0
        try:
            while index < len(queue):
                window = queue[index]
                index += 1
                state_record = self.state.get_window(window.solver_window_id)
                if self.resume and state_record.get("status") in {
                    "postprocessed",
                    "template_contract_incomplete",
                    "mode_enumeration_incomplete",
                }:
                    if self._window_artifacts_complete(window):
                        continue
                outcome = self._run_window_with_retries(window)
                if outcome.get("failed"):
                    continue
                if outcome["mode_count"] == self.config.max_modes:
                    if selected_ids is not None:
                        current = self.state.get_window(
                            window.solver_window_id
                        )
                        self.state.set_window(
                            window.solver_window_id,
                            current.get("status", "postprocessed"),
                            window=window.to_dict(),
                            mode_count_saturated=True,
                            followup_deferred=True,
                            attempt_dir=outcome["attempt_dir"],
                        )
                        continue
                    followups, terminal_status = saturation_followups(
                        window,
                        self.clusters_by_id,
                        search_half_width_mhz=self.config.search_half_width_mhz,
                    )
                    if terminal_status:
                        self.state.set_window(
                            window.solver_window_id,
                            terminal_status,
                            window=window.to_dict(),
                            mode_count_saturated=True,
                            attempt_dir=outcome["attempt_dir"],
                        )
                    for followup in followups:
                        if followup.solver_window_id in queued_ids:
                            continue
                        queued_ids.add(followup.solver_window_id)
                        queue.append(followup)
                        self.windows.append(followup)
                        self.state.set_window(
                            followup.solver_window_id,
                            "pending",
                            window=followup.to_dict(),
                        )
                    if followups:
                        write_solver_windows(
                            self.campaign_dir / "hom_solver_windows.csv",
                            self.windows,
                        )
            return self.aggregate_outputs()
        finally:
            self.close()
            self._verify_inputs_unchanged()

    def _window_artifacts_complete(self, window: SolverWindow) -> bool:
        record = self.state.get_window(window.solver_window_id)
        attempt_dir = record.get("attempt_dir", "")
        if not attempt_dir:
            return False
        path = Path(attempt_dir)
        return (
            (path / "native_results.json").is_file()
            and (path / "mode_candidates.json").is_file()
            and (path / "artifact_index.json").is_file()
        )

    def _run_window_with_retries(self, window: SolverWindow) -> dict[str, Any]:
        last_error = ""
        for _ in range(self.config.retry_attempts):
            attempt_number = self._next_attempt_number(window)
            try:
                return self._run_window(window, attempt_number)
            except Exception as exc:
                last_error = str(exc)
                _logger.exception(
                    "Workflow 4 window %s attempt %d failed",
                    window.solver_window_id,
                    attempt_number,
                )
                self.state.set_window(
                    window.solver_window_id,
                    "failed",
                    window=window.to_dict(),
                    error=last_error,
                )
                self._reset_connection()
                remove_result_folder(str(self.working_project))
                remove_lock_file(str(self.working_project.parent))
        _logger.error(
            "Window %s exhausted retries and will remain explicitly failed: %s",
            window.solver_window_id,
            last_error,
        )
        return {
            "failed": True,
            "mode_count": 0,
            "attempt_dir": "",
            "candidates": [],
        }

    def _run_window(
        self,
        window: SolverWindow,
        attempt_number: int,
    ) -> dict[str, Any]:
        attempt_id = f"attempt_{attempt_number:03d}"
        attempt_dir = (
            self.campaign_dir
            / "windows"
            / window.solver_window_id
            / attempt_id
        )
        if attempt_dir.exists():
            raise FileExistsError(f"attempt directory already exists: {attempt_dir}")
        raw_dir = attempt_dir / "raw"
        raw_dir.mkdir(parents=True)
        write_json(
            attempt_dir / "attempt_metadata.json",
            {
                "window": window.to_dict(),
                "attempt_id": attempt_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.state.set_window(
            window.solver_window_id,
            "running",
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=str(attempt_dir.resolve()),
        )

        working_export_dir = (
            self.working_project.with_suffix("") / "Export" / "3d"
        )
        before_by_root = {
            working_export_dir: snapshot_directory(working_export_dir),
            self.config.field_contract.export_dir: snapshot_directory(
                self.config.field_contract.export_dir
            ),
        }
        connection = self._ensure_connection()
        solver = SolverRunner(
            timeout_s=self.config.solver_timeout_s,
            settle_s=self.config.solver_settle_s,
        )
        with connection.open_project(str(self.working_project)) as project:
            updated = project.update_parameters(
                {self.config.parameter_name: window.f_hom_mhz},
                use_full_rebuild=True,
            )
            if not updated:
                raise RuntimeError(
                    f"failed to update parameter {self.config.parameter_name}"
                )
            solver_result = solver.run(project)
            messages = project.get_messages()
            (attempt_dir / "cst_messages.txt").write_text(
                str(messages), encoding="utf-8", errors="replace"
            )
            if not solver_result.success:
                raise RuntimeError(
                    f"CST solver failed ({solver_result.error_type}): "
                    f"{solver_result.error_message}"
                )
            if not project.save():
                raise RuntimeError("failed to save working CST project")

        self.state.set_window(
            window.solver_window_id,
            "solved",
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=str(attempt_dir.resolve()),
            solver_elapsed_s=solver_result.elapsed_s,
            mesh_cells=solver_result.mesh_cells,
        )

        adapter = EigenmodeResultAdapter(
            self.working_project,
            self.config.result_contract,
            max_modes=self.config.max_modes,
            allow_interactive=False,
        )
        native_modes = adapter.read_native_modes()
        write_native_results(
            attempt_dir / "native_results.json", native_modes, adapter.errors
        )
        audit = adapter.audit(self.config.field_contract)
        write_json(attempt_dir / "result_contract_audit.json", audit)
        write_json(self.campaign_dir / "result_contract_audit.json", audit)
        line_archive_status = adapter.archive_complex_lines(
            native_modes,
            self.config.field_contract,
            raw_dir / "lines",
        )
        write_json(
            attempt_dir / "line_field_archive_status.json",
            line_archive_status,
        )

        runtime_export_dir = self._runtime_export_dir()
        before = before_by_root.get(runtime_export_dir, {})
        after = snapshot_directory(runtime_export_dir)
        changed = changed_files(before, after)
        archived = archive_changed_files(
            runtime_export_dir,
            raw_dir / "3d",
            changed,
        )
        write_artifact_index(
            attempt_dir / "artifact_index.json",
            source_root=runtime_export_dir,
            before=before,
            after=after,
            archived=archived,
        )
        self.state.set_window(
            window.solver_window_id,
            "extracted",
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=str(attempt_dir.resolve()),
            native_mode_count=len(native_modes),
            archived_file_count=len(archived),
        )

        candidates = self._process_attempt(
            window, attempt_id, attempt_dir, native_modes
        )
        required_missing = [
            *audit.get("required_missing", []),
            *audit.get("missing_field_patterns", []),
            *[
                candidate.data_availability_reason
                for candidate in candidates
                if candidate.data_availability_reason.startswith(
                    ("field_contract_error:", "field_processing_error:")
                )
            ],
        ]
        status = (
            "template_contract_incomplete"
            if required_missing
            else "postprocessed"
        )
        self.state.set_window(
            window.solver_window_id,
            status,
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=str(attempt_dir.resolve()),
            native_mode_count=len(native_modes),
            mode_count_saturated=len(native_modes) == self.config.max_modes,
            required_missing=required_missing,
        )
        return {
            "mode_count": len(native_modes),
            "attempt_dir": str(attempt_dir.resolve()),
            "candidates": candidates,
        }

    def _process_attempt(
        self,
        window: SolverWindow,
        attempt_id: str,
        attempt_dir: Path,
        native_modes: Iterable[NativeModeResult],
    ) -> list[EigenmodeCandidate]:
        raw_dir = attempt_dir / "raw"
        candidates: list[EigenmodeCandidate] = []
        for native in native_modes:
            mode_id = (
                f"MODE_{window.solver_window_id}_{attempt_id.upper()}"
                f"_M{native.mode_number}"
            )
            candidate = EigenmodeCandidate(
                mode_id=mode_id,
                solver_window_id=window.solver_window_id,
                attempt_id=attempt_id,
                mode_number=native.mode_number,
                frequency_hz=native.frequency_hz,
                r_over_q_ohm=native.r_over_q_ohm,
                voltage_v=native.voltage_v,
                total_energy_j=native.total_energy_j,
                total_loss_w=native.total_loss_w,
                residual=native.residual,
                q_loaded=native.q_loaded,
                q0=native.q0,
                regional_q=native.regional_q,
            )
            fields = {}
            field_contract_errors = []
            field_dest = self.campaign_dir / "fields" / mode_id
            for point in REQUIRED_FIELD_POINTS:
                line_source = (
                    raw_dir
                    / "lines"
                    / f"mode_{native.mode_number}_{point}.npz"
                )
                try:
                    if line_source.is_file():
                        destination = field_dest / f"{point}.npz"
                        _safe_copy(line_source, destination)
                        candidate.field_paths[point] = str(
                            destination.resolve()
                        )
                        fields[point] = read_complex_line_npz(destination)
                        continue
                    pattern = self.config.field_contract.patterns.get(point, "")
                    if not pattern:
                        raise FileNotFoundError(
                            "no archived 1D curve or HDF5 fallback pattern"
                        )
                    source = resolve_field_file(
                        raw_dir,
                        pattern,
                        mode=native.mode_number,
                        point=point,
                    )
                    if source is None:
                        raise FileNotFoundError("HDF5 fallback not found")
                    destination = field_dest / f"{point}{source.suffix}"
                    _safe_copy(source, destination)
                    candidate.field_paths[point] = str(destination.resolve())
                    fields[point] = read_complex_ez_line(
                        destination,
                        field_dataset=self.config.field_contract.field_dataset,
                        z_dataset=self.config.field_contract.z_dataset,
                        field_component=self.config.field_contract.field_component,
                    )
                except Exception as exc:
                    field_contract_errors.append(f"{point}:{exc}")

            if field_contract_errors:
                candidate.data_availability_reason = (
                    "field_contract_error:" + "|".join(field_contract_errors)
                )
            elif native.total_energy_j is None:
                candidate.data_availability_reason = "missing_total_energy"
            else:
                try:
                    metrics = calculate_transverse_metrics(
                        fields,
                        frequency_hz=native.frequency_hz,
                        stored_energy_j=native.total_energy_j,
                        offset_mm=self.config.offset_mm,
                        beta=self.config.beta,
                    )
                    apply_transverse_metrics(
                        candidate,
                        metrics,
                        validation_tolerance=self.config.validation_tolerance,
                    )
                except Exception as exc:
                    candidate.data_availability_reason = (
                        f"field_processing_error:{exc}"
                    )
            candidates.append(candidate)

        write_json(
            attempt_dir / "mode_candidates.json",
            [candidate.to_dict() for candidate in candidates],
        )
        return candidates

    def offline_reprocess(self) -> list[EigenmodeCandidate]:
        """Re-read archived HDF5 fields and regenerate all derived outputs."""

        for metadata_path in sorted(
            (self.campaign_dir / "windows").glob(
                "*/attempt_*/attempt_metadata.json"
            )
        ):
            attempt_dir = metadata_path.parent
            native_path = attempt_dir / "native_results.json"
            if not native_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            window = SolverWindow(**metadata["window"])
            native_modes, _ = read_native_results(native_path)
            self._process_attempt(
                window,
                str(metadata["attempt_id"]),
                attempt_dir,
                native_modes,
            )
        return self.aggregate_outputs()

    def _load_all_candidates(self) -> list[EigenmodeCandidate]:
        candidates = []
        for path in sorted(
            (self.campaign_dir / "windows").glob(
                "*/attempt_*/mode_candidates.json"
            )
        ):
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidates.extend(EigenmodeCandidate.from_dict(item) for item in payload)
        return candidates

    def aggregate_outputs(self) -> list[EigenmodeCandidate]:
        candidates = self._load_all_candidates()
        center_fields = {}
        for candidate in candidates:
            center_path = candidate.field_paths.get("center", "")
            if center_path and Path(center_path).is_file():
                if Path(center_path).suffix.lower() == ".npz":
                    center_fields[candidate.mode_id] = read_complex_line_npz(
                        center_path
                    )
                else:
                    center_fields[candidate.mode_id] = read_complex_ez_line(
                        center_path,
                        field_dataset=self.config.field_contract.field_dataset,
                        z_dataset=self.config.field_contract.z_dataset,
                        field_component=self.config.field_contract.field_component,
                    )
        deduplicated = deduplicate_modes(
            candidates,
            center_fields,
            frequency_tolerance_hz=self.config.dedup_frequency_tolerance_hz,
            field_correlation_threshold=self.config.dedup_field_correlation,
            r_over_q_relative_tolerance=self.config.dedup_r_over_q_tolerance,
        )
        write_eigenmode_results(
            self.campaign_dir / "hom_eigenmode_results.csv",
            deduplicated,
        )
        write_match_outputs(
            self.campaign_dir,
            clusters=self.clusters,
            candidates=deduplicated,
            match_half_width_mhz=self.config.match_half_width_mhz,
            cluster_failure_reasons=self._cluster_failure_reasons(),
        )
        return deduplicated

    def _cluster_failure_reasons(self) -> dict[str, str]:
        reasons: dict[str, str] = {}
        for cluster in self.clusters:
            statuses = []
            for record in self.state.data.get("windows", {}).values():
                window_data = record.get("window", {})
                if cluster.target_cluster_id in window_data.get("cluster_ids", []):
                    statuses.append(record.get("status", ""))
            if "mode_enumeration_incomplete" in statuses:
                reasons[cluster.target_cluster_id] = "mode_enumeration_incomplete"
            elif not statuses or all(status == "pending" for status in statuses):
                reasons[cluster.target_cluster_id] = "not_simulated"
            elif statuses and all(
                status == "template_contract_incomplete" for status in statuses
            ):
                reasons[cluster.target_cluster_id] = "template_contract_incomplete"
            elif statuses and all(status == "failed" for status in statuses):
                reasons[cluster.target_cluster_id] = "solver_failed"
            elif cluster.propagation_background:
                reasons[cluster.target_cluster_id] = (
                    "propagating_no_discrete_mode"
                )
        return reasons

    def _verify_inputs_unchanged(self) -> None:
        expected = self.state.data
        if sha256_file(self.config.input_csv) != expected.get("input_hash"):
            raise RuntimeError("input CSV changed during Workflow 4 execution")
        if sha256_file(self.config.template_path) != expected.get("template_hash"):
            raise RuntimeError("CST template changed during Workflow 4 execution")
