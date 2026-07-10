"""2D profile self-intersection checks."""

from __future__ import annotations


def profile_is_simple(profile_points: list[tuple[float, float]]) -> bool:
    """Return true when sampled r-z segments do not cross non-adjacent segments."""
    segments = list(zip(profile_points, profile_points[1:]))
    for i, left in enumerate(segments):
        for j, right in enumerate(segments):
            if abs(i - j) <= 1:
                continue
            if i == 0 and j == len(segments) - 1:
                continue
            if _segments_intersect(left[0], left[1], right[0], right[1]):
                return False
    return True


def all_r_nonnegative(profile_points: list[tuple[float, float]]) -> bool:
    """Return true when all profile radii are on the positive side of the axis."""
    return all(radius >= 0.0 for _, radius in profile_points)


def _segments_intersect(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    eps = 1e-9

    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
        return (
            min(p[0], r[0]) - eps <= q[0] <= max(p[0], r[0]) + eps
            and min(p[1], r[1]) - eps <= q[1] <= max(p[1], r[1]) + eps
        )

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if o1 * o2 < -eps and o3 * o4 < -eps:
        return True
    if abs(o1) <= eps and on_segment(a, c, b):
        return True
    if abs(o2) <= eps and on_segment(a, d, b):
        return True
    if abs(o3) <= eps and on_segment(c, a, d):
        return True
    if abs(o4) <= eps and on_segment(c, b, d):
        return True
    return False
