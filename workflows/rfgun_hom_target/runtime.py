"""Verified CST lifecycle for WF5; every mutation targets an owned copy.

Solver VBA is sourced from the user-supplied ModelHistory and official CST
EigenmodeSolver documentation: SetFrequencyTarget specifies a LOWER frequency
limit; modes above it are calculated in ascending frequency order. The
all-modes-in-range switch is JDM-only and is not used with General (Lossy).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import logging
import math
from pathlib import Path
import re
import time
from uuid import uuid4
from typing import Any, Callable, Iterator

from .storage import atomic_json, copy_verified_project, digest, BudgetExhausted
from .postprocess import PostprocessConfig, read_native_modes, collect_and_analyze
from .session_recovery import ensure_sessions_inactive, query_pid

LOG = logging.getLogger(__name__)
FREQUENCY_FACTORS = {"Hz": 1., "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
LENGTH_TO_MM = {"mm": 1., "cm": 10., "m": 1000., "um": .001}


class EvaluationFailure(RuntimeError):
    """A classified failure, with narrowly scoped transient retry semantics."""
    def __init__(self, message: str, category: str = "solver_failed", transient: bool = False):
        super().__init__(message)
        self.category, self.transient = category, transient


def metadata(project: Path) -> dict[str, Any]:
    """Read saved source metadata without opening CST or trusting stale results."""
    folder = project.with_suffix("")
    history = json.loads((folder / "Model/3D/ModelHistory.json").read_text(encoding="utf-8-sig"))
    params = json.loads((folder / "Model/Parameters.json").read_text(encoding="utf-8-sig"))
    general = history["general"]
    length = general.get("length")
    frequency = general.get("frequency")
    funit = frequency.get("unit") if isinstance(frequency, dict) else frequency
    if length not in LENGTH_TO_MM or funit not in FREQUENCY_FACTORS:
        raise ValueError("Unsupported/missing project length or frequency unit")
    return {"length_unit": length, "frequency_unit": funit,
            "parameters": {p["name"]: float(p["value"]) for p in params["parameters"]},
            "general": general}


def read_baseline(project: Path, config: Any) -> dict[str, float]:
    """Read canonical degrees/mm from the current template parameter table."""
    info = metadata(project)
    values = {}
    for p in config.parameters:
        value = info["parameters"][p.cst_name or p.name]
        if p.unit == "mm":
            value *= LENGTH_TO_MM[info["length_unit"]]
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite template parameter {p.name}")
        values[p.name] = value
    return values


def postprocess_config(config: Any, info: dict[str, Any]) -> PostprocessConfig:
    """Translate the public workflow configuration to the portable field contract."""
    if config.results.frequency_unit != info["frequency_unit"]:
        raise ValueError("Configured result frequency unit differs from template metadata")
    p = config.physics
    pattern = re.escape(config.results.frequency).replace(re.escape("{mode}"), r"(\d+)")
    return PostprocessConfig(z_range_mm=p.z_range_mm, z_samples=p.z_samples, offsets_mm=p.offsets_mm,
        frequency_pattern=pattern, frequency_unit=config.results.frequency_unit,
        q_loaded_path=config.results.q_loaded, field_path=config.results.efield,
        geometry_unit=info["length_unit"], beta=p.beta, field_amplitude=p.field_convention,
        conductivity_layers=p.conductivity_layers, gradient_tolerance=p.gradient_tolerance,
        sampling_tolerance=p.integration_tolerance, minimum_q=p.min_q,
        vba_timeout_s=config.solver.postprocess_timeout_s)


def solver_vba(config: Any, frequency_unit: str, mode_count: int) -> str:
    """Set eigenmode search only; preserve user-tested mesh/material/port settings.

    Public frequencies use MHz; VBA frequencies use the template's own unit.
    No Reset or mesh adaptation command is issued.
    """
    scale = 1e6 / FREQUENCY_FACTORS[frequency_unit]
    lo, hi = config.physics.frequency_min_mhz * scale, config.solver.upper_frequency_mhz * scale
    target = config.solver.target_frequency_mhz * scale
    if target > lo:
        raise ValueError("Solver lower frequency limit must not skip the objective band")
    return "\n".join(['ChangeSolverType "HF Eigenmode"',
        f'Solver.FrequencyRange "{lo:.15g}", "{hi:.15g}"',
        'Solver.CalculationType "Eigenmode"', 'With EigenmodeSolver',
        ' .SetMethodType "General (Lossy)", "Tet"',
        ' .SetModesInFrequencyRange "False"',
        f' .SetFrequencyTarget "True", "{target:.15g}"',
        f' .SetNumberOfModes "{mode_count}"',
        ' .SetCalculateExternalQFactor "True"', 'End With'])


def coverage_complete(native: Any, mode_count: int, upper_mhz: float) -> bool:
    """An ascending, contiguous table must pass the band end within the solver range.

    General (Lossy) truncates at the global upper frequency. Fewer modes than
    requested are admissible only when an actually solved mode is above the
    acceptance window; an incomplete in-window table is never an empty band.
    """
    numbers = {m.mode_number for m in native}
    ordered = sorted(native, key=lambda m: m.mode_number)
    return (0 < len(native) <= mode_count and numbers == set(range(1, len(native) + 1))
            and all(a.frequency_hz <= b.frequency_hz for a, b in zip(ordered, ordered[1:]))
            and max(m.frequency_hz for m in native) > upper_mhz * 1e6)


def fixed_window_table_valid(native: Any, mode_count: int, lower_mhz: float, upper_mhz: float) -> bool:
    """Validate returned evidence under a user-accepted finite-mode window.

    Frequencies are in Hz. This checks table integrity, NOT spectral completeness.
    Empty/missing results must never be interpreted as zero transverse impedance.
    """
    ordered = sorted(native, key=lambda m: m.mode_number)
    return (0 < len(native) <= mode_count
            and {m.mode_number for m in native} == set(range(1, len(native) + 1))
            and all(a.frequency_hz <= b.frequency_hz for a, b in zip(ordered, ordered[1:]))
            and all(lower_mhz * 1e6 - 1. <= m.frequency_hz <= upper_mhz * 1e6 + 1. for m in native))


def result_fingerprint(project: Path) -> dict[str, str]:
    """Fingerprint saved native result files, not only the small .cst container."""
    root = project.with_suffix("")
    files = [project, root / "Model/Parameters.json"]
    files += sorted(p for p in (root / "Result").rglob("*") if p.is_file()
                    and p.suffix.lower() not in {".lok", ".lock"})
    return {str(p.relative_to(project.parent)): digest(p) for p in files if p.is_file()}


def verify_solved(path: Path, directory: Path) -> dict[str, Any]:
    """Reject result-folder replacement and altered saved geometry on recovery."""
    evidence = json.loads((directory / "solved.json").read_text(encoding="utf-8"))
    if digest(path) != evidence["project_sha256"]:
        raise ValueError("Saved solved project fingerprint changed")
    if "result_fingerprint" in evidence and result_fingerprint(path) != evidence["result_fingerprint"]:
        raise ValueError("Saved result-folder fingerprint changed")
    return evidence


class CSTEvaluator:
    """Evaluate or resume one geometry, with a fresh owned copy for each attempt."""

    def __init__(self, config: Any, template: Path):
        self.config, self.template = config, template
        self.info = metadata(template)
        self.pp = postprocess_config(config, self.info)

    @contextmanager
    def _project(self, path: Path, directory: Path, phase: str) -> Iterator[Any]:
        # Lazy imports: config, offline analysis and all pure numerical code need no CST.
        from cst_optimization.core.connection import CSTConnection
        project, pid, connection = None, None, None
        connect_started = False
        session = {"session_id": str(uuid4()), "pid": None,
                   "project": str(path.resolve()), "phase": "opening"}
        session_path = directory / f"{phase}_session.json"
        # Persist BEFORE any operation that can create a DesignEnvironment.
        atomic_json(session_path, session)
        try:
            connection = CSTConnection(library_path=self.config.paths.cst_library_path, mode="new")
            connect_started = True
            connection.connect()
            pid = connection.pid
            session.update(pid=pid, phase="active")
            atomic_json(session_path, session)
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise EvaluationFailure("Owned CST PID could not be recorded", "cleanup_failed")
            project = connection.open_project(str(path))
            project.activate()
            if Path(project.filename).resolve() != path.resolve():
                raise EvaluationFailure("CST opened an unexpected project", "ownership_failed")
            yield project
        finally:
            # A failed connect may nevertheless have created its own DE and PID.
            # Recover only this connection's PID; never infer one from other processes.
            if (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0) and connection is not None and connect_started:
                try:
                    recovered_pid = connection.pid
                except Exception:
                    recovered_pid = None
                if isinstance(recovered_pid, int) and not isinstance(recovered_pid, bool) and recovered_pid > 0:
                    pid = recovered_pid
                    session.update(pid=pid, phase="cleanup")
                    try:
                        atomic_json(session_path, session)
                    except Exception:
                        LOG.exception("Could not persist recovered owned PID; still attempting targeted cleanup")
            close_error = None
            try:
                if project is not None:
                    project.close(save=False)
            except BaseException as exc:
                close_error = exc
            finally:
                # This runs even if project.close raises. Never use generic close.
                result = {"success": False, "exit_verified": False}
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and connection is not None:
                    try:
                        result = connection.close_targeted(pid_override=pid)
                    except Exception as exc:
                        result["error"] = f"{type(exc).__name__}: {exc}"
                    # Shared close_targeted uses tasklist. Independently verify exact
                    # PID absence before issuing a trustworthy cleanup certificate.
                    try:
                        pid_state = query_pid(pid)
                    except Exception:
                        pid_state = "unknown"
                    result["pid_state"] = pid_state
                    result["exit_verified"] = pid_state == "absent"
                    result["success"] = bool(result.get("success")) and pid_state == "absent"
                elif not connect_started:
                    result.update(success=True, no_session_started=True)
                else:
                    result["error"] = "Connection started without a recorded owned PID"
                result.update(session_id=session["session_id"], pid=pid, project=session["project"])
                if close_error is not None:
                    result["project_close_error"] = f"{type(close_error).__name__}: {close_error}"
                atomic_json(directory / f"{phase}_cleanup.json", result)
            if not result.get("success"):
                raise EvaluationFailure(f"Owned session cleanup failed: {result}", "cleanup_failed")
            if close_error is not None:
                if isinstance(close_error, (KeyboardInterrupt, SystemExit)):
                    raise close_error
                raise EvaluationFailure(f"Project close failed; owned process cleanup completed: {close_error}", "project_close_failed") from close_error

    def _prepare(self, parameters: dict[str, float], directory: Path) -> Path:
        path, _ = copy_verified_project(self.template, directory / "project")
        mapping = {p.cst_name or p.name: parameters[p.name] /
                   (LENGTH_TO_MM[self.info["length_unit"]] if p.unit == "mm" else 1.)
                   for p in self.config.parameters}
        try:
            with self._project(path, directory, "prepare") as project:
                if not project.update_parameters(mapping, use_full_rebuild=True):
                    raise EvaluationFailure("CST rejected parameter update/full rebuild", "geometry_failed")
                if not project.save(include_results=False):
                    raise EvaluationFailure("Could not save result-free candidate", "save_failed")
        except EvaluationFailure:
            raise
        except Exception as exc:
            transient = any(s in str(exc).lower() for s in ("rpc", "disconnected", "connection lost"))
            raise EvaluationFailure(str(exc), "transient_failed" if transient else "geometry_failed", transient) from exc
        actual = read_baseline(path, self.config)
        if any(not math.isclose(actual[k], v, rel_tol=1e-10, abs_tol=1e-8) for k, v in parameters.items()):
            raise EvaluationFailure("Saved candidate parameters do not match requested geometry", "geometry_failed")
        return path

    def _solve(self, path: Path, directory: Path, count: int, reserve: Callable) -> None:
        from cst_optimization.core.solver import SolverRunner
        with self._project(path, directory, "solve") as project:
            project.execute_vba(solver_vba(self.config, self.info["frequency_unit"], count),
                                header="WF5 eigenmode frequency coverage", timeout=180.)
            if not project.save(include_results=False):
                raise EvaluationFailure("Failed to save configured solver", "save_failed")
            log = path.with_suffix("") / "Result/Model.log"
            before = digest(log) if log.exists() else None
            log_before = log.read_text(errors="replace") if log.exists() else ""
            try:
                messages_before = str(project.get_messages())
            except Exception:
                messages_before = ""
            # Persist reservation BEFORE calling the expensive synchronous solver.
            number = reserve(str(directory))
            atomic_json(directory / "solve_started.json", {"budget_number": number, "mode_count": count,
                                                           "started_ns": time.time_ns()})
            result = SolverRunner(timeout_s=self.config.solver.timeout_s,
                                  settle_s=self.config.solver.settle_s).run(project)
            atomic_json(directory / "solver_result.json", asdict(result))
            try:
                messages = str(project.get_messages())
            except Exception as exc:
                messages = f"message capture unavailable: {exc}"
            (directory / "messages.txt").write_text(messages, encoding="utf-8")
            if not result.success:
                raise EvaluationFailure(result.error_message or "Solver failed",
                                        result.error_type or "solver_failed", result.error_type == "com")
            fresh_log = log.exists() and digest(log) != before
            logtext = log.read_text(errors="replace") if fresh_log else ""
            if log_before and logtext.startswith(log_before):
                logtext = logtext[len(log_before):]
            new_messages = messages[len(messages_before):] if messages.startswith(messages_before) else (
                messages if "eigenmode solver successful" not in messages_before.lower() else "")
            if "eigenmode solver successful" not in (new_messages + "\n" + logtext).lower():
                raise EvaluationFailure("No explicit Eigenmode solver successful evidence", "solver_failed")
            if not project.save(include_results=True):
                raise EvaluationFailure("Solved project could not be saved", "save_failed")
        evidence = {"project_sha256": digest(path), "mode_count": count,
                    "result_fingerprint": result_fingerprint(path),
                    "messages_sha256": digest(directory / "messages.txt")}
        if log.exists():
            evidence["log_sha256"] = digest(log)
        atomic_json(directory / "solved.json", evidence)

    def __call__(self, parameters: dict[str, float], evaluation_dir: Path, reserve: Callable) -> dict[str, Any]:
        """Resume saved fields without solving, otherwise run bounded fresh attempts."""
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        state_path = evaluation_dir / "evaluation.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else dict(
            mode_count=self.config.solver.mode_count, coverage_retries=0, transient_retries=0,
            attempts=0, current=None, phase="new", parameters=parameters)
        if state["parameters"] != parameters:
            raise EvaluationFailure("Evaluation identity differs from saved geometry")
        # The campaign's Python lock does not cover a CST child surviving a crash.
        # Gate before reusing a result, overwriting session markers, or launching CST.
        ensure_sessions_inactive(evaluation_dir)
        if state["phase"] == "complete":
            if state.get("project"):
                verify_solved(Path(state["project"]), Path(state["current"]))
            return state["result"]
        # Close the crash window between saved solve evidence and evaluation journal.
        if state.get("current") and state["phase"] not in {"solved", "postprocess_pending", "coverage_retry"}:
            previous = Path(state["current"])
            proof = previous / "solved.json"
            projects = list((previous / "project").glob("*.cst"))
            if proof.is_file() and len(projects) == 1:
                verify_solved(projects[0], previous)
                state.update(project=str(projects[0]), phase="solved")
                atomic_json(state_path, state)
        while True:
            if state["phase"] not in {"solved", "postprocess_pending"}:
                directory = evaluation_dir / f"attempt_{state['attempts']:03d}"
                state["attempts"] += 1
                state.update(current=str(directory), phase="prepare")
                atomic_json(state_path, state)
                try:
                    path = self._prepare(parameters, directory)
                    try:
                        self._solve(path, directory, state["mode_count"], reserve)
                    except (BudgetExhausted, EvaluationFailure, KeyboardInterrupt):
                        raise
                    except Exception as exc:
                        transient = any(s in str(exc).lower() for s in ("rpc", "disconnected", "connection lost"))
                        raise EvaluationFailure(str(exc), "transient_failed" if transient else "solver_failed", transient) from exc
                    state.update(project=str(path), phase="solved")
                    atomic_json(state_path, state)
                except BudgetExhausted:
                    raise
                except EvaluationFailure as exc:
                    state.update(phase="failed", error=str(exc), category=exc.category)
                    atomic_json(state_path, state)
                    if exc.transient and state["transient_retries"] < 1:
                        state["transient_retries"] += 1
                        atomic_json(state_path, state)
                        continue
                    return {"status": exc.category, "error": str(exc), "worst": None}
            directory, path = Path(state["current"]), Path(state["project"])
            try:
                # Refuse stale/tampered result-bearing projects on postprocessing recovery.
                evidence = verify_solved(path, directory)
                native = read_native_modes(path, self.pp)
                if any(m.frequency_hz < self.config.solver.target_frequency_mhz * 1e6 - 1. for m in native):
                    raise ValueError("Native modes violate the configured lower frequency limit")
                atomic_json(directory / "native_modes.json", [m.to_dict() for m in native])
                fixed = self.config.solver.coverage_policy == "fixed_window"
                coverage = dict(coverage_policy=self.config.solver.coverage_policy,
                                coverage_basis="user_accepted_fixed_window" if fixed else "upper_sentinel",
                                coverage_verified=not fixed)
                if fixed:
                    if not fixed_window_table_valid(native, state["mode_count"],
                            self.config.solver.target_frequency_mhz, self.config.solver.upper_frequency_mhz):
                        return dict(status="coverage_failed", error="Invalid or empty fixed-window mode table",
                                    worst=None, **coverage)
                elif not coverage_complete(native, state["mode_count"], self.config.physics.frequency_max_mhz):
                    if state["coverage_retries"] >= self.config.solver.coverage_retries or state["mode_count"] >= self.config.solver.max_mode_count:
                        return {"status": "coverage_failed", "error": "Mode table does not cover upper band boundary", "worst": None}
                    state["mode_count"] = min(self.config.solver.max_mode_count, state["mode_count"] * 2)
                    state["coverage_retries"] += 1
                    state["phase"] = "coverage_retry"
                    atomic_json(state_path, state)
                    continue
                # Empty objective band is accepted only after a full lower-bound coverage proof.
                band = (self.config.physics.frequency_min_mhz, self.config.physics.frequency_max_mhz)
                selected = [m for m in native if band[0] * 1e6 <= m.frequency_hz <= band[1] * 1e6]
                if not selected:
                    if fixed:
                        return dict(status="coverage_failed", error="Fixed-window results cannot establish an empty objective band",
                                    worst=None, **coverage)
                    data = {"native_modes": [m.to_dict() for m in native], "modes": [],
                            "coverage_complete": True, "empty_band": True}
                    result = dict(status="valid", worst=0., project=str(path), modes=data)
                else:
                    index = len(list(directory.glob("postprocess_*")))
                    out = directory / f"postprocess_{index:03d}"
                    with self._project(path, directory, "postprocess") as project:
                        processed = collect_and_analyze(project, path, out, self.pp, band, native_modes=native)
                    evidence["result_fingerprint"] = result_fingerprint(path)
                    atomic_json(directory / "solved.json", evidence)
                    data = processed.to_dict()
                    atomic_json(directory / "latest_analysis.json", data)
                    if not processed.quality_ok:
                        reasons = json.dumps(data, ensure_ascii=False)
                        retryable = any(m.metrics is None for m in processed.modes)
                        state.update(phase="postprocess_pending" if retryable else "invalid", error=reasons)
                        atomic_json(state_path, state)
                        return dict(status="postprocess_failed" if retryable else "quality_failed",
                                    worst=None, error=reasons, project=str(path), modes=data, **coverage)
                    result = dict(status="valid", worst=float(processed.worst_impedance_ohm_per_m),
                                  project=str(path), modes=data)
                result.update(coverage)
                state.update(phase="complete", result=result)
                # Postprocessing may write native QFactor results on the owned copy.
                evidence["result_fingerprint"] = result_fingerprint(path)
                atomic_json(directory / "solved.json", evidence)
                atomic_json(state_path, state)
                return result
            except (BudgetExhausted, KeyboardInterrupt):
                raise
            except EvaluationFailure as exc:
                if exc.category == "cleanup_failed":
                    return dict(status="cleanup_failed", worst=None, error=str(exc), project=str(path))
                raise
            except Exception as exc:
                state.update(phase="postprocess_pending", error=f"{type(exc).__name__}: {exc}")
                atomic_json(state_path, state)
                return dict(status="postprocess_failed", worst=None, error=state["error"], project=str(path))
