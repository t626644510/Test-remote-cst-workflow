"""CST result reading layer.

Provides ResultReader, the single point of contact for ``cst.results``.
Returns typed, structured data containers rather than raw tuples/lists.
No physics interpretation happens here — that belongs in ``physics/``.

CST 2026 additions: ``Result2DItem`` colormap support (cutting-plane field
plots), ``get_tree_items(filter='colormap')``, and lazy ``ProjectFile``
caching.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import init_cst_path

_logger = logging.getLogger(__name__)

# ── Lazy cst.results import (resolved on first use) ────────────────────
_RESULTS_MODULE = None


def _ensure_results_imported() -> None:
    """One-time import of cst.results.

    Assumes ``init_cst_path()`` has already been called by
    ``CSTConnection._ensure_cst_imported()`` — does NOT re-insert a
    potentially conflicting default path.
    """
    global _RESULTS_MODULE
    if _RESULTS_MODULE is not None:
        return
    import cst.results as _cr
    _RESULTS_MODULE = _cr


# ---------------------------------------------------------------------------
# Typed result containers
# ---------------------------------------------------------------------------


@dataclass
class SParameterData:
    """Raw S-parameter data extracted from a CST 1D result."""

    frequencies: np.ndarray
    s_complex: np.ndarray
    reference_impedance: np.ndarray
    xlabel: str = ""
    ylabel: str = ""
    treepath: str = ""
    run_id: int = 0


@dataclass
class ScalarResult:
    """A single 0D (table) result value."""

    value: float
    unit: str = ""
    treepath: str = ""
    run_id: int = 0


@dataclass
class Result2DData:
    """2D colormap result from a cutting plane or surface (CST 2025+).

    Attributes
    ----------
    data : np.ndarray
        2D array of result values, shape ``(ny, nx)``, row-major.
    xdata : np.ndarray
        Sampling positions along the x-axis (length *nx*).
    ydata : np.ndarray
        Sampling positions along the y-axis (length *ny*).
    xlabel : str
        Label of the x-axis.
    ylabel : str
        Label of the y-axis.
    data_unit : str
        Unit of the result data (e.g. ``"V/m"``).
    title : str
        Result title from the navigation tree.
    treepath : str
        Navigation tree path from which the data was read.
    run_id : int
        CST parameter sweep run ID.
    """

    data: np.ndarray
    xdata: np.ndarray
    ydata: np.ndarray
    xlabel: str = ""
    ylabel: str = ""
    data_unit: str = ""
    title: str = ""
    treepath: str = ""
    run_id: int = 0


@dataclass
class ResultBundle:
    """Aggregated raw results from one CST simulation.

    CST 2026: *colormaps* may carry 2D cutting-plane field data read via
    ``Result2DItem``.
    """

    s_parameters: dict[str, SParameterData] = field(default_factory=dict)
    scalars: dict[str, ScalarResult] = field(default_factory=dict)
    colormaps: dict[str, Result2DData] = field(default_factory=dict)
    run_id: int = 0
    parameter_combination: dict[str, float] | None = None


# ---------------------------------------------------------------------------
# ResultReader
# ---------------------------------------------------------------------------


class ResultReader:
    """Reads raw results from a ``.cst`` project file using ``cst.results``.

    Parameters
    ----------
    project_path : str
        Path to the ``.cst`` file on disk.
    allow_interactive : bool
        If ``True``, allows reading results while the project is open in
        CST Studio Suite (requires the user to have saved first).
    cache_project_file : bool
        If ``True`` (default), the ``ProjectFile`` is opened once and
        reused.  Call ``invalidate_cache()`` after the project is
        re-saved from CST.
    """

    # Canonical tree paths — adjust to match your project template
    TREEPATH_S11: str = r"1D Results\S-Parameters\S1(2),1(2)"
    TREEPATH_S21: str = r"1D Results\S-Parameters\S2(1),1(2)"
    TREEPATH_S31: str = r"1D Results\S-Parameters\S3(1),1(2)"
    TREEPATH_MAX_E_Z0: str = r"Tables\0D Results\MaxE_Z0"
    TREEPATH_MAX_E_Z1: str = r"Tables\0D Results\MaxE_Z1"
    TREEPATH_MAX_E_Z2: str = r"Tables\0D Results\MaxE_Z2"

    def __init__(
        self,
        project_path: str,
        allow_interactive: bool = True,
        cache_project_file: bool = True,
        s11_treepath: str = "",
        s21_treepath: str = "",
        s31_treepath: str = "",
    ) -> None:
        self._project_path = project_path
        self._allow_interactive = allow_interactive
        self._cache_enabled = cache_project_file
        self._pf: Any = None

        # Per-instance S-parameter tree path overrides (config-driven).
        # When empty, the class-level defaults are used.
        if s11_treepath:
            self.TREEPATH_S11 = s11_treepath
        if s21_treepath:
            self.TREEPATH_S21 = s21_treepath
        if s31_treepath:
            self.TREEPATH_S31 = s31_treepath

        _ensure_results_imported()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        """Drop the cached ``ProjectFile`` so the next read re-opens it.

        Call this after the project has been re-saved from CST Studio
        Suite (e.g. after a solver run), otherwise stale results may
        be returned.
        """
        self._pf = None

    # ------------------------------------------------------------------
    # Public read methods — 0D / 1D
    # ------------------------------------------------------------------

    def get_s_parameter(
        self, tree_path: str = "", run_id: int = 0
    ) -> SParameterData:
        """Read a 1D S-parameter result."""
        tree_path = tree_path or self.TREEPATH_S11
        item = self._get_result_item(tree_path, run_id)

        freqs = np.array(item.get_xdata(), dtype=float)

        raw_data = item.get_data()
        if isinstance(raw_data, list) and len(raw_data) > 0:
            first = raw_data[0]
            tuple_len = len(first) if isinstance(first, tuple) else 1
        else:
            tuple_len = 1

        if tuple_len >= 3:
            complex_s11 = np.array([v[1] for v in raw_data], dtype=complex)
            ref_imp = np.array([v[2] for v in raw_data], dtype=complex)
        elif tuple_len == 2:
            complex_s11 = np.array([v[1] for v in raw_data], dtype=complex)
            ref_imp = np.zeros_like(complex_s11)
        else:
            complex_s11 = np.array(raw_data, dtype=complex)
            ref_imp = np.zeros_like(complex_s11)

        return SParameterData(
            frequencies=freqs,
            s_complex=complex_s11,
            reference_impedance=ref_imp,
            xlabel=item.xlabel,
            ylabel=item.ylabel,
            treepath=tree_path,
            run_id=run_id,
        )

    def get_scalar(self, tree_path: str, run_id: int = 0) -> ScalarResult:
        """Read a 0D table scalar result."""
        item = self._get_result_item(tree_path, run_id)
        val = item.get_data()
        value = float(val[0]) if isinstance(val, list) else float(val)
        return ScalarResult(value=value, treepath=tree_path, run_id=run_id)

    def get_1d_result(
        self, tree_path: str, run_id: int = 0
    ) -> tuple[np.ndarray, np.ndarray]:
        """Read a generic 1D result, returning ``(xdata, ydata)``."""
        item = self._get_result_item(tree_path, run_id)
        return np.array(item.get_xdata()), np.array(item.get_ydata())

    def get_result_item(self, tree_path: str, run_id: int = 0) -> Any:
        """Return the raw ``cst.results.ResultItem``."""
        return self._get_result_item(tree_path, run_id)

    # ------------------------------------------------------------------
    # Public read methods — 2D (CST 2025+)
    # ------------------------------------------------------------------

    def get_2d_result(
        self, tree_path: str, run_id: int = 0
    ) -> Result2DData:
        """Read a 2D colormap result (cutting-plane field plot).

        Requires CST Studio Suite 2025 or later.  The project file must
        have been saved after the solver run.

        Parameters
        ----------
        tree_path : str
            Navigation tree path to the colormap result.
        run_id : int
            Parametric run ID (0 = nominal).

        Returns
        -------
        Result2DData
        """
        mod_3d = self._project_file.get_3d()
        item = mod_3d.get_result2d_item(tree_path)

        return Result2DData(
            data=np.array(item.get_data(), dtype=float),
            xdata=np.array(item.get_xpositions(), dtype=float),
            ydata=np.array(item.get_ypositions(), dtype=float),
            xlabel=item.xlabel or "",
            ylabel=item.ylabel or "",
            data_unit=getattr(item, "dataunit", "") or "",
            title=item.title or "",
            treepath=tree_path,
            run_id=run_id,
        )

    # ------------------------------------------------------------------
    # Tree exploration
    # ------------------------------------------------------------------

    def list_tree_items(self, filter_str: str = "0D/1D") -> list[str]:
        """List all result tree items matching *filter_str*.

        Parameters
        ----------
        filter_str : str
            ``"0D/1D"`` for scalar/curve results,
            ``"colormap"`` for 2D cutting-plane results (CST 2025+).

        Returns
        -------
        list[str]
        """
        return self._project_file.get_3d().get_tree_items(filter_str)

    def list_colormap_items(self) -> list[str]:
        """List all 2D colormap result tree paths (CST 2025+)."""
        return self.list_tree_items("colormap")

    def get_run_ids(
        self, tree_path: str, skip_nonparametric: bool = False
    ) -> list[int]:
        """Return all run IDs available for *tree_path*."""
        return self._project_file.get_3d().get_run_ids(
            tree_path, skip_nonparametric=skip_nonparametric
        )

    def get_all_run_ids(self, max_mesh_passes_only: bool = True) -> list[int]:
        """Return all run IDs across the project."""
        return self._project_file.get_3d().get_all_run_ids(
            max_mesh_passes_only=max_mesh_passes_only
        )

    def get_parameter_combination(self, run_id: int) -> dict[str, float]:
        """Resolve a *run_id* to its parameter name → value mapping."""
        return self._project_file.get_3d().get_parameter_combination(run_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _project_file(self) -> Any:
        """Lazy-init (and optionally cache) the ``cst.results.ProjectFile``."""
        if self._pf is None or not self._cache_enabled:
            self._pf = _RESULTS_MODULE.ProjectFile(
                self._project_path, allow_interactive=self._allow_interactive
            )
        return self._pf

    def _get_result_item(self, tree_path: str, run_id: int) -> Any:
        return self._project_file.get_3d().get_result_item(tree_path, run_id)
