"""Tolerance sampling runner — CST batch evaluation without optimization.

Reads a tolerance YAML config (nominal values, per-parameter tolerance_abs,
batch_size, min/max_samples), perturbs parameters around nominal via
Monte Carlo sampling, runs CST solves, and writes results into the shared
evaluation database.

Uses ``cst_optimization.evaluation`` for retry, dedup, and persistence.
No optimizer, no GP surrogate — pure sampling.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

from cst_optimization.core.connection import CSTConnection
from cst_optimization.core.project import CSTProject
from cst_optimization.core.results import ResultReader
from cst_optimization.core.solver import SolverRunner
from cst_optimization.evaluation.evaluation_database_schema import (
    ParameterIdentity,
    EvaluationDatabaseRecord,
    RawEvaluationPayload,
    current_schema_version,
)
from cst_optimization.evaluation.evaluation_database_storage import SQLiteEvaluationDatabase, EvaluationDatabaseConfig
from cst_optimization.physics.formulas import (
    half_power_bandwidth, loaded_q_from_bandwidth,
    coupling_beta as _coupling_beta_formula, intrinsic_q0,
)
from cst_optimization.physics.poynting import max_modified_poynting, discover_field_files
from cst_optimization.physics.heating import max_h_from_field_file, pulsed_heating_delta_t

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


@dataclass
class ToleranceParam:
    """One parameter entry from the tolerance config section."""
    name: str
    nominal: float
    tolerance_abs: float
    unit: str = "mm"
    enabled: bool = True
    description: str = ""


@dataclass
class ToleranceConfig:
    """Container for a parsed tolerance YAML section."""
    project_path: str
    library_path: str
    min_samples: int = 30
    max_samples: int = 100
    batch_size: int = 10
    convergence_rtol: float = 0.01
    seed: int = 42
    db_path: str = ""
    output_dir: str = "D:/Results/tolerance"
    parameters: list[ToleranceParam] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.parameters is None:
            self.parameters = []


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_tolerance_config(config_path: str | Path) -> ToleranceConfig:
    """Parse a tolerance YAML file into a ``ToleranceConfig``.

    Accepts either a standalone tolerance config or the ``tolerance:``
    section embedded in ``config/default.yaml``.

    The mandatory ``cst.library_path`` is read from a top-level ``cst:``
    key when present (embedded mode); standalone files must include it
    directly.
    """
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    tol = raw.get("tolerance", raw)  # embedded or standalone
    cst = raw.get("cst", {})

    params = [
        ToleranceParam(
            name=p["name"],
            nominal=float(p["nominal"]),
            tolerance_abs=float(p.get("tolerance_abs", p.get("delta", 0.0))),
            unit=p.get("unit", "mm"),
            enabled=p.get("enabled", True),
            description=p.get("description", ""),
        )
        for p in tol.get("parameters", [])
        if p.get("enabled", True)
    ]

    project_path = tol.get("project_path", tol.get("cst_path", ""))
    library_path = tol.get(
        "library_path",
        cst.get("library_path", r"D:\CST\AMD64\python_cst_libraries"),
    )
    output_dir = tol.get(
        "output_dir",
        os.path.dirname(project_path) if project_path else "D:/Results/tolerance",
    )
    db_path = tol.get("db_path", os.path.join(output_dir, "tolerance_eval.db"))

    return ToleranceConfig(
        project_path=project_path,
        library_path=library_path,
        min_samples=int(tol.get("min_samples", 30)),
        max_samples=int(tol.get("max_samples", 100)),
        batch_size=int(tol.get("batch_size", 10)),
        convergence_rtol=float(tol.get("convergence_rtol", 0.01)),
        seed=int(tol.get("seed", 42)),
        db_path=db_path,
        output_dir=output_dir,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------


class ToleranceSampler:
    """Monte Carlo tolerance evaluator using CST.

    Parameters
    ----------
    config : ToleranceConfig
        Parsed tolerance configuration.
    """

    def __init__(self, config: ToleranceConfig) -> None:
        self._cfg = config
        self._rng = np.random.RandomState(config.seed)
        self._param_names = [p.name for p in config.parameters]
        self._nominals = np.array([p.nominal for p in config.parameters], dtype=float)
        self._tolerances = np.array([p.tolerance_abs for p in config.parameters], dtype=float)

        # Database
        os.makedirs(os.path.dirname(config.db_path) or ".", exist_ok=True)
        db_cfg = EvaluationDatabaseConfig(path=config.db_path, enabled=True)
        self._db = SQLiteEvaluationDatabase(db_cfg)
        self._db.open()

        # CST connection (lazy — created on first sample)
        self._conn: CSTConnection | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, n_samples: int | None = None, recover_only: bool = False) -> int:
        """Run tolerance sampling with auto-recovery of failed records.

        1. Query DB for previously failed parameter combinations → re-run them.
        2. If recover_only=False and still under target, fill with new samples.

        Parameters
        ----------
        n_samples : int or None
            Target sample count.  Defaults to ``cfg.max_samples``.
        recover_only : bool
            If True, only re-run failed records; skip new random samples.

        Returns
        -------
        int
            Number of evaluations written to the database.
        """
        n_target = n_samples or self._cfg.max_samples
        n_target = max(self._cfg.min_samples, n_target)
        n_remaining = n_target
        success_count = 0
        global_idx = 0

        _logger.info(
            "Tolerance sampling: target=%d, batch_size=%d, recover_only=%s",
            n_target, self._cfg.batch_size, recover_only,
        )
        print(f"Tolerance sampling: target {n_target} samples")
        if recover_only:
            print(f"  Mode: RECOVER — only re-running previously failed records")
        print(f"  Project: {self._cfg.project_path}")
        print(f"  Database: {self._cfg.db_path}")
        print(f"  Parameters: {len(self._param_names)}")
        print("-" * 60)

        # ---- Phase 1: Recovery of failed records ---------------------------
        try:
            all_rows = self._db.get_all_records()
        except Exception:
            all_rows = []

        failed_rows = [
            r for r in all_rows
            if r.get("status") not in ("success", None, "")
            and r.get("param_values") is not None
        ]
        n_existing_success = sum(
            1 for r in all_rows if r.get("status") == "success"
        )

        if failed_rows:
            print(f"\nRecovery: {len(failed_rows)} failed record(s) found "
                  f"({n_existing_success} already success).")
            for row in failed_rows:
                global_idx += 1
                try:
                    pv = row["param_values"]
                    x = np.array(pv, dtype=float) if not isinstance(pv, np.ndarray) else pv.astype(float)
                except Exception:
                    print(f"  [skip] bad param_values in row id={row.get('id')}")
                    continue
                self._evaluate_one(global_idx, x, recovery=True)
                success_count += 1
                n_remaining -= 1
            print(f"Recovery complete.")
        else:
            print(f"\nNo failed records ({n_existing_success} existing success).")

        # ---- Phase 2: New random samples to fill target ---------------------
        if recover_only:
            print("Recover-only mode — skipping new random samples.")
            return success_count

        if n_remaining <= 0:
            print("Target already reached — no new random samples needed.")
            return success_count

        n_batches = (n_remaining + self._cfg.batch_size - 1) // self._cfg.batch_size
        print(f"\nNew samples: {n_remaining} in {n_batches} batch(es)")
        for batch_idx in range(n_batches):
            batch_start = batch_idx * self._cfg.batch_size
            batch_end = min(batch_start + self._cfg.batch_size, n_remaining)
            batch_n = batch_end - batch_start

            print(f"\nBatch {batch_idx + 1}/{n_batches} ({batch_n} samples)")

            param_vectors = self._sample_batch(batch_n)
            for i, x in enumerate(param_vectors):
                global_idx += 1
                self._evaluate_one(global_idx, x)
                success_count += 1

        _logger.info("Tolerance sampling complete: %d evaluations", success_count)
        return success_count

    def close(self) -> None:
        """Release CST connection and database."""
        if self._conn is not None:
            try:
                self._conn.close(force=False)
            except Exception:
                pass
            self._conn = None
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _sample_batch(self, n: int) -> list[np.ndarray]:
        """Generate *n* parameter vectors via uniform perturbation."""
        vectors = []
        for _ in range(n):
            offsets = self._rng.uniform(-1, 1, size=len(self._nominals))
            x = self._nominals + offsets * self._tolerances
            vectors.append(x)
        return vectors

    def _get_connection(self) -> CSTConnection:
        """Lazy CST connection — created once per sampler lifetime."""
        if self._conn is None:
            self._conn = CSTConnection(
                library_path=self._cfg.library_path, mode="new",
            )
            self._conn.connect()
            self._conn.set_quiet_mode(True)
            _logger.info("CST connection established — PID %s", self._conn.pid)
        return self._conn

    def _evaluate_one(self, index: int, x: np.ndarray, recovery: bool = False) -> None:
        """Run one CST solve and persist to the evaluation database."""
        conn = self._get_connection()
        param_dict = dict(zip(self._param_names, x))
        pid = ParameterIdentity(
            param_names=list(self._param_names),
            values=[float(v) for v in x],
        )

        t_start = time.perf_counter()

        # Build evaluation record
        record = EvaluationDatabaseRecord(
            parameter_identity=pid,
            status="pending",
            retry_count=0,
        )

        project_dir = os.path.splitext(self._cfg.project_path)[0]
        raw_metrics: dict[str, float] = {}
        solver_ok = False
        error = ""

        project = None
        try:
            project = self._get_connection().open_project(self._cfg.project_path)
            ok = project.update_parameters(param_dict, use_full_rebuild=True)
            if not ok:
                raise RuntimeError("Parameter update failed")

            runner = SolverRunner(timeout_s=300, settle_s=2.0)
            solver_result = runner.run(project)

            if not solver_result.success:
                error = f"Solver failed [{solver_result.error_type}]: {solver_result.error_message or 'unknown'}"
                record.status = "solver_failed"
            else:
                try:
                    project.save()
                except Exception:
                    pass

                for _ in range(3):
                    time.sleep(5.0)
                    e_file, _ = discover_field_files(project_dir)
                    if e_file:
                        break

                reader = ResultReader(project.filename, allow_interactive=True)
                s11 = reader.get_s_parameter()
                mag = np.abs(s11.s_complex)

                f0, f1, f2, gamma_min = half_power_bandwidth(
                    s11.frequencies, mag, target_freq=11.424,
                )
                raw_metrics["resonant_freq"] = float(f0)
                coupling = float(_coupling_beta_formula(gamma_min))
                raw_metrics["coupling_beta"] = coupling
                raw_metrics["q0"] = float(intrinsic_q0(
                    loaded_q_from_bandwidth(f0, f1, f2), coupling,
                ))

                e_max = reader.get_scalar(reader.TREEPATH_MAX_E_Z0)
                e_sim = float(e_max.value)
                raw_metrics["peak_e_field"] = e_sim

                try:
                    e1 = reader.get_scalar(reader.TREEPATH_MAX_E_Z1).value
                    e2 = reader.get_scalar(reader.TREEPATH_MAX_E_Z2).value
                    emx = max(e_sim, e1, e2)
                    emn = min(e_sim, e1, e2)
                    raw_metrics["field_flatness"] = 1.0 - emn / emx if emx > 0 else 1.0
                except Exception:
                    raw_metrics["field_flatness"] = np.nan

                e_file, h_file = discover_field_files(project_dir)
                if e_file and h_file and e_sim > 0:
                    scale = 200e6 / e_sim
                    raw_metrics["max_modified_poynting"] = float(
                        max_modified_poynting(e_file, h_file, gc=0.125, field_scale=scale),
                    )
                    h_peak = max_h_from_field_file(h_file)
                    raw_metrics["pulsed_heating"] = float(pulsed_heating_delta_t(
                        h_peak_sim=h_peak, e_peak_sim=e_sim,
                        e_target=200e6, pulse_width_ns=300,
                        frequency_hz=11.424e9, rrr=5.5,
                    ))

                solver_ok = True
                record.status = "success"

        except Exception as exc:
            error = str(exc)[:500]
            record.status = "solver_failed"
            _logger.warning("Tolerance eval %d failed: %s", index, error)

        finally:
            if project is not None:
                try:
                    project.close(save=False)
                except Exception:
                    pass

        # Persist to DB — use RawEvaluationPayload so raw_metrics are written
        elapsed = round(time.perf_counter() - t_start, 1)
        record.raw_payload = RawEvaluationPayload(
            raw_metrics=raw_metrics if raw_metrics else None,
            objective_values=raw_metrics if raw_metrics else None,
            gate_results=None,
            diagnostics=None,
        )
        record.source = "rfgun_tolerance.runner"
        record.error_taxonomy = {"error_message": error} if error else None

        try:
            row_id = self._db.insert_final_record(record)
            status = "OK" if solver_ok else "FAIL"
            vals = ", ".join(
                f"{k}={v:.4g}" for k, v in raw_metrics.items()
                if np.isfinite(v)
            ) if raw_metrics else "N/A"
            print(f"  [{index:04d}] {status} ({elapsed:.0f}s) {vals}")
        except Exception as exc:
            _logger.warning("DB write failed for eval %d: %s", index, exc)
