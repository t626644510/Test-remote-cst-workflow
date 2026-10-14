"""Retry decisions for known numerical guards, including legacy worker replies.

This module changes scheduling only. The numerical backend and its fingerprint
remain unchanged, so completed axis fields can still pair with a later X solve.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class FailurePolicy:
    """Whether identical inputs may be retried; unknown failures stay bounded."""

    category: str = 'unclassified'
    retry_identical: bool = True
    numerical_steps_started: bool | None = None
    coupling_bound: float | None = None
    guard_limit: float | None = None


def classify_failure(phase: str, traceback_text: str) -> FailurePolicy:
    """Recognize the existing SurfaceCopper initializer guard, without CUDA.

    Require both its final raise site and exact terminal RuntimeError message.
    This also covers saved replies produced before structured policies existed;
    unrelated RuntimeErrors retain the configured bounded retry policy.
    The coupling bound and 0.5 guard are dimensionless, not impedance limits.
    """
    if phase != 'solve':
        return FailurePolicy()
    frames = re.findall(r'^  File "([^"]+)", line \d+, in (\S+)\s*$',
                        traceback_text, re.MULTILINE)
    if not frames:
        return FailurePolicy()
    path, function = frames[-1]
    if (not path.replace('\\', '/').endswith('/rfgun_wakis/backend/surface_copper.py')
            or function != '__init__'):
        return FailurePolicy()
    message = re.fullmatch(r'RuntimeError: Surface explicit coupling bound too large: (\S+)',
                           traceback_text.rstrip().splitlines()[-1])
    if message is None:
        return FailurePolicy()
    try:
        bound = float(message[1])
    except ValueError:
        return FailurePolicy()
    if not bound >= 0.5:
        return FailurePolicy()
    return FailurePolicy(category='surface_coupling_initialization_guard', retry_identical=False,
                         numerical_steps_started=False,
                         coupling_bound=bound if math.isfinite(bound) else None, guard_limit=0.5)
