"""Analytic preflight constraints for the single-bend HOM antenna.

Lengths are millimetres and angles are degrees. These checks describe an ideal
circular tube swept along one circular arc. They do not certify CST face IDs,
Boolean operations, fillet construction, or clearance from the cavity wall.
"""

from dataclasses import dataclass
import math
from typing import Mapping


PARAMETER_NAMES = (
    "selfangle2", "UpperHeight2", "DownHeight2", "Lin2",
    "inner_angle3", "inner_r2",
)


def radial_envelope(
    radius_mm: float, angle_deg: float, conductor_radius_mm: float,
) -> float:
    """Return the exact maximum radial projection of the entire ideal tube.

    The reference axis is the straight antenna axis. The bend centre-line
    radius R must exceed the circular conductor radius a; the bend angle may
    include the closed limits 0 and 180 degrees for evaluating boundaries.
    Fillets are not part of this ideal swept-solid calculation.

    At arc angle phi, d = R*(1-cos(phi)). A cross-section perimeter point has
    radial distance squared d**2 + a**2 + 2*d*a*cos(phi)*t
    - a**2*sin(phi)**2*t**2, where -1 <= t <= 1. Maximising this concave
    quadratic gives the three expressions below. Their dependence on phi is
    respectively R-(R-a)*cos(phi), hypot(a, R*tan(phi/2)), and
    R-(R+a)*cos(phi). Each is nondecreasing on [0, pi] for R>a, and the
    expressions agree at their transitions. Consequently the end section
    gives the maximum over the WHOLE arc, including bends beyond 90 degrees.
    """
    radius, angle, conductor = map(
        float, (radius_mm, angle_deg, conductor_radius_mm),
    )
    if not all(math.isfinite(v) for v in (radius, angle, conductor)):
        raise ValueError("Geometry dimensions and angle must be finite")
    if conductor <= 0 or radius <= conductor:
        raise ValueError("Require bend radius > conductor radius > 0 mm")
    if not 0 <= angle <= 180:
        raise ValueError("Bend angle must lie in [0, 180] degrees")
    phi = math.radians(angle)
    cosine = math.cos(phi)
    if (radius - conductor) * cosine >= conductor:
        # The maximum lies on the outer in-plane cross-section edge (t=1).
        return radius * (1 - cosine) + conductor * cosine
    if (radius + conductor) * cosine <= -conductor:
        # A returning arc has its radial maximum at the opposite edge (t=-1).
        return radius * (1 - cosine) - conductor * cosine
    # The maximum lies between the in-plane edges, not at d+a or d+a*cos(phi).
    return math.hypot(conductor, radius * math.tan(phi / 2))


@dataclass(frozen=True)
class GeometryConstraints:
    """Physical preflight settings in mm, independent of search-box bounds.

    A positive clearance enforces strict physical separation. The configured
    fillet radius is retained as geometry provenance, not added to the minimum
    bend radius: R >= a + fillet is not a proven necessary condition. Actual
    fillet validity must be established by rebuilding the candidate in CST.
    """

    conductor_radius_mm: float = 5.43
    flange_radius_mm: float = 25.0
    clearance_mm: float = 0.01
    fillet_radius_mm: float = 5.43

    def __post_init__(self) -> None:
        for name in (
            "conductor_radius_mm", "flange_radius_mm", "clearance_mm",
            "fillet_radius_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive (mm)")
        if self.flange_radius_mm <= self.conductor_radius_mm + self.clearance_mm:
            raise ValueError("Flange radius must exceed conductor radius plus clearance")

    def violations(self, parameters: Mapping[str, float]) -> list[str]:
        """Describe failed physical checks for canonical six-parameter values.

        Search bounds, including selfangle2 and UpperHeight2 limits, belong to
        campaign configuration. All six values must nevertheless be present
        and finite. Unknown extra keys are harmless.
        """
        failures = []
        values = {}
        for name in PARAMETER_NAMES:
            try:
                value = float(parameters[name])
            except (KeyError, TypeError, ValueError, OverflowError):
                failures.append(f"{name} is missing or is not a finite number")
                continue
            if not math.isfinite(value):
                failures.append(f"{name} is not a finite number")
                continue
            values[name] = value
        if failures:
            return failures
        if values["Lin2"] <= 0:
            failures.append("Lin2 must be positive (mm)")
        if values["Lin2"] < values["DownHeight2"] + self.clearance_mm:
            failures.append("Lin2 - DownHeight2 must be at least clearance_mm")
        radius = values["inner_r2"]
        angle = values["inner_angle3"]
        if radius < self.conductor_radius_mm + self.clearance_mm:
            failures.append("inner_r2 - conductor_radius_mm must be at least clearance_mm")
        if not 0 < angle < 180:
            failures.append("inner_angle3 must lie strictly between 0 and 180 degrees")
        if radius > self.conductor_radius_mm and 0 < angle < 180:
            extent = radial_envelope(radius, angle, self.conductor_radius_mm)
            if extent + self.clearance_mm > self.flange_radius_mm:
                failures.append("Swept conductor radial envelope exceeds flange clearance (mm)")
        return failures

    def feasible(self, parameters: Mapping[str, float]) -> bool:
        """Whether all analytic preflight checks pass; CST rebuild is still required."""
        return not self.violations(parameters)
