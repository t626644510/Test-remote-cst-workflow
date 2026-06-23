"""Workflow 4 campaign orchestration and recoverable CST attempt lifecycle."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.cleanup import verify_process_cleanup
from cst_optimization.core.solver import SolverRunner

from .adapter import (
    EigenmodeResultAdapter,
    read_native_results,
    write_native_results,
)
from .config import Workflow4Config
from .diagnostics import (
    AttemptDiagnostics,
    archived_hdf5_mode_pairs,
    classify_solver_failure,
    read_attempt_diagnostics,
    write_messages,
)
from .fields import (
    archive_changed_files,
    changed_files,
    read_complex_ez_line,
    read_complex_line_npz,
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
    build_mode_target_mapping,
    write_eigenmode_results,
    write_json,
    write_match_outputs,
    write_solver_windows,
    write_target_clusters,
    write_valid_seed,
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
from .state import CampaignState, utc_now

_logger = logging.getLogger(__name__)

_COMPLETED_STATUSES = {
    "postprocessed",
    "mode_enumeration_incomplete",
}
_AVOID_STATUSES = {
    "avoid_retry",
    "avoid_retry_legacy",
    "cleanup_incomplete",
}
_RUNNABLE_STATUSES = {
    "pending",
    "retry_pending",
    "interrupted",
    "extract_retry_pending",
    "result_contract_incomplete",
}


class AttemptFailure(RuntimeError):
    """Classified Workflow 4 attempt failure with persisted recovery facts."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        elapsed_s: float = 0.0,
        diagnostics: AttemptDiagnostics | None = None,
        attempt_dir: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.elapsed_s = float(elapsed_s)
        self.diagnostics = diagnostics
        self.attempt_dir = attempt_dir


class CleanupIncompleteError(RuntimeError):
    """Raised when a Workflow 4-owned CST PID cannot be verified as stopped."""


def _template_revision_id(template_hash: str) -> str:
    return f"TR_{template_hash[:12]}"


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


def _reported_frequency_matches(
    mode_number: int,
    frequency_hz: float,
    diagnostics: AttemptDiagnostics,
    *,
    tolerance_hz: float = 10_000.0,
) -> bool:
    """Require native and final-table frequencies to agree within 10 kHz."""

    reported = dict(diagnostics.final_mode_frequencies_hz).get(mode_number)
    return reported is not None and abs(reported - frequency_hz) <= tolerance_hz


def _elapsed_since(timestamp: str) -> float:
    try:
        started = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return 0.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(
        0.0,
        (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds(),
    )


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
        self._manifest_version_recorded = False
        self._artifact_validation_cache: dict[
            tuple[str, int, int, str], bool
        ] = {}

    @property
    def hashes(self) -> dict[str, str]:
        return {
            "input_hash": sha256_file(self.config.input_csv),
            "template_hash": sha256_file(self.config.template_path),
            "config_hash": sha256_file(self.config.source_config_path),
        }

    def _ensure_template_revision_state(self) -> None:
        revisions = list(self.state.data.get("template_revisions", []))
        if not revisions:
            initial_hash = str(self.state.data.get("template_hash", ""))
            if initial_hash:
                revisions.append(
                    {
                        "revision_id": _template_revision_id(initial_hash),
                        "template_hash": initial_hash,
                        "adopted_at": str(
                            self.state.data.get("updated_at", "")
                        ),
                        "change_note": "initial campaign template",
                    }
                )
        self.state.data["template_revisions"] = revisions
        if revisions and not self.state.data.get(
            "active_template_revision_id"
        ):
            self.state.data["active_template_revision_id"] = revisions[-1][
                "revision_id"
            ]

    @property
    def active_template_revision(self) -> dict[str, Any]:
        self._ensure_template_revision_state()
        active_id = str(
            self.state.data.get("active_template_revision_id", "")
        )
        for revision in self.state.data.get("template_revisions", []):
            if revision.get("revision_id") == active_id:
                return dict(revision)
        return {}

    def _template_revision_for_metadata(
        self, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        revision_id = str(metadata.get("template_revision_id", ""))
        state = getattr(self, "state", None)
        revisions = list(
            state.data.get("template_revisions", []) if state is not None else []
        )
        if revision_id:
            for revision in revisions:
                if revision.get("revision_id") == revision_id:
                    return dict(revision)
        return dict(revisions[0]) if revisions else {}

    def initialize(
        self,
        *,
        require_template: bool = True,
        allow_config_change: bool = False,
        persist: bool = True,
    ) -> None:
        """Load/create campaign state and optionally persist schema migration."""

        if not self.config.input_csv.is_file():
            raise FileNotFoundError(f"input CSV not found: {self.config.input_csv}")
        if require_template and not self.config.template_path.is_file():
            raise FileNotFoundError(
                f"CST template not found: {self.config.template_path}"
            )
        if persist:
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
                else:
                    raise RuntimeError(
                        "resume refused: input, template, or config hash changed"
                    )
            # Migrate before the first current-schema save. CampaignState.save()
            # stamps the current schema version, so saving a config-hash
            # update first would make a legacy campaign look already migrated.
            self._migrate_legacy_state(persist=False)
            self._ensure_template_revision_state()
            self._migrate_stale_running(persist=persist)
            if persist:
                self.state.save()
        else:
            if loaded:
                raise FileExistsError(
                    f"campaign already initialized: {self.campaign_dir}"
                )
            if persist:
                self.state.initialize(**hashes)
                self._ensure_template_revision_state()
                self.state.save()

        self._restore_dynamic_windows()
        if not persist:
            return
        self.write_plan_outputs()
        self._write_manifest()
        for window in self.windows:
            if not self.state.get_window(window.solver_window_id):
                self.state.set_window(
                    window.solver_window_id,
                    "pending",
                    window=window.to_dict(),
                    init_attempt_count=0,
                    long_attempt_count=0,
                    attempt_history=[],
                )

    def initialize_template_migration(self, *, persist: bool = False) -> None:
        """Load a campaign while allowing only an explicit template mismatch."""

        if not self.config.input_csv.is_file():
            raise FileNotFoundError(f"input CSV not found: {self.config.input_csv}")
        if not self.config.template_path.is_file():
            raise FileNotFoundError(
                f"CST template not found: {self.config.template_path}"
            )
        if not self.state.load():
            raise FileNotFoundError(
                f"campaign state is missing: {self.state.path}"
            )
        hashes = self.hashes
        if self.state.data.get("input_hash") != hashes["input_hash"]:
            raise RuntimeError(
                "template migration refused: input CSV hash changed"
            )
        self._migrate_legacy_state(persist=False)
        self._ensure_template_revision_state()
        self._migrate_stale_running(persist=persist)
        self._restore_dynamic_windows()
        if persist:
            self.state.data["config_hash"] = hashes["config_hash"]
            self.state.save()

    def template_migration_preview(
        self,
        *,
        retry_scope: str = "long-related",
    ) -> dict[str, Any]:
        """Preview template adoption and retry-budget resets without writes."""

        if retry_scope != "long-related":
            raise ValueError(f"unsupported retry scope: {retry_scope}")
        hashes = self.hashes
        old_hash = str(self.state.data.get("template_hash", ""))
        changed = old_hash != hashes["template_hash"]
        reset_ids = sorted(
            window_id
            for window_id, record in self.state.data.get(
                "windows", {}
            ).items()
            if record.get("status") in {"avoid_retry", "avoid_retry_legacy"}
            and int(record.get("long_attempt_count", 0)) > 0
        )
        existing_runnable = sorted(
            window_id
            for window_id, record in self.state.data.get(
                "windows", {}
            ).items()
            if record.get("status") in _RUNNABLE_STATUSES
        )
        pure_fast_avoid = sorted(
            window_id
            for window_id, record in self.state.data.get(
                "windows", {}
            ).items()
            if record.get("status") in {"avoid_retry", "avoid_retry_legacy"}
            and int(record.get("long_attempt_count", 0)) == 0
        )
        run_ids = sorted(set(reset_ids + existing_runnable)) if changed else []
        by_id = {window.solver_window_id: window for window in self.windows}
        ideal_hours = sum(
            self._estimate_window_minutes(by_id[window_id]) / 60.0
            for window_id in run_ids
            if window_id in by_id
        )
        return {
            "changed": changed,
            "old_template_hash": old_hash,
            "new_template_hash": hashes["template_hash"],
            "old_revision_id": self.state.data.get(
                "active_template_revision_id", ""
            ),
            "new_revision_id": _template_revision_id(
                hashes["template_hash"]
            ),
            "retry_scope": retry_scope,
            "reset_window_ids": reset_ids if changed else [],
            "existing_runnable_ids": existing_runnable,
            "pure_fast_avoid_ids": pure_fast_avoid,
            "run_count_after_adoption": len(run_ids),
            "skip_completed_count": sum(
                record.get("status") in _COMPLETED_STATUSES
                for record in self.state.data.get("windows", {}).values()
            ),
            "ideal_hours": round(ideal_hours, 1),
            "realistic_hours": (
                round(ideal_hours * 1.35, 1),
                round(ideal_hours * 2.0, 1),
            ),
            "eta_basis": (
                "conservative legacy-template frequency-band estimates; "
                "recalibrate after new-template live smoke"
            ),
        }

    def adopt_template_revision(
        self,
        *,
        retry_scope: str,
        change_note: str,
    ) -> dict[str, Any]:
        """Atomically adopt a new template and reset selected retry budgets."""

        if not change_note.strip():
            raise ValueError("template change note must not be empty")
        preview = self.template_migration_preview(retry_scope=retry_scope)
        if not preview["changed"]:
            raise RuntimeError(
                "template adoption refused: current template hash is unchanged"
            )
        now = utc_now()
        old_revision_id = str(preview["old_revision_id"])
        new_revision_id = str(preview["new_revision_id"])
        revisions = list(self.state.data.get("template_revisions", []))
        if any(
            revision.get("template_hash") == preview["new_template_hash"]
            for revision in revisions
        ):
            raise RuntimeError(
                "template adoption refused: this template hash already exists "
                "in campaign history"
            )
        for window_id in preview["reset_window_ids"]:
            record = dict(self.state.data["windows"][window_id])
            generation_history = list(
                record.get("retry_generation_history", [])
            )
            generation_history.append(
                {
                    "retry_generation": int(
                        record.get("retry_generation", 0)
                    ),
                    "template_revision_id": old_revision_id,
                    "status": record.get("status", ""),
                    "init_attempt_count": int(
                        record.get("init_attempt_count", 0)
                    ),
                    "long_attempt_count": int(
                        record.get("long_attempt_count", 0)
                    ),
                    "error": record.get("error", ""),
                    "failure_class": record.get("failure_class", ""),
                    "terminal_reason": record.get("terminal_reason", ""),
                    "closed_at": now,
                }
            )
            record.pop("error", None)
            record.pop("failure_class", None)
            record.update(
                {
                    "status": "retry_pending",
                    "init_attempt_count": 0,
                    "long_attempt_count": 0,
                    "retry_generation": int(
                        record.get("retry_generation", 0)
                    )
                    + 1,
                    "retry_generation_history": generation_history,
                    "template_revision_id": new_revision_id,
                    "terminal_reason": "template_revision_retry_reset",
                    "updated_at": now,
                }
            )
            self.state.data["windows"][window_id] = record
        revisions.append(
            {
                "revision_id": new_revision_id,
                "template_hash": preview["new_template_hash"],
                "template_path": str(self.config.template_path.resolve()),
                "adopted_at": now,
                "change_note": change_note.strip(),
                "inherits_successful_results": True,
                "retry_scope": retry_scope,
                "reset_window_ids": list(preview["reset_window_ids"]),
            }
        )
        self.state.data.update(
            {
                "template_hash": preview["new_template_hash"],
                "config_hash": self.hashes["config_hash"],
                "template_revisions": revisions,
                "active_template_revision_id": new_revision_id,
            }
        )
        self.state.save()
        self._write_manifest()
        return preview

    def _restore_dynamic_windows(self) -> None:
        known = {window.solver_window_id for window in self.windows}
        for window_id, record in self.state.data.get("windows", {}).items():
            data = record.get("window")
            if data and window_id not in known:
                self.windows.append(SolverWindow(**data))
                known.add(window_id)
        self.windows.sort(key=lambda item: (item.search_min_hz, item.solver_window_id))

    def _migrate_legacy_state(self, *, persist: bool) -> None:
        """Upgrade v1 state without rewriting immutable attempt artifacts."""

        if int(self.state.data.get("schema_version", 1)) >= 2:
            return
        for window_id, old_record in list(
            self.state.data.get("windows", {}).items()
        ):
            record = dict(old_record)
            attempt_root = self.campaign_dir / "windows" / window_id
            history: list[dict[str, Any]] = []
            init_count = 0
            long_count = 0
            for attempt_dir in sorted(attempt_root.glob("attempt_*")):
                diagnostics = read_attempt_diagnostics(attempt_dir)
                success = (attempt_dir / "mode_candidates.json").is_file()
                failure_class = ""
                if not success:
                    failure_class = (
                        "init_fast"
                        if not diagnostics.meshing_successful
                        and not diagnostics.mode_table_present
                        else "long_solve"
                    )
                    if failure_class == "init_fast":
                        init_count += 1
                    else:
                        long_count += 1
                metadata = self._read_attempt_metadata(attempt_dir)
                history.append(
                    {
                        "attempt_id": attempt_dir.name,
                        "started_at": metadata.get("started_at", ""),
                        "ended_at": "",
                        "phase": "postprocess" if success else "solve",
                        "outcome": "success" if success else "failed",
                        "failure_class": failure_class,
                        "meshing_successful": diagnostics.meshing_successful,
                        "solver_successful": diagnostics.solver_successful,
                        "mode_table_present": diagnostics.mode_table_present,
                        "final_mode_numbers": list(
                            diagnostics.final_mode_numbers
                        ),
                        "final_mode_frequencies_hz": {
                            str(mode): frequency
                            for mode, frequency in (
                                diagnostics.final_mode_frequencies_hz
                            )
                        },
                        "propagating_warning_ports": list(
                            diagnostics.propagating_warning_ports
                        ),
                        "legacy_imported": True,
                    }
                )
            old_error = str(record.get("error", ""))
            if old_error:
                failures = list(record.get("failure_history", []))
                failures.append(
                    {
                        "legacy_error": old_error,
                        "attempt_id": record.get("attempt_id", ""),
                    }
                )
                record["failure_history"] = failures
            status = str(record.get("status", "pending"))
            attempt_id = str(record.get("attempt_id", ""))
            if attempt_id:
                local_attempt = attempt_root / attempt_id
                if local_attempt.exists():
                    record["attempt_dir"] = local_attempt.relative_to(
                        self.campaign_dir
                    ).as_posix()
            if status == "failed":
                status = "avoid_retry_legacy"
                record["terminal_reason"] = "legacy_retry_budget_exhausted"
            elif status == "running":
                status = "interrupted"
                # The audited legacy running attempt had substantial solver
                # progress but no final message archive. Conservatively charge
                # one long attempt rather than silently granting a fresh budget.
                long_count = max(1, long_count)
                record["terminal_reason"] = "legacy_stale_running"
            elif status in _COMPLETED_STATUSES:
                record.pop("error", None)
                record.pop("failure_class", None)
            record.update(
                {
                    "status": status,
                    "attempt_history": history,
                    "init_attempt_count": init_count,
                    "long_attempt_count": long_count,
                    "updated_at": utc_now(),
                }
            )
            self.state.data["windows"][window_id] = record
        self.state.data["schema_version"] = 2
        if persist:
            self.state.save()

    def _migrate_stale_running(self, *, persist: bool) -> None:
        """Move dead schema-v2 running attempts to resumable interrupted state."""

        for window_id, old_record in list(
            self.state.data.get("windows", {}).items()
        ):
            if old_record.get("status") != "running":
                continue
            if self._record_has_active_process(window_id, old_record):
                continue
            record = dict(old_record)
            attempt_dir = self._attempt_dir_from_record(window_id, record)
            metadata = (
                self._read_attempt_metadata(attempt_dir)
                if attempt_dir is not None
                else {}
            )
            phase = str(metadata.get("phase", ""))
            elapsed_s = float(metadata.get("wall_elapsed_s", 0.0) or 0.0)
            if elapsed_s <= 0:
                elapsed_s = _elapsed_since(str(metadata.get("started_at", "")))
            long_progress = (
                phase in {"solve", "save", "solved", "export", "postprocess"}
                and elapsed_s >= self.config.long_attempt_threshold_s
            ) or bool(
                metadata.get("meshing_successful")
                or metadata.get("mode_table_present")
                or metadata.get("final_mode_numbers")
            )
            long_count = int(record.get("long_attempt_count", 0))
            if long_progress and not metadata.get("long_budget_charged"):
                long_count += 1
                metadata["long_budget_charged"] = True
                if persist and attempt_dir is not None:
                    write_json(attempt_dir / "attempt_metadata.json", metadata)
            record.update(
                {
                    "status": "interrupted",
                    "failure_class": "external_interrupt",
                    "error": "stale running attempt had no active CST process",
                    "long_attempt_count": long_count,
                    "terminal_reason": "stale_running_no_active_process",
                    "updated_at": utc_now(),
                }
            )
            self.state.data["windows"][window_id] = record

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
            "schema_version": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workflow": "workflow_4_hom_eigenmode",
            "input_csv": str(self.config.input_csv.resolve()),
            "template_path": str(self.config.template_path.resolve()),
            "attempt_project_pattern": (
                "windows/<window_id>/attempt_<n>/model/"
                f"{self.config.template_path.stem}_working.cst"
            ),
            "config_path": str(self.config.source_config_path.resolve()),
            **hashes,
            "active_template_revision_id": self.state.data.get(
                "active_template_revision_id", ""
            ),
            "template_revisions": self.state.data.get(
                "template_revisions", []
            ),
            "git_commit": _git_commit(self.project_root),
            "parameter": {
                "name": self.config.parameter_name,
                "unit": "MHz",
                "search_half_width_mhz": self.config.search_half_width_mhz,
            },
            "solver": {
                "max_modes": self.config.max_modes,
                "mode_count_semantics": "censored_at_max_modes",
                "timeout_s": self.config.solver_timeout_s,
                "settle_s": self.config.solver_settle_s,
                "fast_retry_attempts": self.config.fast_retry_attempts,
                "long_retry_attempts": self.config.long_retry_attempts,
                "fast_retry_backoff_s": list(
                    self.config.fast_retry_backoff_s
                ),
            },
            "physics": {
                "beta": self.config.beta,
                "offset_mm": self.config.offset_mm,
                "longitudinal_voltage": (
                    "integral Ez*exp(+j*omega*z/(beta*c)) dz"
                ),
                "longitudinal_r_over_q": "|V_parallel|^2/(omega*U)",
                "dipole_coefficient": (
                    "|grad_transverse(V_parallel)|^2/(omega*U)"
                ),
                "dipole_coefficient_unit": "ohm/m^2",
                "transverse_conversions": ["ohm/m^2", "ohm/m", "ohm"],
                "kick_factor": "c*A/4",
                "native_crosscheck_relative_tolerance": (
                    self.config.validation_tolerance
                ),
            },
            "boundary_description": self.config.boundary_description,
            "propagating_port_warning_policy": (
                "record_only; boundary_sensitive does not change derived_valid"
            ),
            "propagating_port_warning_implication": (
                "omitted channels may under-estimate leakage and raise Q; "
                "reflections may also change frequency, field shape, and "
                "polarization, so the bias is not always one-directional"
            ),
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
                "mode_field_patterns": (
                    self.config.field_contract.mode_field_patterns
                ),
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

    def _new_connection(self) -> CSTConnection:
        connection = CSTConnection(
            library_path=str(self.config.cst_library_path),
            mode=self.config.connect_mode,
        )
        connection.connect()
        connection.set_quiet_mode(True)
        if not self._manifest_version_recorded:
            self._record_cst_version()
            self._manifest_version_recorded = True
        return connection

    def _record_cst_version(self) -> None:
        manifest_path = self.campaign_dir / "hom_solver_manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["cst_version"] = CSTConnection.version()
            write_json(manifest_path, payload)
        except Exception:
            _logger.warning("Could not record CST version", exc_info=True)

    def _close_attempt_connection(
        self,
        connection: CSTConnection,
        *,
        window_id: str,
        attempt_dir: Path,
        phase: str,
        recorded_pid: int | None,
    ) -> None:
        """Close one Workflow 4-owned CST process without a global sweep."""

        result = connection.close_targeted(pid_override=recorded_pid)
        metadata = self._read_attempt_metadata(attempt_dir)
        cleanup_events = list(metadata.get("cleanup_events", []))
        cleanup_events.append(
            {
                **result,
                "phase": phase,
                "recorded_at": utc_now(),
            }
        )
        self._write_attempt_metadata(
            window_id,
            attempt_dir,
            cleanup_events=cleanup_events,
            last_cleanup=result,
        )
        if not result["success"]:
            self.state.set_window(
                window_id,
                "cleanup_incomplete",
                error=(
                    f"targeted CST cleanup failed during {phase}: "
                    f"{result.get('reason', '')}"
                ),
                failure_class="cleanup_incomplete",
                terminal_reason="owned_cst_pid_not_verified_stopped",
            )
            raise CleanupIncompleteError(
                f"Workflow 4 CST cleanup incomplete during {phase}: {result}"
            )

    def _next_attempt_number(self, window: SolverWindow) -> int:
        root = self.campaign_dir / "windows" / window.solver_window_id
        existing = [
            int(path.name.split("_")[-1])
            for path in root.glob("attempt_*")
            if path.is_dir() and path.name.split("_")[-1].isdigit()
        ]
        return max(existing, default=0) + 1

    def _attempt_dir_from_record(
        self,
        window_id: str,
        record: dict[str, Any],
    ) -> Path | None:
        attempt_id = str(record.get("attempt_id", ""))
        if attempt_id:
            local = self.campaign_dir / "windows" / window_id / attempt_id
            if local.exists():
                return local
        value = str(record.get("attempt_dir", ""))
        if not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else self.campaign_dir / path

    def _record_has_active_process(
        self,
        window_id: str,
        record: dict[str, Any],
    ) -> bool:
        attempt_dir = self._attempt_dir_from_record(window_id, record)
        metadata = (
            self._read_attempt_metadata(attempt_dir)
            if attempt_dir is not None
            else {}
        )
        pid = int(
            metadata.get("solve_pid")
            or metadata.get("prepare_pid")
            or 0
        )
        if pid <= 0:
            return False
        return not verify_process_cleanup(pid, timeout_s=0.6)

    def _attempt_project(self, attempt_dir: Path) -> Path:
        return (
            attempt_dir
            / "model"
            / f"{self.config.template_path.stem}_working.cst"
        )

    def _read_attempt_metadata(self, attempt_dir: Path) -> dict[str, Any]:
        path = attempt_dir / "attempt_metadata.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_attempt_metadata(
        self,
        window_id: str,
        attempt_dir: Path,
        **updates: Any,
    ) -> dict[str, Any]:
        metadata = self._read_attempt_metadata(attempt_dir)
        metadata.update(updates)
        write_json(attempt_dir / "attempt_metadata.json", metadata)
        self.state.record_attempt(window_id, metadata)
        return metadata

    def _window_artifacts_complete(self, window: SolverWindow) -> bool:
        record = self.state.get_window(window.solver_window_id)
        attempt_dir = self._attempt_dir_from_record(
            window.solver_window_id, record
        )
        if attempt_dir is None:
            return False
        return (
            (attempt_dir / "native_results.json").is_file()
            and (attempt_dir / "mode_candidates.json").is_file()
            and (attempt_dir / "artifact_index.json").is_file()
        )

    def _resume_decision(
        self,
        window: SolverWindow,
        *,
        force_retry: bool = False,
    ) -> str:
        record = self.state.get_window(window.solver_window_id)
        status = str(record.get("status", "pending"))
        if status in _COMPLETED_STATUSES and self._window_artifacts_complete(window):
            return "skip_completed"
        if status in _AVOID_STATUSES:
            return "run_forced" if force_retry else "avoid"
        if status == "running":
            return (
                "skip_active"
                if self._record_has_active_process(
                    window.solver_window_id, record
                )
                else "run_interrupted"
            )
        if status in _RUNNABLE_STATUSES:
            return "run"
        if status == "failed":
            return "avoid" if not force_retry else "run_forced"
        return "run"

    def resume_preview(
        self,
        *,
        window_id: str = "",
        force_retry: bool = False,
    ) -> dict[str, Any]:
        """Return a read-only resume decision table and empirical ETA."""

        selected = [
            window
            for window in self.windows
            if not window_id or window.solver_window_id == window_id
        ]
        if window_id and not selected:
            raise KeyError(f"unknown solver window: {window_id}")
        rows = []
        baseline_hours = 0.0
        for window in selected:
            decision = self._resume_decision(
                window, force_retry=force_retry
            )
            estimate_minutes = self._estimate_window_minutes(window)
            if decision.startswith("run"):
                baseline_hours += estimate_minutes / 60.0
            rows.append(
                {
                    "solver_window_id": window.solver_window_id,
                    "status": self.state.get_window(
                        window.solver_window_id
                    ).get("status", "pending"),
                    "decision": decision,
                    "estimated_minutes": estimate_minutes,
                }
            )
        return {
            "windows": rows,
            "run_count": sum(
                str(row["decision"]).startswith("run") for row in rows
            ),
            "skip_count": sum(row["decision"] == "skip_completed" for row in rows),
            "active_count": sum(row["decision"] == "skip_active" for row in rows),
            "avoid_count": sum(row["decision"] == "avoid" for row in rows),
            "ideal_hours": round(baseline_hours, 1),
            "realistic_hours": (
                round(baseline_hours * 1.35, 1),
                round(baseline_hours * 2.0, 1),
            ),
        }

    @staticmethod
    def _estimate_window_minutes(window: SolverWindow) -> float:
        if window.f_hom_mhz < 1600:
            return 40.0
        if window.f_hom_mhz < 2800:
            return 75.0
        if window.f_hom_mhz < 2900:
            return 105.0
        return 120.0

    def run(
        self,
        *,
        window_id: str = "",
        force_retry: bool = False,
    ) -> list[EigenmodeCandidate]:
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
                decision = self._resume_decision(
                    window,
                    force_retry=bool(
                        force_retry
                        and selected_ids is not None
                        and window.solver_window_id in selected_ids
                    ),
                )
                if decision in {"skip_completed", "skip_active", "avoid"}:
                    continue
                outcome = self._run_window_with_retries(
                    window,
                    force_retry=decision == "run_forced",
                )
                self.aggregate_outputs()
                if outcome.get("failed"):
                    continue
                if outcome["mode_count_censored"]:
                    if selected_ids is not None:
                        current = self.state.get_window(
                            window.solver_window_id
                        )
                        self.state.set_window(
                            window.solver_window_id,
                            current.get("status", "postprocessed"),
                            window=window.to_dict(),
                            mode_count_censored=True,
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
                            mode_count_censored=True,
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
                            init_attempt_count=0,
                            long_attempt_count=0,
                            attempt_history=[],
                        )
                    if followups:
                        write_solver_windows(
                            self.campaign_dir / "hom_solver_windows.csv",
                            self.windows,
                        )
            return self.aggregate_outputs()
        finally:
            try:
                self.aggregate_outputs()
            except Exception:
                _logger.warning(
                    "Could not refresh Workflow 4 aggregate outputs",
                    exc_info=True,
                )
            self._verify_inputs_unchanged()

    def _run_window_with_retries(
        self,
        window: SolverWindow,
        *,
        force_retry: bool = False,
    ) -> dict[str, Any]:
        record = self.state.get_window(window.solver_window_id)
        if force_retry:
            record["init_attempt_count"] = 0
            record["long_attempt_count"] = 0
            self.state.set_window(
                window.solver_window_id,
                "retry_pending",
                window=window.to_dict(),
                init_attempt_count=0,
                long_attempt_count=0,
                terminal_reason="forced_manual_retry",
            )
        else:
            recovered = self._recover_saved_extraction(window)
            if recovered is not None:
                return recovered
        last_error = ""
        while True:
            record = self.state.get_window(window.solver_window_id)
            init_count = int(record.get("init_attempt_count", 0))
            long_count = int(record.get("long_attempt_count", 0))
            if init_count >= self.config.fast_retry_attempts:
                return self._avoid_window(
                    window,
                    last_error or str(record.get("error", "")),
                    "init_fast_retry_budget_exhausted",
                )
            if long_count >= self.config.long_retry_attempts:
                return self._avoid_window(
                    window,
                    last_error or str(record.get("error", "")),
                    "long_retry_budget_exhausted",
                )
            attempt_number = self._next_attempt_number(window)
            try:
                return self._run_window(window, attempt_number)
            except KeyboardInterrupt:
                raise
            except AttemptFailure as exc:
                last_error = str(exc)
                failure_record = {
                    "attempt_id": (
                        exc.attempt_dir.name if exc.attempt_dir else ""
                    ),
                    "failure_class": exc.failure_class,
                    "error": last_error,
                    "elapsed_s": exc.elapsed_s,
                    "ended_at": utc_now(),
                }
                failures = list(record.get("failure_history", []))
                failures.append(failure_record)
                if exc.failure_class == "init_fast":
                    init_count += 1
                    exhausted = init_count >= self.config.fast_retry_attempts
                    status = "avoid_retry" if exhausted else "retry_pending"
                    self.state.set_window(
                        window.solver_window_id,
                        status,
                        window=window.to_dict(),
                        error=last_error,
                        failure_class=exc.failure_class,
                        failure_history=failures,
                        init_attempt_count=init_count,
                        long_attempt_count=long_count,
                        terminal_reason=(
                            "init_fast_retry_budget_exhausted"
                            if exhausted
                            else ""
                        ),
                    )
                    if exhausted:
                        return {
                            "failed": True,
                            "mode_count": 0,
                            "mode_count_censored": False,
                            "attempt_dir": "",
                            "candidates": [],
                        }
                    delay_index = min(
                        init_count - 1,
                        len(self.config.fast_retry_backoff_s) - 1,
                    )
                    delay = (
                        self.config.fast_retry_backoff_s[delay_index]
                        if self.config.fast_retry_backoff_s
                        else self.config.retry_cooldown_s
                    )
                    _logger.warning(
                        "Window %s fast initialization failure %d/%d; "
                        "fresh-template retry in %.1f s",
                        window.solver_window_id,
                        init_count,
                        self.config.fast_retry_attempts,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                long_count += 1
                exhausted = long_count >= self.config.long_retry_attempts
                status = "avoid_retry" if exhausted else "retry_pending"
                self.state.set_window(
                    window.solver_window_id,
                    status,
                    window=window.to_dict(),
                    error=last_error,
                    failure_class=exc.failure_class,
                    failure_history=failures,
                    init_attempt_count=init_count,
                    long_attempt_count=long_count,
                    terminal_reason=(
                        "long_retry_budget_exhausted" if exhausted else ""
                    ),
                )
                if exhausted:
                    _logger.error(
                        "Window %s exhausted its two long-attempt budget",
                        window.solver_window_id,
                    )
                    return {
                        "failed": True,
                        "mode_count": 0,
                        "mode_count_censored": False,
                        "attempt_dir": "",
                        "candidates": [],
                    }
                _logger.warning(
                    "Window %s long attempt failed after %.1f s; "
                    "exactly one long retry remains",
                    window.solver_window_id,
                    exc.elapsed_s,
                )

    def _recover_saved_extraction(
        self,
        window: SolverWindow,
    ) -> dict[str, Any] | None:
        """Reuse a solved project after interruption before spending a solve."""

        record = self.state.get_window(window.solver_window_id)
        if record.get("status") not in {
            "interrupted",
            "extract_retry_pending",
            "result_contract_incomplete",
        }:
            return None
        attempt_dir = self._attempt_dir_from_record(
            window.solver_window_id, record
        )
        if attempt_dir is None:
            return None
        metadata = self._read_attempt_metadata(attempt_dir)
        diagnostics = read_attempt_diagnostics(attempt_dir)
        attempt_project = self._attempt_project(attempt_dir)
        local_export = attempt_project.with_suffix("") / "Export" / "3d"
        if not (
            attempt_project.is_file()
            and local_export.is_dir()
            and diagnostics.solver_successful
            and metadata.get("phase")
            in {"solved", "save", "export", "postprocess"}
        ):
            return None
        if not any(
            kinds == {"e", "h"}
            for kinds in archived_hdf5_mode_pairs(
                [
                    item.to_dict()
                    for item in snapshot_directory(local_export).values()
                ],
                self._mode_field_patterns(),
            ).values()
        ):
            return None
        attempt_id = str(metadata.get("attempt_id") or attempt_dir.name)
        _logger.warning(
            "Window %s has a saved solver result; retrying extraction before "
            "spending the remaining long-solve budget",
            window.solver_window_id,
        )
        external = self.config.field_contract.export_dir.resolve()
        export_before = {
            local_export.resolve(): {},
            external: snapshot_directory(external),
        }
        try:
            outcome = self._extract_attempt(
                window,
                attempt_id,
                attempt_dir,
                attempt_project,
                diagnostics,
                export_before=export_before,
                replace_existing=True,
            )
        except Exception as exc:
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="export",
                outcome="interrupted",
                recovery="saved_result_extraction",
                recovery_error=str(exc),
            )
            self.state.set_window(
                window.solver_window_id,
                "retry_pending",
                window=window.to_dict(),
                error=f"saved-result extraction recovery failed: {exc}",
                failure_class="export_postprocess",
            )
            return None
        self._write_attempt_metadata(
            window.solver_window_id,
            attempt_dir,
            phase="postprocess",
            outcome="success",
            ended_at=utc_now(),
            recovery="saved_result_extraction",
        )
        return outcome

    def _avoid_window(
        self,
        window: SolverWindow,
        error: str,
        reason: str,
    ) -> dict[str, Any]:
        self.state.set_window(
            window.solver_window_id,
            "avoid_retry",
            window=window.to_dict(),
            error=error,
            terminal_reason=reason,
        )
        return {
            "failed": True,
            "mode_count": 0,
            "mode_count_censored": False,
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
        attempt_project = self._attempt_project(attempt_dir)
        started_at = utc_now()
        revision = self.active_template_revision
        window_record = self.state.get_window(window.solver_window_id)
        metadata = {
            "window": window.to_dict(),
            "attempt_id": attempt_id,
            "started_at": started_at,
            "ended_at": "",
            "phase": "prepare",
            "outcome": "running",
            "template_revision_id": revision.get("revision_id", ""),
            "template_hash": revision.get(
                "template_hash", self.hashes["template_hash"]
            ),
            "retry_generation": int(
                window_record.get("retry_generation", 0)
            ),
            "attempt_project": attempt_project.relative_to(
                self.campaign_dir
            ).as_posix(),
            "cst_messages_path": (
                attempt_dir / "cst_messages.json"
            ).relative_to(self.campaign_dir).as_posix(),
            "artifact_index_path": (
                attempt_dir / "artifact_index.json"
            ).relative_to(self.campaign_dir).as_posix(),
            "result_contract_audit_path": (
                attempt_dir / "result_contract_audit.json"
            ).relative_to(self.campaign_dir).as_posix(),
        }
        write_json(attempt_dir / "attempt_metadata.json", metadata)
        self.state.record_attempt(window.solver_window_id, metadata)
        self.state.set_window(
            window.solver_window_id,
            "running",
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=attempt_dir.relative_to(self.campaign_dir).as_posix(),
        )
        t0 = time.perf_counter()
        export_before = {
            root: snapshot_directory(root)
            for root in self._export_roots(attempt_project)
        }
        try:
            self._prepare_attempt_project(
                window, attempt_dir, attempt_project
            )
            solver_result, diagnostics = self._solve_attempt_project(
                window, attempt_dir, attempt_project
            )
            elapsed = time.perf_counter() - t0
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="solved",
                solver_elapsed_s=solver_result.elapsed_s,
                wall_elapsed_s=elapsed,
                meshing_successful=diagnostics.meshing_successful,
                solver_successful=diagnostics.solver_successful,
                mode_table_present=diagnostics.mode_table_present,
                final_mode_numbers=list(diagnostics.final_mode_numbers),
                final_mode_frequencies_hz={
                    str(mode): frequency
                    for mode, frequency in diagnostics.final_mode_frequencies_hz
                },
                propagating_warning_ports=list(
                    diagnostics.propagating_warning_ports
                ),
            )
            try:
                outcome = self._extract_attempt(
                    window,
                    attempt_id,
                    attempt_dir,
                    attempt_project,
                    diagnostics,
                    export_before=export_before,
                )
            except Exception as first_error:
                _logger.warning(
                    "Window %s solve succeeded but extraction failed; "
                    "retrying extraction once without a new solve",
                    window.solver_window_id,
                    exc_info=True,
                )
                try:
                    outcome = self._extract_attempt(
                        window,
                        attempt_id,
                        attempt_dir,
                        attempt_project,
                        diagnostics,
                        export_before=export_before,
                        replace_existing=True,
                    )
                except Exception as second_error:
                    raise AttemptFailure(
                        "solver succeeded but result extraction remained "
                        f"unrecoverable: {first_error}; retry: {second_error}",
                        failure_class="export_postprocess",
                        elapsed_s=elapsed,
                        diagnostics=diagnostics,
                        attempt_dir=attempt_dir,
                    ) from second_error
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="postprocess",
                outcome="success",
                ended_at=utc_now(),
                wall_elapsed_s=time.perf_counter() - t0,
            )
            return outcome
        except CleanupIncompleteError:
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="cleanup",
                outcome="failed",
                ended_at=utc_now(),
                wall_elapsed_s=time.perf_counter() - t0,
                failure_class="cleanup_incomplete",
            )
            raise
        except KeyboardInterrupt:
            elapsed = time.perf_counter() - t0
            interrupted_phase = str(
                self._read_attempt_metadata(attempt_dir).get("phase", "solve")
            )
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase=interrupted_phase,
                outcome="interrupted",
                ended_at=utc_now(),
                wall_elapsed_s=elapsed,
                failure_class="external_interrupt",
            )
            record = self.state.get_window(window.solver_window_id)
            long_count = int(record.get("long_attempt_count", 0))
            if elapsed >= self.config.long_attempt_threshold_s:
                long_count += 1
            self.state.set_window(
                window.solver_window_id,
                "interrupted",
                window=window.to_dict(),
                attempt_id=attempt_id,
                attempt_dir=attempt_dir.relative_to(
                    self.campaign_dir
                ).as_posix(),
                failure_class="external_interrupt",
                long_attempt_count=long_count,
                error="manual or external interruption",
            )
            raise
        except AttemptFailure as exc:
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase=(
                    "postprocess"
                    if exc.failure_class == "export_postprocess"
                    else "solve"
                ),
                outcome="failed",
                ended_at=utc_now(),
                wall_elapsed_s=time.perf_counter() - t0,
                failure_class=exc.failure_class,
                error=str(exc),
                meshing_successful=(
                    exc.diagnostics.meshing_successful
                    if exc.diagnostics
                    else False
                ),
                solver_successful=(
                    exc.diagnostics.solver_successful
                    if exc.diagnostics
                    else False
                ),
                mode_table_present=(
                    exc.diagnostics.mode_table_present
                    if exc.diagnostics
                    else False
                ),
                final_mode_numbers=(
                    list(exc.diagnostics.final_mode_numbers)
                    if exc.diagnostics
                    else []
                ),
                final_mode_frequencies_hz=(
                    {
                        str(mode): frequency
                        for mode, frequency in (
                            exc.diagnostics.final_mode_frequencies_hz
                        )
                    }
                    if exc.diagnostics
                    else {}
                ),
            )
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            diagnostics = read_attempt_diagnostics(attempt_dir)
            failure_class = classify_solver_failure(
                diagnostics,
                elapsed_s=elapsed,
                long_attempt_threshold_s=(
                    self.config.long_attempt_threshold_s
                ),
            )
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="prepare",
                outcome="failed",
                ended_at=utc_now(),
                wall_elapsed_s=elapsed,
                failure_class=failure_class,
                error=str(exc),
                meshing_successful=diagnostics.meshing_successful,
                solver_successful=diagnostics.solver_successful,
                mode_table_present=diagnostics.mode_table_present,
                final_mode_numbers=list(diagnostics.final_mode_numbers),
            )
            raise AttemptFailure(
                str(exc),
                failure_class=failure_class,
                elapsed_s=elapsed,
                diagnostics=diagnostics,
                attempt_dir=attempt_dir,
            ) from exc

    def _prepare_attempt_project(
        self,
        window: SolverWindow,
        attempt_dir: Path,
        attempt_project: Path,
    ) -> None:
        """Build and save a clean, result-free project in its own CST session."""

        _safe_copy(self.config.template_path, attempt_project)
        connection: CSTConnection | None = None
        project = None
        recorded_pid: int | None = None
        try:
            connection = self._new_connection()
            recorded_pid = connection.pid
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="rebuild",
                prepare_pid=recorded_pid,
            )
            project = connection.open_project(str(attempt_project))
            updated = project.update_parameters(
                {self.config.parameter_name: window.f_hom_mhz},
                use_full_rebuild=True,
            )
            if not updated:
                raise RuntimeError(
                    f"failed to update parameter {self.config.parameter_name}"
                )
            if not project.save(include_results=False):
                raise RuntimeError("failed to save result-free rebuilt project")
            project.close(save=False)
            project = None
            owned_connection = connection
            connection = None
            self._close_attempt_connection(
                owned_connection,
                window_id=window.solver_window_id,
                attempt_dir=attempt_dir,
                phase="rebuild_close",
                recorded_pid=recorded_pid,
            )
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="ready",
            )
        finally:
            if project is not None:
                project.close(save=False)
            if connection is not None:
                owned_connection = connection
                connection = None
                self._close_attempt_connection(
                    owned_connection,
                    window_id=window.solver_window_id,
                    attempt_dir=attempt_dir,
                    phase="rebuild_failure_close",
                    recorded_pid=recorded_pid,
                )

    def _solve_attempt_project(
        self,
        window: SolverWindow,
        attempt_dir: Path,
        attempt_project: Path,
    ) -> tuple[Any, AttemptDiagnostics]:
        """Solve using a second fresh CST connection and preserve diagnostics."""

        connection: CSTConnection | None = None
        project = None
        solver_result = None
        diagnostics = read_attempt_diagnostics(attempt_dir)
        recorded_pid: int | None = None
        try:
            connection = self._new_connection()
            recorded_pid = connection.pid
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="solve",
                solve_pid=recorded_pid,
            )
            project = connection.open_project(str(attempt_project))
            solver = SolverRunner(
                timeout_s=self.config.solver_timeout_s,
                settle_s=self.config.solver_settle_s,
            )
            solver_result = solver.run(project)
            try:
                messages = project.get_messages()
            except Exception:
                messages = []
            diagnostics = write_messages(attempt_dir, messages)
            if not solver_result.success:
                failure_class = classify_solver_failure(
                    diagnostics,
                    elapsed_s=solver_result.elapsed_s,
                    long_attempt_threshold_s=(
                        self.config.long_attempt_threshold_s
                    ),
                )
                raise AttemptFailure(
                    f"CST solver failed ({solver_result.error_type}): "
                    f"{solver_result.error_message}",
                    failure_class=failure_class,
                    elapsed_s=solver_result.elapsed_s,
                    diagnostics=diagnostics,
                    attempt_dir=attempt_dir,
                )
            if not diagnostics.solver_successful:
                raise AttemptFailure(
                    "CST returned from run_solver without an explicit "
                    "Eigenmode solver successful message",
                    failure_class="long_solve",
                    elapsed_s=solver_result.elapsed_s,
                    diagnostics=diagnostics,
                    attempt_dir=attempt_dir,
                )
            self._write_attempt_metadata(
                window.solver_window_id,
                attempt_dir,
                phase="save",
            )
            if not project.save(include_results=True):
                raise AttemptFailure(
                    "failed to save solved attempt project",
                    failure_class="long_solve",
                    elapsed_s=solver_result.elapsed_s,
                    diagnostics=diagnostics,
                    attempt_dir=attempt_dir,
                )
            project.close(save=False)
            project = None
            owned_connection = connection
            connection = None
            self._close_attempt_connection(
                owned_connection,
                window_id=window.solver_window_id,
                attempt_dir=attempt_dir,
                phase="solve_close",
                recorded_pid=recorded_pid,
            )
            return solver_result, diagnostics
        finally:
            if project is not None:
                project.close(save=False)
            if connection is not None:
                owned_connection = connection
                connection = None
                self._close_attempt_connection(
                    owned_connection,
                    window_id=window.solver_window_id,
                    attempt_dir=attempt_dir,
                    phase="solve_failure_close",
                    recorded_pid=recorded_pid,
                )

    def _extract_attempt(
        self,
        window: SolverWindow,
        attempt_id: str,
        attempt_dir: Path,
        attempt_project: Path,
        diagnostics: AttemptDiagnostics,
        *,
        export_before: dict[Path, dict[str, Any]] | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        raw_dir = attempt_dir / "raw"
        if replace_existing:
            for path in (
                raw_dir / "lines",
                raw_dir / "3d",
                attempt_dir / "native_results.json",
                attempt_dir / "mode_candidates.json",
                attempt_dir / "artifact_index.json",
                attempt_dir / "line_field_archive_status.json",
            ):
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()

        self._write_attempt_metadata(
            window.solver_window_id,
            attempt_dir,
            phase="export",
        )
        adapter = EigenmodeResultAdapter(
            attempt_project,
            self.config.result_contract,
            max_modes=self.config.max_modes,
            allow_interactive=False,
        )
        all_native_modes = adapter.read_native_modes()
        reported = set(diagnostics.final_mode_numbers)
        native_modes = [
            mode
            for mode in all_native_modes
            if mode.mode_number in reported
            and _reported_frequency_matches(
                mode.mode_number,
                mode.frequency_hz,
                diagnostics,
            )
            and window.search_min_hz <= mode.frequency_hz <= window.search_max_hz
        ]
        write_native_results(
            attempt_dir / "native_results.json", native_modes, adapter.errors
        )
        audit = adapter.audit(self.config.field_contract)
        audit["reported_mode_numbers"] = list(diagnostics.final_mode_numbers)
        audit["reported_mode_frequencies_hz"] = {
            str(mode): frequency
            for mode, frequency in diagnostics.final_mode_frequencies_hz
        }
        audit["accepted_mode_numbers"] = [
            mode.mode_number for mode in native_modes
        ]
        line_archive_status = adapter.archive_complex_lines(
            native_modes,
            self.config.field_contract,
            raw_dir / "lines",
        )
        for point_status in line_archive_status.values():
            for point, value in list(point_status.items()):
                text = str(value)
                if not text or text.startswith("ERROR:"):
                    continue
                path = Path(text)
                if path.is_absolute():
                    try:
                        point_status[point] = path.relative_to(
                            self.campaign_dir
                        ).as_posix()
                    except ValueError:
                        pass
        write_json(
            attempt_dir / "line_field_archive_status.json",
            line_archive_status,
        )

        before_by_root = export_before or {}
        export_snapshots = []
        for root in self._export_roots(attempt_project):
            before = before_by_root.get(root, {})
            after = snapshot_directory(root)
            changed = changed_files(before, after)
            recognized_count = sum(
                len(kinds)
                for kinds in archived_hdf5_mode_pairs(
                    [item.to_dict() for item in changed],
                    self._mode_field_patterns(),
                ).values()
            )
            export_snapshots.append(
                (recognized_count, len(changed), root, before, after, changed)
            )
        _, _, runtime_export_dir, before, after, changed = max(
            export_snapshots,
            key=lambda item: (item[0], item[1], -len(str(item[2]))),
        )
        archived = archive_changed_files(
            runtime_export_dir,
            raw_dir / "3d",
            changed,
            path_base=self.campaign_dir,
        )
        write_artifact_index(
            attempt_dir / "artifact_index.json",
            source_root=runtime_export_dir,
            before=before,
            after=after,
            archived=archived,
        )
        pairs = archived_hdf5_mode_pairs(
            archived,
            self._mode_field_patterns(),
        )
        rejection_reasons: list[str] = []
        if not diagnostics.mode_table_present:
            rejection_reasons.append("missing_final_mode_table")
        if set(mode.mode_number for mode in native_modes) != reported:
            rejection_reasons.append(
                "native_mode_numbers_do_not_match_final_mode_table"
            )
        for mode in native_modes:
            if pairs.get(mode.mode_number, set()) != {"e", "h"}:
                rejection_reasons.append(
                    f"mode_{mode.mode_number}:missing_fresh_EH_pair"
                )
            point_status = line_archive_status.get(str(mode.mode_number), {})
            for point in REQUIRED_FIELD_POINTS:
                value = str(point_status.get(point, ""))
                if not value or value.startswith("ERROR:"):
                    rejection_reasons.append(
                        f"mode_{mode.mode_number}:{point}:missing_fresh_line"
                    )
        audit["freshness_rejection_reasons"] = rejection_reasons
        audit["template_contract_complete"] = not (
            audit.get("required_missing")
            or audit.get("missing_field_patterns")
            or rejection_reasons
        )
        write_json(attempt_dir / "result_contract_audit.json", audit)
        write_json(self.campaign_dir / "result_contract_audit.json", audit)
        if rejection_reasons:
            self.state.set_window(
                window.solver_window_id,
                "result_contract_incomplete",
                window=window.to_dict(),
                attempt_id=attempt_id,
                attempt_dir=attempt_dir.relative_to(
                    self.campaign_dir
                ).as_posix(),
                required_missing=rejection_reasons,
            )
            raise RuntimeError("; ".join(rejection_reasons))

        mode_count_censored = (
            len(native_modes) == self.config.max_modes
        )
        candidates = self._process_attempt(
            window,
            attempt_id,
            attempt_dir,
            native_modes,
            diagnostics=diagnostics,
            mode_count_censored=mode_count_censored,
        )
        self.state.set_window(
            window.solver_window_id,
            "postprocessed",
            clear_active_error=True,
            window=window.to_dict(),
            attempt_id=attempt_id,
            attempt_dir=attempt_dir.relative_to(
                self.campaign_dir
            ).as_posix(),
            native_mode_count=len(native_modes),
            archived_file_count=len(archived),
            mode_count_censored=mode_count_censored,
            required_missing=[],
            warning_codes=list(diagnostics.warning_codes),
            propagating_warning_ports=list(
                diagnostics.propagating_warning_ports
            ),
            boundary_sensitive=diagnostics.boundary_sensitive,
            terminal_reason="",
        )
        return {
            "failed": False,
            "mode_count": len(native_modes),
            "mode_count_censored": mode_count_censored,
            "attempt_dir": attempt_dir.relative_to(
                self.campaign_dir
            ).as_posix(),
            "candidates": candidates,
        }

    def _export_roots(self, attempt_project: Path) -> tuple[Path, ...]:
        """Return copy-local and configured external CST export roots."""

        roots = [
            attempt_project.with_suffix("") / "Export" / "3d",
            self.config.field_contract.export_dir,
        ]
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            resolved = root.resolve()
            key = str(resolved).casefold()
            if key not in seen:
                seen.add(key)
                unique.append(resolved)
        return tuple(unique)

    def _mode_field_patterns(self) -> dict[str, str]:
        field_contract = getattr(self.config, "field_contract", None)
        return dict(
            getattr(
                field_contract,
                "mode_field_patterns",
                {
                    "e": "Mode {mode}_e.h5",
                    "h": "Mode {mode}_h.h5",
                },
            )
        )

    def _process_attempt(
        self,
        window: SolverWindow,
        attempt_id: str,
        attempt_dir: Path,
        native_modes: Iterable[NativeModeResult],
        *,
        diagnostics: AttemptDiagnostics | None = None,
        mode_count_censored: bool = False,
    ) -> list[EigenmodeCandidate]:
        raw_dir = attempt_dir / "raw"
        candidates: list[EigenmodeCandidate] = []
        diagnostics = diagnostics or read_attempt_diagnostics(attempt_dir)
        attempt_metadata = self._read_attempt_metadata(attempt_dir)
        revision = self._template_revision_for_metadata(attempt_metadata)
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
                warning_codes=list(diagnostics.warning_codes),
                boundary_sensitive=diagnostics.boundary_sensitive,
                mode_count_censored=mode_count_censored,
                template_revision_id=str(
                    attempt_metadata.get("template_revision_id")
                    or revision.get("revision_id", "")
                ),
                template_hash=str(
                    attempt_metadata.get("template_hash")
                    or revision.get("template_hash", "")
                ),
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
                        relative = destination.relative_to(
                            self.campaign_dir
                        ).as_posix()
                        candidate.field_paths[point] = relative
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
                    candidate.field_paths[point] = destination.relative_to(
                        self.campaign_dir
                    ).as_posix()
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
        """Re-read accepted archived fields and regenerate derived outputs."""

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
            diagnostics = read_attempt_diagnostics(attempt_dir)
            accepted_numbers = set(diagnostics.final_mode_numbers)
            native_modes = [
                mode
                for mode in native_modes
                if mode.mode_number in accepted_numbers
                and _reported_frequency_matches(
                    mode.mode_number,
                    mode.frequency_hz,
                    diagnostics,
                )
                and window.search_min_hz
                <= mode.frequency_hz
                <= window.search_max_hz
            ]
            self._process_attempt(
                window,
                str(metadata["attempt_id"]),
                attempt_dir,
                native_modes,
                diagnostics=diagnostics,
                mode_count_censored=(
                    len(native_modes) == self.config.max_modes
                ),
            )
        return self.aggregate_outputs()

    def _resolve_candidate_field_path(
        self,
        candidate: EigenmodeCandidate,
        point: str,
    ) -> Path:
        value = candidate.field_paths.get(point, "")
        if value:
            path = Path(value)
            if not path.is_absolute():
                path = self.campaign_dir / path
            if path.is_file():
                return path
        return self.campaign_dir / "fields" / candidate.mode_id / f"{point}.npz"

    def _candidate_is_fresh(
        self,
        candidate: EigenmodeCandidate,
        attempt_dir: Path,
        window: SolverWindow,
    ) -> bool:
        diagnostics = read_attempt_diagnostics(attempt_dir)
        if candidate.mode_number not in diagnostics.final_mode_numbers:
            return False
        if not _reported_frequency_matches(
            candidate.mode_number,
            candidate.frequency_hz,
            diagnostics,
        ):
            return False
        if not (
            window.search_min_hz
            <= candidate.frequency_hz
            <= window.search_max_hz
        ):
            return False
        artifact_path = attempt_dir / "artifact_index.json"
        if not artifact_path.is_file():
            return False
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        archived = artifact.get("archived", [])
        pairs = archived_hdf5_mode_pairs(
            archived,
            self._mode_field_patterns(),
        )
        if pairs.get(candidate.mode_number, set()) != {"e", "h"}:
            return False
        mode_artifacts = [
            item
            for item in archived
            if Path(str(item.get("relative_path", ""))).name.lower()
            in {
                f"mode {candidate.mode_number}_e.h5".lower(),
                f"mode {candidate.mode_number}_h.h5".lower(),
            }
        ]
        if len(mode_artifacts) != 2:
            return False
        for item in mode_artifacts:
            artifact_file = (
                attempt_dir / "raw" / "3d" / str(item["relative_path"])
            )
            if not self._artifact_file_valid(artifact_file, item):
                return False
        for point in REQUIRED_FIELD_POINTS:
            path = self._resolve_candidate_field_path(candidate, point)
            if not path.is_file():
                return False
            try:
                field = read_complex_line_npz(path)
            except Exception:
                return False
            if len(field.z_m) < 2 or len(field.z_m) != len(field.ez_v_per_m):
                return False
            candidate.field_paths[point] = path.relative_to(
                self.campaign_dir
            ).as_posix()
        candidate.warning_codes = list(diagnostics.warning_codes)
        candidate.boundary_sensitive = diagnostics.boundary_sensitive
        candidate.mode_count_censored = (
            len(diagnostics.final_mode_numbers) == self.config.max_modes
        )
        return True

    def _artifact_file_valid(
        self,
        path: Path,
        fingerprint: dict[str, Any],
    ) -> bool:
        if not path.is_file():
            return False
        stat = path.stat()
        expected_size = int(fingerprint.get("size", -1))
        expected_hash = str(fingerprint.get("sha256", ""))
        if stat.st_size != expected_size or not expected_hash:
            return False
        key = (
            str(path.resolve()),
            stat.st_size,
            stat.st_mtime_ns,
            expected_hash,
        )
        cached = self._artifact_validation_cache.get(key)
        if cached is not None:
            return cached
        valid = sha256_file(path) == expected_hash
        self._artifact_validation_cache[key] = valid
        return valid

    def _load_all_candidates(self) -> list[EigenmodeCandidate]:
        candidates: list[EigenmodeCandidate] = []
        for path in sorted(
            (self.campaign_dir / "windows").glob(
                "*/attempt_*/mode_candidates.json"
            )
        ):
            metadata = self._read_attempt_metadata(path.parent)
            window_data = metadata.get("window")
            if not window_data:
                continue
            window = SolverWindow(**window_data)
            payload = json.loads(path.read_text(encoding="utf-8"))
            for item in payload:
                candidate = EigenmodeCandidate.from_dict(item)
                revision = self._template_revision_for_metadata(metadata)
                if not candidate.template_revision_id:
                    candidate.template_revision_id = str(
                        metadata.get("template_revision_id")
                        or revision.get("revision_id", "")
                    )
                if not candidate.template_hash:
                    candidate.template_hash = str(
                        metadata.get("template_hash")
                        or revision.get("template_hash", "")
                    )
                if self._candidate_is_fresh(candidate, path.parent, window):
                    candidates.append(candidate)
        return candidates

    def aggregate_outputs(self) -> list[EigenmodeCandidate]:
        candidates = self._load_all_candidates()
        center_fields = {}
        for candidate in candidates:
            center_path = self._resolve_candidate_field_path(
                candidate, "center"
            )
            if center_path.is_file():
                if center_path.suffix.lower() == ".npz":
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
        mappings, _ = build_mode_target_mapping(
            deduplicated,
            self.clusters,
            match_half_width_mhz=self.config.match_half_width_mhz,
        )
        write_valid_seed(
            self.campaign_dir / "hom_valid_seed.csv",
            deduplicated,
            mappings,
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
                status in {"result_contract_incomplete", "extract_retry_pending"}
                for status in statuses
            ):
                reasons[cluster.target_cluster_id] = "result_contract_incomplete"
            elif statuses and all(status in _AVOID_STATUSES for status in statuses):
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
