"""Raw 1D-curve database — stores CST result curves for penalty-agnostic warmup.

Records the raw frequency-domain data (xdata/ydata arrays) from every
``ResultReader`` call during an evaluation.  When the penalty algorithm
changes, these curves can be replayed through a ``VirtualResultReader`` —
the objectives' ``raw_value()`` methods run unchanged, but this time with
the new scalarization parameters / penalty modes.

Design
------
- **RecordingResultReader** wraps a real ``ResultReader``, intercepts
  ``get_s_parameter``, ``get_1d_result``, and ``get_scalar``, and saves
  the raw arrays to an in-memory dict.
- **VirtualResultReader** loads a ``.npz`` file and implements the same
  interface, so ``ObjectiveFunction.raw_value()`` works without modification.
- ``curves_to_warmup()`` loads all ``.npz`` files in a directory, replays
  each through the current objectives, and returns ``(X, y)`` for SAO.

Storage layout::

    D:/Results/raw_curves/
        index.jsonl       # one JSON line per evaluation
        eval_0000.npz     # raw 1D arrays for evaluation 0
        eval_0001.npz     # ...
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Callable

import numpy as np

_logger = logging.getLogger(__name__)

# Import ResultReader types lazily to avoid circular imports
from .core.results import ResultReader, SParameterData, ScalarResult

# ---------------------------------------------------------------------------
# Tree-path key sanitization
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.]")


def _sanitize(tree_path: str) -> str:
    """Convert a CST tree path into a safe ``.npz`` key segment."""
    return _SAFE_RE.sub("_", tree_path.replace("\\", "/"))


# ---------------------------------------------------------------------------
# RecordingResultReader
# ---------------------------------------------------------------------------


class RecordingResultReader:
    """Wrap a ``ResultReader`` and record all 1D/0D reads in memory.

    Every call to ``get_s_parameter``, ``get_1d_result``, or ``get_scalar``
    is intercepted.  The raw arrays are saved to ``recorded_curves`` keyed
    by the CST tree path.

    All other attribute accesses are proxied to the inner reader.
    """

    def __init__(self, inner: ResultReader | None = None) -> None:
        self._inner = inner
        self.recorded_curves: dict[str, dict[str, Any]] = {}
        # Track read order for deterministic replay
        self._read_order: list[str] = []

    # -- intercepted methods -------------------------------------------------

    def get_s_parameter(
        self, tree_path: str = "", run_id: int = 0
    ) -> SParameterData:
        result = self._inner.get_s_parameter(tree_path, run_id)
        tp = tree_path or self._inner.TREEPATH_S11
        self._record_curve(
            tp,
            xdata=np.asarray(result.frequencies, dtype=float),
            ydata=np.asarray(result.s_complex),
            ref_impedance=np.asarray(result.reference_impedance),
            xlabel=getattr(result, "xlabel", ""),
            ylabel=getattr(result, "ylabel", ""),
            curve_type="s_parameter",
        )
        return result

    def get_1d_result(
        self, tree_path: str, run_id: int = 0
    ) -> tuple[np.ndarray, np.ndarray]:
        xdata, ydata = self._inner.get_1d_result(tree_path, run_id)
        # Try to grab axis labels from the underlying ResultItem
        xlabel = ""
        ylabel = ""
        try:
            item = self._inner.get_result_item(tree_path, run_id)
            xlabel = getattr(item, "xlabel", "") or ""
            ylabel = getattr(item, "ylabel", "") or ""
        except Exception:
            pass
        self._record_curve(
            tree_path,
            xdata=np.asarray(xdata, dtype=float),
            ydata=np.asarray(ydata),
            xlabel=xlabel,
            ylabel=ylabel,
            curve_type="1d",
        )
        return xdata, ydata

    def get_scalar(self, tree_path: str, run_id: int = 0) -> ScalarResult:
        result = self._inner.get_scalar(tree_path, run_id)
        self._record_curve(
            tree_path,
            xdata=np.array([0.0]),
            ydata=np.array([float(result.value)]),
            xlabel="",
            ylabel="",
            curve_type="scalar",
        )
        return result

    # -- proxy ---------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in (
            "recorded_curves", "_read_order", "_record_curve",
            "get_s_parameter", "get_1d_result", "get_scalar",
        ):
            raise AttributeError(name)
        return getattr(self._inner, name)

    # -- internal ------------------------------------------------------------

    def _record_curve(
        self,
        tree_path: str,
        xdata: np.ndarray,
        ydata: np.ndarray,
        xlabel: str = "",
        ylabel: str = "",
        ref_impedance: np.ndarray | None = None,
        curve_type: str = "1d",
    ) -> None:
        entry: dict[str, Any] = {
            "xdata": np.asarray(xdata, dtype=float),
            "curve_type": curve_type,
            "xlabel": str(xlabel),
            "ylabel": str(ylabel),
        }
        if np.issubdtype(np.asarray(ydata).dtype, np.complexfloating):
            arr = np.asarray(ydata)
            entry["ydata_real"] = np.asarray(arr.real, dtype=float)
            entry["ydata_imag"] = np.asarray(arr.imag, dtype=float)
        else:
            entry["ydata_real"] = np.asarray(ydata, dtype=float)
        if ref_impedance is not None:
            ri = np.asarray(ref_impedance)
            if np.issubdtype(ri.dtype, np.complexfloating):
                entry["ref_imp_real"] = np.asarray(ri.real, dtype=float)
                entry["ref_imp_imag"] = np.asarray(ri.imag, dtype=float)
            else:
                entry["ref_imp_real"] = np.asarray(ri, dtype=float)
        if tree_path not in self.recorded_curves:
            self._read_order.append(tree_path)
        self.recorded_curves[tree_path] = entry


# ---------------------------------------------------------------------------
# Session helpers (module-level)
# ---------------------------------------------------------------------------

_active_recorders: list[RecordingResultReader] = []


def start_recording_session() -> None:
    """Begin a new recording session (clears any previous recorders)."""
    _active_recorders.clear()


def make_recording_reader(project_path: str) -> Callable[[], RecordingResultReader]:
    """Create a callable that returns a ``RecordingResultReader`` for *project_path*.

    The new recorder is registered in the active session so that
    :func:`collect_curves` can gather all curves at the end.

    Returns a **callable** (compatible with ``ObjectiveFunction._reader_factory``).
    """
    inner = ResultReader(str(project_path), allow_interactive=True)
    rec = RecordingResultReader(inner)
    _active_recorders.append(rec)
    return lambda: rec


def collect_curves() -> dict[str, dict[str, Any]]:
    """Return all recorded curves from the active session.

    Keys are CST tree paths; values are the recorded array dicts.
    """
    merged: dict[str, dict[str, Any]] = {}
    for rec in _active_recorders:
        merged.update(rec.recorded_curves)
    return merged


# ---------------------------------------------------------------------------
# .npz save / index management
# ---------------------------------------------------------------------------


def save_curves_npz(
    path: str,
    curves: dict[str, dict[str, Any]],
) -> None:
    """Write recorded curves to a compressed ``.npz`` file.

    Parameters
    ----------
    path : str
        Output ``.npz`` path.
    curves : dict
        Output of :func:`collect_curves`.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload: dict[str, np.ndarray] = {}
    for tree_path, entry in curves.items():
        base = _sanitize(tree_path)
        payload[f"{base}/xdata"] = np.asarray(entry["xdata"], dtype=float)
        if "ydata_real" in entry:
            payload[f"{base}/ydata_real"] = np.asarray(entry["ydata_real"], dtype=float)
        if "ydata_imag" in entry:
            payload[f"{base}/ydata_imag"] = np.asarray(entry["ydata_imag"], dtype=float)
        if "ref_imp_real" in entry:
            payload[f"{base}/ref_imp_real"] = np.asarray(entry["ref_imp_real"], dtype=float)
        if "ref_imp_imag" in entry:
            payload[f"{base}/ref_imp_imag"] = np.asarray(entry["ref_imp_imag"], dtype=float)
        # Store metadata as string arrays
        meta = {
            "xlabel": str(entry.get("xlabel", "")),
            "ylabel": str(entry.get("ylabel", "")),
            "curve_type": str(entry.get("curve_type", "1d")),
        }
        payload[f"{base}/__meta__"] = np.array(list(meta.items()), dtype=object)
    np.savez_compressed(path, **payload)


def save_index_record(index_path: str, record: dict[str, Any]) -> None:
    """Append one line to the ``index.jsonl`` file."""
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    record.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with open(index_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_index(index_path: str) -> list[dict[str, Any]]:
    """Read all records from ``index.jsonl``."""
    if not os.path.isfile(index_path):
        return []
    records: list[dict[str, Any]] = []
    with open(index_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# VirtualResultReader — replay .npz as ResultReader
# ---------------------------------------------------------------------------


class _MockResultItem:
    """Minimal mock of ``cst.results.ResultItem`` for ``get_result_item``."""

    def __init__(self, xlabel: str = "", ylabel: str = "") -> None:
        self.xlabel = xlabel
        self.ylabel = ylabel


class VirtualResultReader:
    """Replay 1D curves from a ``.npz`` file, exposing the ``ResultReader`` API.

    ``ObjectiveFunction.raw_value()`` expects a ``ResultReader``.
    This class implements the same read methods by loading arrays from
    a previously-saved ``.npz`` file.
    """

    # Class-level sentinel so objectives that reference TREEPATH constants still work
    TREEPATH_S11: str = r"1D Results\S-Parameters\S1(2),1(2)"
    TREEPATH_S21: str = r"1D Results\S-Parameters\S2(1),1(2)"
    TREEPATH_S31: str = r"1D Results\S-Parameters\S3(1),1(2)"
    TREEPATH_MAX_E_Z0: str = r"Tables\0D Results\MaxE_Z0"
    TREEPATH_MAX_E_Z1: str = r"Tables\0D Results\MaxE_Z1"
    TREEPATH_MAX_E_Z2: str = r"Tables\0D Results\MaxE_Z2"
    allow_interactive: bool = False

    def __init__(self, npz_path: str, default_ref_impedance: float = 50.0) -> None:
        self._data = np.load(npz_path, allow_pickle=True)
        self._default_ref_imp = float(default_ref_impedance)
        # Build tree_path → sanitized_base mapping
        self._tp_to_base: dict[str, str] = {}
        for key in self._data.keys():
            if "/xdata" in key:
                base = key[: key.index("/xdata")]
                self._tp_to_base[_unsanitize(base)] = base

    # -- public API matching ResultReader ------------------------------------

    def get_s_parameter(
        self, tree_path: str = "", run_id: int = 0
    ) -> SParameterData:
        tp = tree_path or self.TREEPATH_S11
        base = self._resolve_base(tp)
        freqs = self._load_array(f"{base}/xdata")
        real = self._load_array(f"{base}/ydata_real")
        imag = self._load_array(f"{base}/ydata_imag", required=False)
        if imag is not None:
            s_cx = real + 1j * imag
        else:
            s_cx = real.astype(complex)

        ref_real = self._load_array(f"{base}/ref_imp_real", required=False)
        ref_imag = self._load_array(f"{base}/ref_imp_imag", required=False)
        if ref_real is not None:
            if ref_imag is not None:
                ref_imp = ref_real + 1j * ref_imag
            else:
                ref_imp = ref_real.astype(complex)
        else:
            ref_imp = np.full_like(s_cx, self._default_ref_imp + 0j)

        xlabel = self._load_meta(base, "xlabel", "")
        ylabel = self._load_meta(base, "ylabel", "")

        return SParameterData(
            frequencies=freqs,
            s_complex=s_cx,
            reference_impedance=ref_imp,
            xlabel=xlabel,
            ylabel=ylabel,
            treepath=tp,
            run_id=0,
        )

    def get_1d_result(
        self, tree_path: str, run_id: int = 0
    ) -> tuple[np.ndarray, np.ndarray]:
        base = self._resolve_base(tree_path)
        xdata = self._load_array(f"{base}/xdata")
        real = self._load_array(f"{base}/ydata_real")
        imag = self._load_array(f"{base}/ydata_imag", required=False)
        if imag is not None:
            ydata = real + 1j * imag
        else:
            ydata = real
        return xdata, ydata

    def get_scalar(self, tree_path: str, run_id: int = 0) -> ScalarResult:
        base = self._resolve_base(tree_path)
        ydata = self._load_array(f"{base}/ydata_real")
        value = float(ydata[0]) if len(ydata) > 0 else np.nan
        return ScalarResult(value=value, treepath=tree_path, run_id=0)

    def get_result_item(self, tree_path: str, run_id: int = 0) -> _MockResultItem:
        base = self._resolve_base(tree_path)
        xlabel = self._load_meta(base, "xlabel", "")
        ylabel = self._load_meta(base, "ylabel", "")
        return _MockResultItem(xlabel=xlabel, ylabel=ylabel)

    # -- internal ------------------------------------------------------------

    def _resolve_base(self, tree_path: str) -> str:
        sanitized = _sanitize(tree_path)
        if sanitized in self._tp_to_base:
            return self._tp_to_base[sanitized]
        # Fuzzy match: try all stored keys
        for tp, base in self._tp_to_base.items():
            if _sanitize(tp) == sanitized:
                return base
        # Last resort: use the sanitized path directly
        return sanitized

    def _load_array(self, key: str, required: bool = True) -> np.ndarray | None:
        if key in self._data:
            return np.asarray(self._data[key], dtype=float)
        if required:
            raise KeyError(
                f"Key '{key}' not found in .npz. "
                f"Available: {list(self._data.keys())}"
            )
        return None

    def _load_meta(self, base: str, field: str, default: str = "") -> str:
        meta_key = f"{base}/__meta__"
        if meta_key not in self._data:
            return default
        meta_arr = self._data[meta_key]
        for pair in meta_arr:
            if pair[0] == field:
                return str(pair[1])
        return default

    def close(self) -> None:
        """Release the backing ``.npz`` file handle."""
        if hasattr(self._data, "close"):
            self._data.close()


# ---------------------------------------------------------------------------
# Warmup from stored curves
# ---------------------------------------------------------------------------


def curves_to_warmup(
    index_path: str,
    objectives: list[Any],
    weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Load all ``.npz`` evaluations and re-compute penalties.

    Each evaluation's curves are replayed through the *objectives* using
    a ``VirtualResultReader``.  Only evaluations where **all** objectives
    produce finite raw values are returned.

    Parameters
    ----------
    index_path : str
        Path to ``index.jsonl``.
    objectives : list[ObjectiveFunction]
        Current objectives (with their current modes).
    weights : np.ndarray or None
        Scalarisation weights.  Equal weights if ``None``.

    Returns
    -------
    X : np.ndarray (N_valid, D)
    y : np.ndarray (N_valid,)
    """
    records = load_index(index_path)
    if not records:
        _logger.info("curves_to_warmup: index is empty (%s)", index_path)
        return np.empty((0, 0)), np.empty((0,))

    index_dir = os.path.dirname(index_path) or "."
    n_obj = len(objectives)
    obj_names = [obj.name for obj in objectives]

    if weights is None:
        w = np.ones(n_obj) / n_obj
    else:
        w = np.asarray(weights, dtype=float)
        w = w / np.sum(w)

    # Collect all parameter names from the first record
    first_params = records[0].get("params", {})
    param_names = list(first_params.keys())
    d = len(param_names)

    # Pre-allocate
    n_total = len(records)
    X_all = np.full((n_total, d), np.nan)
    raw_all = np.full((n_total, n_obj), np.nan)

    for i, rec in enumerate(records):
        npz_file = rec.get("npz_file", "")
        npz_path = os.path.join(index_dir, npz_file) if npz_file else ""
        if not npz_path or not os.path.isfile(npz_path):
            continue

        # Fill parameters
        rp = rec.get("params", {})
        for j, pn in enumerate(param_names):
            X_all[i, j] = float(rp.get(pn, np.nan))

        # Replay curves through objectives
        try:
            vreader = VirtualResultReader(npz_path)
        except Exception:
            _logger.warning("Failed to open %s", npz_path, exc_info=True)
            continue

        for j, obj in enumerate(objectives):
            saved_factory = getattr(obj, "_reader_factory", None)
            obj._reader_factory = lambda vr=vreader: vr  # noqa: E731
            try:
                rv = obj.raw_value()
                if np.isfinite(rv):
                    raw_all[i, j] = float(rv)
            except Exception:
                pass
            finally:
                obj._reader_factory = saved_factory

    # Keep only rows where ALL objectives have finite raw values
    valid = np.all(np.isfinite(raw_all), axis=1)
    if not np.any(valid):
        _logger.warning("curves_to_warmup: no valid evaluations (all have NaN)")
        return np.empty((0, d)), np.empty((0,))

    X_valid = X_all[valid]
    raw_valid = raw_all[valid]

    # Penalty + weighted sum
    penalties = np.full((len(X_valid), n_obj), np.nan)
    for j, obj in enumerate(objectives):
        for i in range(len(X_valid)):
            try:
                penalties[i, j] = obj.mode.compute(float(raw_valid[i, j]))
            except Exception:
                penalties[i, j] = np.nan

    valid2 = np.all(np.isfinite(penalties), axis=1)
    X_final = X_valid[valid2]
    y_final = np.dot(penalties[valid2], w)

    _logger.info(
        "curves_to_warmup: %d/%d evaluations usable for warmup",
        len(X_final), n_total,
    )
    return X_final, y_final


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unsanitize(sanitized: str) -> str:
    """Inverse of ``_sanitize`` — best-effort, not exact."""
    return sanitized.replace("_", " ").replace("/", "\\")
