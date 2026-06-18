"""Recovery workflow evaluator — two-pass CST solve for WF3.

Extracted from `workflows/rfgun_sao/evaluator.py` in Phase 11.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

class RecoveryWorkflowEvaluator:
    """Single-project two-pass evaluator for workflow 3."""

    def __init__(
        self,
        connection: CSTConnection,
        cst_path: str,
        parameter_set: ParameterSet,
        optimize_metrics: list[MetricSpec],
        threshold_metrics: list[MetricSpec],
        report_metrics: list[MetricSpec],
        solver_runner: SolverRunner,
        message_logger: MessageLogger,
        frequency_gate: FrequencyGate,
        calibration_guess_ghz: float,
        warm_start: np.ndarray | None = None,
        opt_logger: Any | None = None,
        record_dir: str = "",
        s11_depth_threshold_db: float = -1.0,
        mode_spacing_ghz: float = 0.04,
        library_path: str = "",
        inter_pass_recovery: bool = False,
    ) -> None:
        self._conn = connection
        self._cst_path = cst_path
        self._params = parameter_set
        self._optimize_metrics = list(optimize_metrics)
        self._threshold_metrics = list(threshold_metrics)
        self._report_metrics = list(report_metrics)
        self._solver = solver_runner
        self._msg = message_logger
        self._gate = frequency_gate
        self._f_guess_ghz = float(calibration_guess_ghz)
        self._warm_start = None if warm_start is None else np.asarray(warm_start, dtype=float)
        self._opt_logger = opt_logger
        self._project_dir = os.path.splitext(self._cst_path)[0]
        self._record_dir = record_dir or os.getcwd()
        os.makedirs(self._record_dir, exist_ok=True)
        self._record_path = os.path.join(self._record_dir, "evaluation_records.jsonl")
        self._all_metrics = (
            self._optimize_metrics + self._threshold_metrics + self._report_metrics
        )
        self._metric_by_name = {m.name: m for m in self._all_metrics}
        self._last_result: EvaluationResult | None = None
        self._last_raw_metrics: dict[str, float] = {}
        self._last_penalties: dict[str, float] = {}
        self._n_objectives = len(self._optimize_metrics) + len(self._threshold_metrics)
        self._s11_depth_threshold_db = float(s11_depth_threshold_db)
        self._mode_spacing_ghz = float(mode_spacing_ghz)
        self._library_path = library_path
        self._inter_pass_recovery = inter_pass_recovery

    @property
    def warm_start(self) -> np.ndarray | None:
        return None if self._warm_start is None else self._warm_start.copy()

    @property
    def parameter_names(self) -> list[str]:
        return self._params.names

    @property
    def objective_names(self) -> list[str]:
        return [m.output_name for m in (self._optimize_metrics + self._threshold_metrics)]

    @property
    def report_metric_names(self) -> list[str]:
        return [m.output_name for m in self._report_metrics]

    @property
    def last_result(self) -> EvaluationResult | None:
        return self._last_result

    @property
    def last_raw_metrics(self) -> dict[str, float]:
        return dict(self._last_raw_metrics)

    @property
    def last_penalties(self) -> dict[str, float]:
        return dict(self._last_penalties)

    @property
    def record_path(self) -> str:
        return self._record_path

    @property
    def logged_evaluations(self) -> int:
        if self._opt_logger is None:
            return 0
        try:
            return int(self._opt_logger.n_evaluations)
        except Exception:
            return 0

    def evaluate(self, params: np.ndarray, iteration: int = 0) -> EvaluationResult:
        """Evaluate one physical parameter vector."""
        x_phys = np.asarray(params, dtype=float)
        x_phys = self._params.validate(x_phys)
        param_dict = self._params.to_dict(x_phys)
        vals = ", ".join(f"{k}={v:.4f}" for k, v in param_dict.items())
        print(f"[iter {iteration}] {vals}", flush=True)
        _logger.info("Evaluation %d started: %s", iteration, vals)

        t0 = time.perf_counter()
        project: CSTProject | None = None
        reader: ResultReader | None = None

        raw_metrics: dict[str, float] = {}
        objective_values: dict[str, float] = {}
        penalty_values: dict[str, float] = {}
        pass_log: dict[str, Any] = {}
        result = EvaluationResult(
            status=EvaluationStatus.UNKNOWN_ERROR,
            raw_metrics=raw_metrics,
            objective_values=objective_values,
            penalty_values=penalty_values,
            pass_log=pass_log,
        )

        try:
            _logger.info("Opening CST project: %s", self._cst_path)
            project = self._conn.open_project(self._cst_path)
            ok = project.update_parameters(param_dict, use_full_rebuild=True)
            if not ok:
                raise RuntimeError("Parameter update failed")
            _logger.info("Parameters updated and rebuild completed for iteration %d", iteration)

            self._msg.capture(project)
            self._msg.clear()

            # Pass 1: calibration solve at guessed f_data
            _logger.info("Starting calibration solve for iteration %d", iteration)
            f0_ghz, cal_error, cal_info = self._calibration_solve(project, param_dict, iteration)
            pass_log["calibration"] = cal_info
            if not np.isfinite(f0_ghz):
                result.error = cal_error or "Calibration failed"
                _logger.warning("Calibration failed at iteration %d: %s", iteration, result.error)
                if "S11 dip too shallow" in str(cal_error):
                    result.status = EvaluationStatus.PHYSICS_INVALID
                elif "COM connection lost" in str(cal_error):
                    result.status = EvaluationStatus.COM_LOST
                else:
                    result.status = EvaluationStatus.SOLVER_FAILED
                return result

            result.f0_ghz = float(f0_ghz)
            raw_metrics["resonant_freq"] = float(f0_ghz)
            _logger.info(
                "Calibration solve finished for iteration %d: f0=%.6f GHz",
                iteration, f0_ghz,
            )

            gate_passed = (not self._gate.enabled) or self._gate.accepts(f0_ghz)
            result.frequency_gate_passed = gate_passed
            if not gate_passed:
                delta_mhz = (f0_ghz - self._gate.target_ghz) * 1e3
                result.error = (
                    f"Frequency gate rejected candidate: "
                    f"f0={f0_ghz:.6f} GHz, delta={delta_mhz:+.2f} MHz"
                )
                result.status = EvaluationStatus.FREQUENCY_GATE
                _logger.warning("Frequency gate rejected iteration %d: %s", iteration, result.error)
                return result

            # ── Inter-pass Tier-3 recovery ───────────────────────────
            if self._inter_pass_recovery:
                _logger.info(
                    "Inter-pass Tier-3 reset for iteration %d", iteration,
                )
                try:
                    project.close(save=True)
                except Exception:
                    pass
                self._do_inter_pass_reset()
                project = self._conn.open_project(self._cst_path)
                project.update_parameters(param_dict, use_full_rebuild=True)

            # Pass 2: measurement solve with corrected f_data
            _logger.info(
                "Starting measurement solve for iteration %d with corrected f_data=%.6f GHz",
                iteration, f0_ghz,
            )
            meas = self._measurement_solve(project, param_dict, f0_ghz, iteration)
            pass_log["measurement"] = meas.get("solver_meta", {})
            meas_ok = meas["solver_ok"]
            result.error = meas["error"]
            raw_metrics.update(meas["raw_metrics"])

            if not meas_ok:
                if "COM" in str(result.error):
                    result.status = EvaluationStatus.COM_LOST
                else:
                    result.status = EvaluationStatus.SOLVER_FAILED
                _logger.warning("Measurement solve failed at iteration %d: %s", iteration, result.error)
                return result

            reader = ResultReader(project.filename, allow_interactive=True)
            # Evaluate explicit objective-backed metrics from the saved file
            raw_metrics.update(self._evaluate_configured_metrics(reader))

            # Build objective vectors
            for metric in self._optimize_metrics:
                val = raw_metrics.get(metric.name, np.nan)
                objective_values[metric.output_name] = val
                if np.isfinite(val):
                    if metric.objective is not None:
                        penalty_values[metric.output_name] = metric.objective.mode.compute(float(val))
                    else:
                        penalty_values[metric.output_name] = float(val)
                else:
                    penalty_values[metric.output_name] = 1.0

            for metric in self._threshold_metrics:
                val = raw_metrics.get(metric.name, np.nan)
                objective_values[metric.output_name] = val
                penalty_values[metric.output_name] = self._threshold_penalty(metric, val)

            result.status = EvaluationStatus.SUCCESS
            _logger.info(
                "Iteration %d completed successfully. Metrics: %s",
                iteration,
                ", ".join(
                    f"{k}={v:.6g}" for k, v in sorted(raw_metrics.items()) if np.isfinite(v)
                ),
            )
            return result

        except Exception as exc:
            result.error = str(exc)
            err_str = str(exc).lower()
            if "com" in err_str or "designenvironment" in err_str:
                result.status = EvaluationStatus.COM_LOST
            _logger.error("Workflow-3 evaluation failed: %s", exc, exc_info=True)
            return result

        finally:
            result.elapsed_s = time.perf_counter() - t0
            self._last_result = result
            self._last_raw_metrics = dict(raw_metrics)
            self._last_penalties = dict(penalty_values)
            self._append_record(iteration, x_phys, result)
            if self._opt_logger is not None:
                self._log_evaluation(iteration, x_phys, result)
            if project is not None:
                try:
                    project.close(save=True)
                except Exception:
                    _logger.warning("Failed to close workflow-3 project", exc_info=True)

    def evaluate_objectives(self, params: np.ndarray, iteration: int = 0) -> np.ndarray:
        """Return the optimisation objective vector for SAEA."""
        result = self.evaluate(params, iteration=iteration)
        if result.status != EvaluationStatus.SUCCESS:
            return np.full(self._n_objectives, 1.0)
        return np.array(
            [
                result.penalty_values.get(name, 1.0)
                for name in self.objective_names
            ],
            dtype=float,
        )

    def scalar_evaluator(
        self,
        params: np.ndarray,
        iteration: int = 0,
        weights: np.ndarray | None = None,
    ) -> float:
        """Return a scalar aggregate for SAO."""
        vec = self.evaluate_objectives(params, iteration=iteration)
        if weights is None:
            weights = np.ones(len(vec), dtype=float)
        w = np.asarray(weights, dtype=float)
        w = w / np.sum(w)
        return float(np.dot(vec, w))

    def close(self, force: bool = False) -> None:
        try:
            self._conn.close(force=force)
        finally:
            remove_lock_file(self._project_dir)
        rh = getattr(self, "_retry_handler", None)
        if rh is not None:
            try:
                rh.close_all(force=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal: CST two-pass solve
    # ------------------------------------------------------------------

    def _do_inter_pass_reset(self) -> None:
        """Graceful reset between calibration and measurement passes.

        Normal close (no force kill), remove result folder, reconnect —
        preserving the license server (cstd.exe) and avoiding Qt6 crashes.
        """
        import time as _time
        from cst_optimization.core.cleanup import (
            kill_all_cst_processes, remove_lock_file, remove_result_folder,
        )

        try:
            self._conn.close(force=False)
        except Exception:
            pass

        _time.sleep(5.0)

        kill_all_cst_processes()
        remove_result_folder(self._cst_path)
        remove_lock_file(os.path.dirname(self._cst_path))

        _time.sleep(5.0)

        self._conn = CSTConnection(library_path=self._library_path, mode="new")
        self._conn.connect()
        self._conn.set_quiet_mode(True)
        _logger.info("Inter-pass reset: connected to new CST DE, PID=%s", self._conn.pid)

    def _calibration_solve(
        self,
        project: CSTProject,
        param_dict: dict[str, float],
        iteration: int,
    ) -> tuple[float, str, dict[str, Any]]:
        params = dict(param_dict)
        params["f_data"] = self._f_guess_ghz
        project.update_parameters(params)
        solver_result = self._solver.run(project)
        self._msg.capture(project)
        msg_path = self._msg.write(label="calibration", iteration=iteration)
        info = {
            "success": bool(solver_result.success),
            "error_type": solver_result.error_type,
            "error_message": solver_result.error_message,
            "elapsed_s": solver_result.elapsed_s,
            "mesh_cells": solver_result.mesh_cells,
            "message_log": msg_path,
        }
        if not solver_result.success and solver_result.error_type == "com":
            return np.nan, "COM connection lost during calibration", info
        project.save()
        try:
            project.model3d.abort_solver()
        except Exception:
            pass

        reader = ResultReader(project.filename, allow_interactive=True)
        s11 = reader.get_s_parameter()
        mag = np.abs(s11.s_complex)

        # ── S11 depth gate: reject before wasting effort on shallow dips ──
        gamma_min = float(np.min(mag))
        s11_min_db = float(20.0 * np.log10(max(gamma_min, 1e-12)))
        info["s11_min_db"] = s11_min_db

        if s11_min_db > self._s11_depth_threshold_db:
            _logger.warning(
                "S11 dip too shallow at iteration %d: |S11|_min=%.2f dB (threshold %.1f dB)",
                iteration, s11_min_db, self._s11_depth_threshold_db,
            )
            return (
                np.nan,
                f"S11 dip too shallow ({s11_min_db:.1f} dB > {self._s11_depth_threshold_db:.1f} dB)",
                info,
            )

        # ── Resonance detection with fallback chain ──
        try:
            f0, _, _, _ = half_power_bandwidth(
                s11.frequencies, mag, target_freq=self._f_guess_ghz
            )
        except Exception as exc_target:
            try:
                f0, _, _, _ = half_power_bandwidth(s11.frequencies, mag)
            except Exception as exc_full:
                _logger.warning(
                    "Half-power bandwidth failed at iteration %d; "
                    "falling back to dip minimum. target-window error=%s, "
                    "full-range error=%s",
                    iteration, exc_target, exc_full,
                )
                f0, _ = resonance_from_dip(
                    s11.frequencies, mag, target_freq=self._f_guess_ghz,
                )
                info["resonance_fallback"] = "dip_minimum"

        if not np.isfinite(f0):
            return np.nan, "Invalid calibrated resonance", info
        info["f0_ghz"] = float(f0)

        # ── Multi-dip mode ambiguity detection ──
        try:
            dip_indices, _ = find_peaks(-mag, prominence=0.01)
            if len(dip_indices) > 1:
                dip_freqs = s11.frequencies[dip_indices]
                dip_mags = mag[dip_indices]
                nearby_mask = np.abs(dip_freqs - f0) < self._mode_spacing_ghz
                nearby_freqs = dip_freqs[nearby_mask]
                if len(nearby_freqs) > 1:
                    nearby_mags = dip_mags[nearby_mask]
                    info["mode_ambiguous"] = True
                    info["nearby_dips"] = [
                        {"freq": float(f), "mag": float(m)}
                        for f, m in zip(nearby_freqs, nearby_mags)
                    ]
                    deepest_idx = int(np.argmin(nearby_mags))
                    info["deepest_dip_is_candidate"] = bool(
                        abs(nearby_freqs[deepest_idx] - f0) < 1e-4
                    )
                    _logger.info(
                        "Multi-dip detected near f0=%.4f GHz: %d dips within %.3f GHz; "
                        "deepest_dip_is_candidate=%s",
                        f0, len(nearby_freqs), self._mode_spacing_ghz,
                        info["deepest_dip_is_candidate"],
                    )
        except Exception:
            pass  # mode detection is diagnostic-only; never fail calibration

        return float(f0), "", info

    def _measurement_solve(
        self,
        project: CSTProject,
        param_dict: dict[str, float],
        f0_ghz: float,
        iteration: int,
    ) -> dict[str, Any]:
        params = dict(param_dict)
        params["f_data"] = float(f0_ghz)
        project.update_parameters(params)
        solver_result = self._solver.run(project)
        self._msg.capture(project)
        msg_path = self._msg.write(label="measurement", iteration=iteration)
        if not solver_result.success and solver_result.error_type == "com":
            return {
                "solver_ok": False,
                "error": "COM connection lost during measurement",
                "raw_metrics": {},
                "solver_meta": {
                    "success": False,
                    "error_type": solver_result.error_type,
                    "error_message": solver_result.error_message,
                    "elapsed_s": solver_result.elapsed_s,
                    "mesh_cells": solver_result.mesh_cells,
                    "message_log": msg_path,
                },
            }

        project.save()
        raw_metrics: dict[str, float] = {"resonant_freq": float(f0_ghz)}

        reader = ResultReader(project.filename, allow_interactive=True)
        s11 = reader.get_s_parameter()
        e0 = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
        bundle = ResultBundle(
            s_parameters={"S1,1": s11},
            scalars={"MaxE_Z0": e0},
        )

        raw_metrics["coupling_beta"] = float(CouplingBeta().compute(bundle))
        raw_metrics["p_input"] = float(InputPower(target_e_acc_vm=200e6).compute(bundle))
        raw_metrics["e_peak"] = float(PeakSurfaceField().compute(bundle))
        raw_metrics["q0"] = float(IntrinsicQ().compute(bundle))
        raw_metrics["q_loaded"] = float(LoadedQ().compute(bundle))
        raw_metrics["s11_db"] = float(
            20.0 * np.log10(max(MinS11().compute(bundle), 1e-15))
        )

        # Field-dependent diagnostics
        self._cache_field_exports(project.filename, iteration)
        try:
            raw_metrics["field_flatness"] = self._compute_field_flatness(reader)
        except Exception:
            pass
        try:
            raw_metrics["max_modified_poynting"] = self._compute_modified_poynting(
                project.filename, raw_metrics["e_peak"], iteration
            )
        except Exception:
            pass
        try:
            raw_metrics["pulsed_heating"] = self._compute_pulsed_heating(
                project.filename, raw_metrics["e_peak"], iteration
            )
        except Exception:
            pass

        ok = bool(solver_result.success or raw_metrics)
        return {
            "solver_ok": ok,
            "error": "",
            "raw_metrics": raw_metrics,
            "solver_meta": {
                "success": bool(solver_result.success),
                "error_type": solver_result.error_type,
                "error_message": solver_result.error_message,
                "elapsed_s": solver_result.elapsed_s,
                "mesh_cells": solver_result.mesh_cells,
                "message_log": msg_path,
            },
        }

    def _evaluate_configured_metrics(self, reader: ResultReader) -> dict[str, float]:
        raw_values: dict[str, float] = {}
        for metric in self._all_metrics:
            if metric.objective is None:
                continue
            saved = getattr(metric.objective, "_reader_factory", None)
            metric.objective._reader_factory = lambda r=reader: r
            try:
                raw_values[metric.name] = float(metric.objective.raw_value())
            except Exception:
                continue
            finally:
                metric.objective._reader_factory = saved
        return raw_values

    def _threshold_penalty(self, metric: MetricSpec, value: float) -> float:
        if not np.isfinite(value):
            return 1.0
        threshold = 0.0 if metric.threshold is None else float(metric.threshold)
        sigma = 1.0 if metric.sigma is None else max(float(metric.sigma), 1e-12)

        if metric.direction == "greater_than":
            if value >= threshold:
                return 0.0
            return float(1.0 - np.exp(-(threshold - value) / sigma))

        if value <= threshold:
            return 0.0
        return float(1.0 - np.exp(-(value - threshold) / sigma))

    def _compute_field_flatness(self, reader: ResultReader) -> float:
        e0 = reader.get_scalar(reader.TREEPATH_MAX_E_Z0).value
        e1 = reader.get_scalar(reader.TREEPATH_MAX_E_Z1).value
        e2 = reader.get_scalar(reader.TREEPATH_MAX_E_Z2).value
        e_max = max(e0, e1, e2)
        e_min = min(e0, e1, e2)
        if e_max <= 0:
            raise ValueError("Invalid field-flatness inputs")
        return float(1.0 - e_min / e_max)

    def _compute_modified_poynting(
        self,
        project_path: str,
        e_peak_sim: float,
        iteration: int,
    ) -> float:
        prj_dir = os.path.splitext(project_path)[0]
        cache_dir = os.path.join(
            os.path.dirname(prj_dir), "Results", "fields", f"iter_{iteration:04d}"
        )
        e_file, h_file = discover_field_files(cache_dir)
        if not e_file or not h_file:
            e_file, h_file = discover_field_files(prj_dir)
        if not e_file or not h_file:
            raise FileNotFoundError("Field exports not found for modified Poynting")
        cfg = self._metric_by_name.get("max_modified_poynting")
        obj_params = cfg.obj_params or {} if cfg is not None else {}
        e_target = float(obj_params.get("e_target", 200e6))
        gc = float(obj_params.get("gc", 0.125))
        scale = e_target / max(float(e_peak_sim), 1e-12)
        return float(max_modified_poynting(e_file, h_file, gc=gc, field_scale=scale))

    def _compute_pulsed_heating(
        self,
        project_path: str,
        e_peak_sim: float,
        iteration: int,
    ) -> float:
        prj_dir = os.path.splitext(project_path)[0]
        cache_dir = os.path.join(
            os.path.dirname(prj_dir), "Results", "fields", f"iter_{iteration:04d}"
        )
        _, h_file = discover_field_files(cache_dir)
        if not h_file:
            _, h_file = discover_field_files(prj_dir)
        if not h_file:
            raise FileNotFoundError("H-field export not found for pulsed heating")
        cfg = self._metric_by_name.get("pulsed_heating")
        obj_params = cfg.obj_params or {} if cfg is not None else {}
        h_peak = max_h_from_field_file(h_file)
        return float(
            pulsed_heating_delta_t(
                h_peak_sim=h_peak,
                e_peak_sim=float(e_peak_sim),
                e_target=float(obj_params.get("e_target", 200e6)),
                pulse_width_ns=float(obj_params.get("pulse_width_ns", 300.0)),
                frequency_hz=float(obj_params.get("frequency_hz", 11.424e9)),
                rrr=float(obj_params.get("rrr", 5.5)),
            )
        )

    @staticmethod
    def _cache_field_exports(project_path: str, iteration: int) -> None:
        import glob
        import shutil

        prj_dir = os.path.splitext(project_path)[0]
        src_dir = os.path.join(prj_dir, "Export", "3d")
        if not os.path.isdir(src_dir):
            return
        dst_dir = os.path.join(
            os.path.dirname(prj_dir), "Results", "fields", f"iter_{iteration:04d}"
        )
        os.makedirs(dst_dir, exist_ok=True)
        for pattern in (
            "*e-field*", "*E-field*", "*E_Field*",
            "*h-field*", "*H-field*", "*H_Field*",
        ):
            for src in glob.glob(os.path.join(src_dir, pattern)):
                shutil.copy2(src, os.path.join(dst_dir, os.path.basename(src)))

    def _log_evaluation(
        self,
        iteration: int,
        x_phys: np.ndarray,
        result: EvaluationResult,
    ) -> None:
        physics = dict(result.raw_metrics or {})
        physics["frequency_gate_passed"] = float(bool(result.frequency_gate_passed))
        objective_values = dict(result.penalty_values or {})
        self._opt_logger.log_evaluation(
            iteration=iteration,
            x=x_phys,
            param_names=self._params.names,
            physics=physics,
            objective_values=objective_values,
            solver_ok=result.solver_ok,
            error=result.error,
            elapsed_s=result.elapsed_s,
        )

    def _append_record(
        self,
        iteration: int,
        x_phys: np.ndarray,
        result: EvaluationResult,
    ) -> None:
        """Append one JSONL record for post-run inspection."""
        record = {
            "iteration": int(iteration),
            "parameters": {
                name: float(val) for name, val in zip(self._params.names, x_phys)
            },
            "solver_ok": bool(result.solver_ok),
            "status": result.status.value,
            "error": result.error,
            "elapsed_s": float(result.elapsed_s),
            "f0_ghz": (
                None if not np.isfinite(result.f0_ghz) else float(result.f0_ghz)
            ),
            "frequency_gate_passed": bool(result.frequency_gate_passed),
            "raw_metrics": result.raw_metrics or {},
            "objective_values": result.objective_values or {},
            "penalty_values": result.penalty_values or {},
            "pass_log": result.pass_log or {},
        }
        try:
            with open(self._record_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        except OSError:
            _logger.warning(
                "Failed to append workflow-3 evaluation record to %s",
                self._record_path,
                exc_info=True,
            )
# ---- cloned from recovery.py's clone_metric_specs ----
def clone_metric_specs(metrics: list[MetricSpec]) -> list[MetricSpec]:
    """Deep-copy metric specs so objectives can be rebound safely."""
    return [copy.deepcopy(m) for m in metrics]
