"""Task generation and saved-current analysis; no live CST dependencies."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.integrate import trapezoid


@dataclass(frozen=True)
class Task:
    """One source and external RF excitation (phase in degrees)."""

    source: str
    factor1: float
    phase: int

    @property
    def key(self) -> str:
        return f"s{int(self.source[8:]):02d}_f{round(self.factor1 * 100):03d}_p{self.phase:03d}"

    def record(self) -> dict[str, Any]:
        """The voltage label assumes the user's factor1=1 -> 500 kV calibration."""
        return dict(asdict(self), key=self.key, voltage_kV=500 * self.factor1)


def tasks() -> list[Task]:
    """861 actual runs; zero RF field has only one independent phase."""
    return [
        Task(f"particle{s}", f / 5, p)
        for s in range(1, 22)
        for f in range(6)
        for p in ([0] if f == 0 else range(0, 360, 45))
    ]


def logical_grid() -> list[dict[str, Any]]:
    """1008 logical combinations, with explicit zero-field aliases."""
    return [
        dict(Task(f"particle{s}", f / 5, p).record(),
             actual_key=Task(f"particle{s}", f / 5, 0 if f == 0 else p).key,
             equivalent_reference=(f == 0 and p != 0))
        for s in range(1, 22) for f in range(6) for p in range(0, 360, 45)
    ]


def active_source_macro(source: str) -> str:
    """Official PICSolver API: switch only primary sources, never SEE surfaces."""
    if source not in {f"particle{i}" for i in range(1, 22)}:
        raise ValueError(f"Unknown source: {source}")
    lines = ["With PICSolver"]
    for i in range(1, 22):
        name = f"particle{i}"
        lines.append(f'.DefineActiveParticleSourcesAndInterfaces "{name}", "{name == source}"')
    return "\n".join(lines + ["End With"])


def current_xy(curve: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Require measured time in ns, current in A, and strictly ordered samples."""
    if curve["xlabel"] != "Time / ns" or curve["ylabel"] != "Current / A":
        raise ValueError("Expected Time / ns and Current / A")
    x, y = np.asarray(curve["x"], float), np.asarray(curve["y"], float)
    if (len(x) < 2 or x.shape != y.shape or
            not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or
            not np.all(np.diff(x) > 0)):
        raise ValueError("Invalid or nonmonotonic current curve")
    return x, y


def integral_coulomb(x: np.ndarray, y: np.ndarray, a: float, b: float) -> float:
    """Integrate A against ns converted to s; interpolate only inside the record."""
    if not x[0] <= a < b <= x[-1]:
        raise ValueError("Integration window outside recorded interval")
    mask = (x > a) & (x < b)
    xx = np.r_[a, x[mask], b]
    yy = np.r_[np.interp(a, x, y), y[mask], np.interp(b, x, y)]
    return float(trapezoid(yy, xx * 1e-9))


def analyze(curves: dict[str, dict[str, Any]], receivers: list[str]) -> dict[str, Any]:
    """Charge-weighted effective SEY, not macro-count ratio or mean instantaneous SEY.

    Incident current is positive and emitted-electron current negative in the
    verified CST monitor convention. Zero incident charge has undefined SEY.
    """
    pairs, issues, no_sample = {}, {}, []
    for surface in receivers:
        # Geometry component "/" becomes a result-tree hierarchy separator.
        tree_surface = surface.replace("/", "\\")
        inc_path = f"1D Results\\Collision Information\\Current\\{tree_surface}"
        out_path = f"1D Results\\Emission Information\\Current\\[SEE]\\{tree_surface}"
        hist_path = f"1D Results\\Collision Information\\Energy\\{tree_surface}"
        inc, out = curves.get(inc_path), curves.get(out_path)
        if inc is None and out is None:
            hist = curves.get(hist_path)
            if hist is not None and np.all(np.asarray(hist["y"]) == 0):
                no_sample.append(surface)
            else:
                issues[surface] = "Missing current pair; no zero-collision evidence"
            continue
        if inc is None or out is None:
            # CST does not create a current curve for a zero signal.
            eh = curves.get(f"1D Results\\Emission Information\\Energy\\[SEE]\\{tree_surface}")
            if inc is not None and out is None and eh is not None and np.all(np.asarray(eh["y"]) == 0):
                out = dict(inc, y=np.zeros_like(inc["y"]))
            else:
                issues[surface] = "Missing matching incident/secondary current"
                continue
        try:
            x, y = current_xy(inc)
            t, z = current_xy(out)
            if y.min() < 0 or z.max() > 0:
                raise ValueError("Unexpected current sign; do not abs a net current")
            pairs[surface] = (x, y, t, -z)
        except ValueError as exc:
            issues[surface] = str(exc)
    windows = [(0., 20.), (5., 10.), (10., 15.), (15., 20.), (5., 20.)]
    rows = []
    for a, requested_end in windows:
        # Use a common time interval for the combined result, never extrapolate.
        if not pairs:
            continue
        b = float(min(requested_end, *(min(v[0][-1], v[2][-1]) for v in pairs.values())))
        start = float(max(a, *(max(v[0][0], v[2][0]) for v in pairs.values())))
        if b <= start:
            continue
        qi = qe = 0.
        for surface, (x, y, t, z) in pairs.items():
            inc_q = integral_coulomb(x, y, start, b)
            out_q = integral_coulomb(t, z, start, b)
            qi += inc_q
            qe += out_q
            dt = max(float(np.median(np.diff(x))), float(np.median(np.diff(t))))
            rows.append(dict(surface=surface, start_ns=start, requested_end_ns=requested_end,
                             end_ns=b, window_complete=(start == a and requested_end-b <= 2*dt),
                             incident_C=inc_q, secondary_C=out_q,
                             sey=out_q/inc_q if inc_q > 0 else None))
        rows.append(dict(surface="combined_paired_receivers", start_ns=start,
                         requested_end_ns=requested_end, end_ns=b,
                         window_complete=all(v["window_complete"] for v in rows[-len(pairs):]),
                         incident_C=qi, secondary_C=qe, sey=qe/qi if qi > 0 else None))
    return dict(rows=rows, issues=issues, no_collision_samples=no_sample,
                combined_scope=list(pairs),
                note="Combined SEY covers paired SEE surfaces only, not boundary losses.")
