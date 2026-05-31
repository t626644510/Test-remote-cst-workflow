"""In-situ sensitivity analysis — reuse optimisation data at zero extra cost.

Instead of running a dedicated sensitivity campaign (thousands of CST
evaluations), this module fits a GP surrogate to the accumulated
optimisation history and runs Sobol', correlation, or linear-regression
analysis on the surrogate.

Three analysis methods
----------------------
============  ======  ==================================================
Method        Min N   Description
============  ======  ==================================================
``gp_sobol``  30      Saltelli Sobol' indices computed on a fitted GP
                       surrogate (1024 base samples, D*(2D+2) cheap
                       predictions).  Best overall accuracy.
``correlation`` 10    Spearman ρ and Pearson r between each parameter
                       and each objective.  Fast but linear/monotonic only.
``linear``    10      Standardised linear regression coefficients β.
                       Good for screening when the response is smooth.
============  ======  ==================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from scipy.stats import spearmanr, pearsonr, qmc

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
from sklearn.preprocessing import StandardScaler

from .base import OptimizationResult


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass
class SensitivityReport:
    """Container for in-situ sensitivity analysis results.

    Attributes
    ----------
    method : str
        Which method produced this report.
    n_data_points : int
        Number of (X, F) samples from the optimisation history.
    param_names : list[str]
        Ordered parameter names.
    objective_index : int
        Which objective column was analysed (0 for first).
    sobol_s1 : dict[str, float]
        First-order Sobol' indices (only for ``gp_sobol``).
    sobol_st : dict[str, float]
        Total-effect Sobol' indices (only for ``gp_sobol``).
    spearman : dict[str, float]
        Spearman rank correlation (only for ``correlation``).
    pearson : dict[str, float]
        Pearson linear correlation (only for ``correlation``).
    linear_betas : dict[str, float]
        Standardised regression coefficients (only for ``linear``).
    recommendation : str
        Human-readable interpretation.
    """

    method: str = ""
    n_data_points: int = 0
    param_names: list[str] = field(default_factory=list)
    objective_index: int = 0

    sobol_s1: dict[str, float] = field(default_factory=dict)
    sobol_st: dict[str, float] = field(default_factory=dict)

    spearman: dict[str, float] = field(default_factory=dict)
    pearson: dict[str, float] = field(default_factory=dict)

    linear_betas: dict[str, float] = field(default_factory=dict)

    recommendation: str = ""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class InSituSensitivity:
    """Zero-extra-cost sensitivity analysis from optimisation history.

    Parameters
    ----------
    result : OptimizationResult
        The completed optimisation result (must contain ``history_x``
        and ``history_f``).
    param_names : list[str]
        Parameter names, ordered to match ``history_x`` columns.
    seed : int or None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        result: OptimizationResult,
        param_names: list[str],
        seed: int | None = 42,
    ) -> None:
        if not result.history_x or not result.history_f:
            raise ValueError("OptimizationResult must contain history_x and history_f")

        self._X = np.array(result.history_x)  # (N, D)
        self._F = np.array(result.history_f)  # (N, M) or (N,)
        if self._F.ndim == 1:
            self._F = self._F.reshape(-1, 1)
        self._param_names = list(param_names)
        self._seed = seed
        self._rng = np.random.RandomState(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        method: str = "gp_sobol",
        objective_index: int = 0,
        n_gp_base_samples: int = 1024,
    ) -> SensitivityReport:
        """Run sensitivity analysis.

        Parameters
        ----------
        method : str
            ``"gp_sobol"`` | ``"correlation"`` | ``"linear"``.
        objective_index : int
            Which objective column in ``history_f`` to analyse (0-based).
        n_gp_base_samples : int
            For ``gp_sobol``: Saltelli base sample count.  Total GP
            evaluations = N * (2D + 2).  Default 1024.

        Returns
        -------
        SensitivityReport
        """
        y = self._F[:, objective_index]  # (N,)
        valid = np.isfinite(y)
        if valid.sum() < 5:
            raise ValueError(
                f"Too few valid objective values ({valid.sum()}) for analysis"
            )

        X_valid = self._X[valid]
        y_valid = y[valid]
        n_valid = len(y_valid)

        if method == "gp_sobol":
            return self._analyze_gp_sobol(X_valid, y_valid, n_valid, n_gp_base_samples)
        elif method == "correlation":
            return self._analyze_correlation(X_valid, y_valid, n_valid)
        elif method == "linear":
            return self._analyze_linear(X_valid, y_valid, n_valid)
        else:
            raise ValueError(
                f"Unknown method: '{method}'.  "
                f"Choose from: gp_sobol, correlation, linear"
            )

    # ------------------------------------------------------------------
    # Method implementations
    # ------------------------------------------------------------------

    def _analyze_gp_sobol(
        self,
        X: np.ndarray,
        y: np.ndarray,
        n_valid: int,
        n_base: int,
    ) -> SensitivityReport:
        """GP-surrogate Sobol' analysis."""
        n_params = X.shape[1]

        # Fit GP surrogate
        kernel = ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3)) * RBF(
            length_scale=[1.0] * n_params,
            length_scale_bounds=(1e-3, 1e2),
        ) + WhiteKernel(noise_level=1e-4, noise_level_bounds=(1e-6, 1e-1))

        gp = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=3,
            random_state=self._seed,
        )
        gp.fit(X, y)

        # Scale normaliser for unit-cube sampling
        lo = X.min(axis=0)
        hi = X.max(axis=0)
        span = hi - lo
        span[span < 1e-12] = 1.0  # avoid div-by-zero for constant params

        def gp_predict(x_unit: np.ndarray) -> np.ndarray:
            """GP prediction from unit-cube samples."""
            x_phys = lo + x_unit * span
            return gp.predict(x_phys)

        # Saltelli estimator on GP surrogate
        D = n_params
        N = n_base
        sampler = qmc.Sobol(d=D * (D + 2), scramble=True, seed=self._seed)
        unit_samples = sampler.random(n=N)

        A_unit = unit_samples[:, :D]
        B_unit = unit_samples[:, D : 2 * D]

        f_A = gp_predict(A_unit)
        f_B = gp_predict(B_unit)

        f0 = float(np.mean(f_A))
        var_Y = float(np.mean(f_A**2) - f0**2)

        s1 = {}
        st = {}

        for j in range(D):
            AB_unit = A_unit.copy()
            AB_unit[:, j] = B_unit[:, j]
            f_AB = gp_predict(AB_unit)

            if var_Y > 1e-15:
                s1_j = float(np.mean(f_B * (f_AB - f_A)) / var_Y)
                st_j = float(0.5 * np.mean((f_A - f_AB) ** 2) / var_Y)
            else:
                s1_j = 0.0
                st_j = 0.0

            s1[self._param_names[j]] = max(0.0, min(1.0, s1_j))
            st[self._param_names[j]] = max(0.0, min(1.0, st_j))

        # Build recommendation
        important = [
            n for n in self._param_names if st.get(n, 0) > 0.1
        ]
        dominant = [
            n for n in self._param_names if st.get(n, 0) > 0.5
        ]
        if dominant:
            rec = (
                f"Dominant parameter(s): {', '.join(dominant)}. "
                f"Focus optimisation efforts on these."
            )
        elif important:
            rec = (
                f"Influential parameter(s): {', '.join(important)}. "
                f"Consider refining their ranges."
            )
        else:
            rec = "No single parameter dominates — the response is likely smooth and multi-dimensional."

        return SensitivityReport(
            method="gp_sobol",
            n_data_points=n_valid,
            param_names=self._param_names,
            sobol_s1=s1,
            sobol_st=st,
            recommendation=rec,
        )

    def _analyze_correlation(
        self, X: np.ndarray, y: np.ndarray, n_valid: int
    ) -> SensitivityReport:
        """Spearman + Pearson correlation analysis."""
        spearman = {}
        pearson = {}
        for j, name in enumerate(self._param_names):
            xj = X[:, j]
            # Skip constant columns
            if np.std(xj) < 1e-15:
                spearman[name] = 0.0
                pearson[name] = 0.0
                continue
            r_s, _ = spearmanr(xj, y)
            r_p, _ = pearsonr(xj, y)
            spearman[name] = float(r_s)
            pearson[name] = float(r_p)

        # Recommendation
        significant = [
            n for n in self._param_names
            if abs(spearman.get(n, 0)) > 0.3
        ]
        if significant:
            rec = (
                f"Parameters with |Spearman ρ| > 0.3: {', '.join(significant)}. "
                f"These show monotonic association with the objective."
            )
        else:
            rec = "No parameter shows strong monotonic correlation — may need more samples or a non-monotonic method (try gp_sobol)."

        return SensitivityReport(
            method="correlation",
            n_data_points=n_valid,
            param_names=self._param_names,
            spearman=spearman,
            pearson=pearson,
            recommendation=rec,
        )

    def _analyze_linear(
        self, X: np.ndarray, y: np.ndarray, n_valid: int
    ) -> SensitivityReport:
        """Standardised linear regression coefficients."""
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        # OLS via normal equation: β = (X'X)^-1 X'y
        beta = np.linalg.lstsq(X_scaled, y, rcond=None)[0]

        betas = {}
        for j, name in enumerate(self._param_names):
            betas[name] = float(beta[j])

        # Normalise to sum of absolute values for relative importance
        total = sum(abs(b) for b in betas.values()) or 1.0
        ranked = sorted(betas.items(), key=lambda kv: abs(kv[1]), reverse=True)

        lines = [f"Standardised linear coefficients (rel. importance):"]
        for name, b in ranked:
            pct = abs(b) / total * 100
            lines.append(f"  {name}: β = {b:+.4f}  ({pct:.1f}%)")

        return SensitivityReport(
            method="linear",
            n_data_points=n_valid,
            param_names=self._param_names,
            linear_betas=betas,
            recommendation="\n".join(lines),
        )
