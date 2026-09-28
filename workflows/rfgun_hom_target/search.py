"""Sequential threshold search; failures never become numerical GP targets."""
from __future__ import annotations

from dataclasses import asdict
import logging
import math
from pathlib import Path
from typing import Any, Callable
import warnings

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler

from cst_optimization.parameters.base import ParameterSet, ParamRange
from cst_optimization.parameters.geometry import GeometryParameter
from cst_optimization.optimization.acquisition import ExpectedImprovement
from cst_optimization.optimization.sampling import latin_hypercube_sampling
from cst_optimization.evaluation.evaluation_database_schema import ParameterIdentity
from .geometry import GeometryConstraints
from .storage import BudgetExhausted, CampaignStore, atomic_json
from .physics import ModeSignature, match_mode_signatures
from .session_recovery import SessionRecoveryBlocked
from .reporting import diagnostic_summary, mode_report_lines

LOG = logging.getLogger(__name__)


def objective(worst_ohm_per_m: float, threshold_ohm_per_m: float) -> float:
    """Dimensionless monotone log1p ratio; inputs use circuit transverse Ω/m."""
    if not math.isfinite(worst_ohm_per_m) or worst_ohm_per_m < 0 or threshold_ohm_per_m <= 0:
        raise ValueError("Invalid physical impedance or threshold")
    return math.log1p(worst_ohm_per_m / threshold_ohm_per_m)


class CandidatePlanner:
    """Compose shared normalization, sampling and EI with sklearn GP regression."""

    def __init__(self, config: Any, state: dict[str, Any]):
        self.config = config
        self.state = state
        self.space = ParameterSet([GeometryParameter(p.name, ParamRange(p.lower, p.upper), unit=p.unit)
                                   for p in config.parameters])
        self.geometry = GeometryConstraints(**asdict(config.geometry))
        self.rng = np.random.default_rng(config.search.seed)
        if state.get("rng_state"):
            self.rng.bit_generator.state = state["rng_state"]
        if state.get("radius") is None:
            state["radius"] = config.search.initial_radius

    def key(self, parameters: dict[str, float]) -> str:
        """Stable canonical identity, independent of external CST parameter aliases."""
        return ParameterIdentity(self.space.names, [parameters[n] for n in self.space.names],
                                 precision=8).parameter_key()

    def valid_training_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Exclude every failed, incomplete or unverified observation."""
        rows = [r for r in self.state["records"] if r["status"] == "valid"
                and math.isfinite(r["objective"])]
        x = np.array([[r["parameters"][n] for n in self.space.names] for r in rows])
        return (np.array([self.space.normalize(row) for row in x]) if len(rows) else np.empty((0, len(self.space.names))),
                np.array([r["objective"] for r in rows]))

    def ask(self, baseline: dict[str, float]) -> tuple[dict[str, float], str]:
        """Generate feasible unseen points, mixing local and global exploration."""
        records = self.state["records"]
        seen = {self.key(r["parameters"]) for r in records}
        valid = [r for r in records if r["status"] == "valid"]
        best = min(valid, key=lambda r: r["objective"])["parameters"] if valid else baseline
        center = self.space.normalize(np.array([best[n] for n in self.space.names]))
        initial = len(records) < self.config.search.initial_points
        local_fraction = .5 if initial else self.config.search.local_fraction
        radius = self.state["radius"]
        candidates, sources = [], []
        draws = 0
        while len(candidates) < self.config.search.candidate_pool and draws < self.config.search.candidate_draws:
            size = min(512, self.config.search.candidate_draws - draws)
            unit = latin_hypercube_sampling(np.tile([0., 1.], (len(center), 1)), size,
                                           seed=int(self.rng.integers(0, 2**31 - 1)))
            local = self.rng.random(size) < local_fraction
            lo, hi = np.maximum(0., center - radius), np.minimum(1., center + radius)
            unit[local] = lo + unit[local] * (hi - lo)
            for u, is_local in zip(unit, local):
                physical = self.space.to_dict(self.space.denormalize(u))
                key = self.key(physical)
                if key not in seen and self.geometry.feasible(physical):
                    candidates.append(u)
                    sources.append("local" if is_local else "global")
                    seen.add(key)
                    if len(candidates) == self.config.search.candidate_pool:
                        break
            draws += size
        self.state["rng_state"] = self.rng.bit_generator.state
        if not candidates:
            raise ValueError("No unseen feasible candidates within the configured draw limit")
        pool = np.asarray(candidates)
        x, y = self.valid_training_data()
        index = 0
        if not initial and len(y) >= 3:
            try:
                scaled_y = StandardScaler().fit_transform(y[:, None]).ravel()
                gp = GaussianProcessRegressor(kernel=ConstantKernel(1., (1e-3, 1e3))
                    * Matern(np.ones(len(center)), (.02, 5.), nu=2.5)
                    + WhiteKernel(1e-5, (1e-8, .1)), normalize_y=False,
                    random_state=int(self.rng.integers(0, 2**31 - 1)), n_restarts_optimizer=1)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    gp.fit(x, scaled_y)
                ei = ExpectedImprovement(xi=.01)
                utilities = np.array([ei.evaluate(u, gp, float(scaled_y.min())) for u in pool])
                if not np.isfinite(utilities).all():
                    raise ValueError("Non-finite GP acquisition")
                index = int(np.argmax(utilities))
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                LOG.warning("GP unavailable; using feasible exploration: %s", exc)
        self.state["rng_state"] = self.rng.bit_generator.state
        return self.space.to_dict(self.space.denormalize(pool[index])), sources[index]

    def observe(self, record: dict[str, Any], previous_best: float) -> None:
        """Adapt local radius while retaining global candidates at every step."""
        improved = record["status"] == "valid" and record["objective"] < previous_best - 1e-6
        if improved:
            self.state["improvements"] += 1
            self.state["no_improvement"] = 0
            if self.state["improvements"] >= 2:
                self.state["radius"] = min(self.config.search.max_radius, self.state["radius"] * 1.5)
                self.state["improvements"] = 0
        else:
            self.state["improvements"] = 0
            self.state["no_improvement"] += 1
            if self.state["no_improvement"] >= 4:
                self.state["radius"] = max(self.config.search.min_radius, self.state["radius"] / 2)
                self.state["no_improvement"] = 0


class Campaign:
    """Own ask/evaluate/persist/stop, with injectable CST-free evaluation in tests."""

    def __init__(self, config: Any, store: CampaignStore, evaluator: Callable):
        self.config, self.store, self.evaluator = config, store, evaluator
        self.planner = CandidatePlanner(config, store.state)

    def run(self, baseline: dict[str, float], *, baseline_only: bool = False) -> dict[str, Any]:
        """Run or resume; no confirmation solve is performed after a valid pass."""
        state = self.store.state
        self.store.sync_mirrors()
        if state.get("status") == "runtime_failed":
            return self.report()  # A failed owned-session cleanup requires explicit diagnosis.
        for p in self.config.parameters:
            if p.name not in baseline or not p.lower <= baseline[p.name] <= p.upper:
                raise ValueError(f"Baseline parameter {p.name} missing or outside configured range")
        violations = self.planner.geometry.violations(baseline)
        if violations:
            raise ValueError("Baseline geometry preflight failed: " + "; ".join(violations))
        while True:
            valid = [r for r in state["records"] if r["status"] == "valid"]
            best = min(valid, key=lambda r: r["objective"]) if valid else None
            if best and best["worst"] <= self.config.physics.threshold_ohm_per_m:
                state["status"] = "target_reached"
                break
            if baseline_only and state["records"] and not state["pending"]:
                state["status"] = "baseline_complete" if state["records"][0]["status"] == "valid" else "baseline_failed"
                if state["status"] == "baseline_failed":
                    state["error"] = state["records"][0].get("error", "Baseline evaluation failed")
                break
            if not state["pending"] and state["records"] and state["records"][0]["status"] != "valid":
                state["status"] = "baseline_failed"
                state["error"] = state["records"][0].get("error", "Baseline evaluation failed")
                break
            if not state["pending"] and state["solve_count"] >= self.config.search.max_solves:
                state["status"] = "budget_exhausted"
                break
            if not state["pending"] and len(state["records"]) >= self.config.search.max_candidate_attempts:
                state["status"] = "candidate_limit"
                break
            if not state["pending"]:
                if not state["records"]:
                    parameters, source = dict(baseline), "baseline"
                else:
                    try:
                        parameters, source = self.planner.ask(baseline)
                    except ValueError as exc:
                        state.update(status="no_feasible_candidates", error=str(exc))
                        break
                identity = f"evaluation_{len(state['records']):04d}"
                state["pending"] = dict(id=identity, parameters=parameters, source=source,
                                        attempt_dir=str(self.store.root / "evaluations" / identity))
                self.store.save()
            pending = state["pending"]
            LOG.info("%s (%s), solve budget %d/%d: %s", pending["id"], pending["source"],
                     state["solve_count"], self.config.search.max_solves, pending["parameters"])
            try:
                result = self.evaluator(pending["parameters"], Path(pending["attempt_dir"]), self.store.reserve_solve)
            except SessionRecoveryBlocked as exc:
                state.update(status="orphan_session_pending", error=str(exc))
                break
            except BudgetExhausted:
                state["status"] = "budget_exhausted"
                break
            except KeyboardInterrupt:
                state["status"] = "interrupted"
                self.store.save()
                raise
            # Postprocessing-only recovery remains pending, even at the solve budget.
            if result["status"] == "postprocess_failed":
                state.update(status="postprocess_pending", error=result.get("error", ""))
                break
            record = {**pending, **result}
            if state["records"] and record.get("modes"):
                reference = self._signatures(state["records"][0])
                current = self._signatures(record)
                width_hz = (self.config.physics.frequency_max_mhz - self.config.physics.frequency_min_mhz) * 1e6
                record["mode_matches"] = [m.to_dict() for m in match_mode_signatures(
                    reference, current, frequency_gate_hz=width_hz)]
            if record["status"] == "valid":
                record["objective"] = objective(record["worst"], self.config.physics.threshold_ohm_per_m)
            else:
                record["objective"] = None
            self.planner.observe(record, best["objective"] if best else math.inf)
            self.store.finish(record)
            LOG.info("%s: %s; worst=%s Ω/m", record["id"], record["status"], record.get("worst"))
            if record["status"] == "cleanup_failed":
                state.update(status="runtime_failed", error=record.get("error", "Owned CST cleanup failed"))
                break
        self.store.save()
        return self.report()

    @staticmethod
    def _signatures(record: dict[str, Any]) -> list[ModeSignature]:
        """Supplemental identity evidence; never filters the window objective."""
        signatures = []
        for row in (record.get("modes") or {}).get("modes", []):
            metrics = row.get("metrics") or {}
            if "voltages_real_v" not in metrics:
                continue
            volts = np.asarray(metrics["voltages_real_v"]) + 1j * np.asarray(metrics["voltages_imag_v"])
            if np.linalg.norm(volts) > 0:
                signatures.append(ModeSignature(str(row["mode_number"]), row["frequency_hz"], tuple(volts)))
        return signatures

    def report(self) -> dict[str, Any]:
        """Write self-contained status and best candidate links, never a false pass."""
        state = self.store.state
        valid = [r for r in state["records"] if r["status"] == "valid"]
        best = min(valid, key=lambda r: r["objective"]) if valid else None
        report = dict(status=state["status"], solve_count=state["solve_count"],
                      max_solves=self.config.search.max_solves, evaluations=len(state["records"]),
                      threshold_ohm_per_m=self.config.physics.threshold_ohm_per_m,
                      coverage_policy=self.config.solver.coverage_policy,
                      best=best, error=state.get("error"),
                      numerical_policy="User-tested template mesh; no extra confirmation solve",
                      model="isolated eigenmode circuit transverse impedance, beta=1, peak fields")
        atomic_json(self.store.root / "summary.json", report)
        if best:
            atomic_json(self.store.root / "best.json", best)
        lines = ["# WF5 transverse HOM search", "", f"Status: **{report['status']}**",
                 f"CST solves: {report['solve_count']} / {report['max_solves']}",
                 "", f"Threshold: {report['threshold_ohm_per_m']/1000:g} kΩ/m.",
                 "Mesh: inherited from the user-tested template; no additional verification solve."]
        if self.config.solver.coverage_policy == "fixed_window":
            lines += ["Coverage: user-accepted fixed frequency window and mode count; no automatic mode-count expansion or upper-sentinel proof."]
        if best:
            lines += ["", f"Best worst-mode impedance: {best['worst']/1000:.6g} kΩ/m",
                      f"Saved project: {best.get('project', '')}", "", "Parameters:", ""]
            lines += [f"- {k}: {v:.12g}" for k, v in best["parameters"].items()]
            lines += ["", f"Mode details and raw evidence: {best['attempt_dir']}"]
        if report.get("error"):
            lines += ["", f"Detail: {diagnostic_summary(report['error'])}"]
        lines += mode_report_lines(self.store.root, report, state,
                                  (self.config.physics.frequency_min_mhz,
                                   self.config.physics.frequency_max_mhz))
        (self.store.root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report
