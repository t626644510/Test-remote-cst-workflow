"""Bounds for finite TRK endpoints: time ns and absolute macrocharge C.

Only native counts can establish collisions hidden at a rounded terminal time.
No trajectory ID is invented; charge bounds use actual eligible track weights.
"""
from __future__ import annotations
from typing import Any
import numpy as np


def terminal_collision_bounds(a: np.ndarray, stats: dict[str, Any]) -> dict[str, Any] | None:
    """Return native-count-constrained bounds, or None for exact endpoints."""
    a = np.atleast_2d(a)
    if a.shape[1] != 8 or not len(a) or not np.all(np.isfinite(a)):
        raise ValueError('Invalid trajectory endpoints')
    if not stats.get('final'):
        return None
    terminal = a[:, 4] == a[:, 4].max()
    missing = int(terminal.sum()) - int(stats['final'])
    if missing == 0:
        return None
    required = ('collided', 'into_solid', 'passed', 'blocked', 'dying', 'ionization')
    if missing < 0 or not all(k in stats for k in required):
        raise ValueError('Terminal survivor count disagrees with solver')
    into = (a[:, 7] == 1) & ~terminal
    collisions = ~terminal & ~into
    candidates = terminal & (a[:, 7] > 1)
    if (missing > int(candidates.sum()) or int(collisions.sum()) + missing != stats['collided']
            or int(into.sum()) != stats['into_solid']
            or np.any(a[into, 3] != a[into, 4])
            or any(stats[k] for k in ('passed', 'blocked', 'dying', 'ionization'))):
        raise ValueError('Unresolved trajectory endpoint classification; no bounded SEY')
    weights = np.sort(np.abs(a[candidates, 5]))
    return dict(ambiguous_terminal_collisions=missing,
                collision_charge_lower_C=float(weights[:missing].sum()),
                collision_charge_upper_C=float(weights[-missing:].sum()),
                terminal_time_ns=float(a[:, 4].max()),
                candidate_count=int(candidates.sum()),
                definition='Native collision/survivor counts constrain the number; track identities are unknown')


def adjusted_statistics(stats: dict[str, Any], bounds: dict[str, Any]) -> dict[str, Any]:
    """Internal exact-classification view, never presented as native statistics."""
    n = bounds['ambiguous_terminal_collisions']
    return dict(stats, final=stats['final'] + n, collided=stats['collided'] - n)
