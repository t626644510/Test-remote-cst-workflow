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
ANTENNA1_NAMES = ("selfangle1", "UpperHeight1", "DownHeight1", "Lin1", "inner_angle", "inner_r")
FORK_NAMES = ("FolkHeight", "FolkHeight2")


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
    """Preflight settings in mm (bend angle in degrees), separate from search bounds.

    A positive clearance enforces strict physical separation. The configured
    fillet radius is retained as geometry provenance, not added to the minimum
    bend radius: R >= a + fillet is not a proven necessary condition. Actual
    fillet validity must be established by rebuilding the candidate in CST.
    """

    conductor_radius_mm: float = 5.43
    flange_radius_mm: float = 25.0
    clearance_mm: float = 0.01
    fillet_radius_mm: float = 5.43
    minimum_down_height_mm: float = 2.0
    minimum_upper_height_mm: float = 5.0
    minimum_centerline_projection_mm: float = 5.43
    maximum_bend_angle_deg: float = 90.0
    antenna_count: int = 1
    minimum_fork_length_mm: float = 5.43
    bend_segments: int = 1

    def __post_init__(self) -> None:
        if type(self.bend_segments) is not int or self.bend_segments not in (1, 2):
            raise ValueError("bend_segments must be integer 1 or 2")
        for name in (
            "conductor_radius_mm", "flange_radius_mm", "clearance_mm",
            "fillet_radius_mm", "minimum_down_height_mm",
            "minimum_upper_height_mm", "minimum_centerline_projection_mm", "minimum_fork_length_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive (mm)")
        if self.flange_radius_mm <= self.conductor_radius_mm + self.clearance_mm:
            raise ValueError("Flange radius must exceed conductor radius plus clearance")
        if self.minimum_centerline_projection_mm + 2 * self.clearance_mm >= self.flange_radius_mm:
            raise ValueError("Minimum centerline projection leaves no flange clearance")
        if not math.isfinite(self.maximum_bend_angle_deg) or not 0 < self.maximum_bend_angle_deg < 180:
            raise ValueError("Maximum bend angle must lie strictly between 0 and 180 degrees")
        if type(self.antenna_count) is not int or self.antenna_count not in (1, 2):
            raise ValueError("antenna_count must be integer 1 or 2")

    def violations(self, parameters: Mapping[str, float]) -> list[str]:
        """Check the configured six- or fourteen-coordinate model, in mm/degrees.

        Search bounds, including selfangle2 and UpperHeight2 upper limits, belong to
        campaign configuration. Model-specific height/projection floors protect
        the topology observed by the user. All configured values must be present
        and finite. Antenna 1's signed bend dimensions must be negative; they are
        reflected to positive magnitudes for the same physical constraints.
        """
        failures = []
        values = {}
        names = PARAMETER_NAMES + (ANTENNA1_NAMES + FORK_NAMES if self.antenna_count == 2 else ())
        for name in names:
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
        failures.extend(self._antenna2_violations(values))
        if self.antenna_count == 2:
            if values["inner_angle"] >= 0 or values["inner_r"] >= 0:
                failures.append("Antenna 1 inner_angle and inner_r must both be negative")
            # Reflect the signed CST coordinates; never silently accept wrong
            # positive signs by using abs(). Other lengths retain their signs.
            reflected = dict(zip(PARAMETER_NAMES, (values["selfangle1"], values["UpperHeight1"],
                values["DownHeight1"], values["Lin1"], -values["inner_angle"], -values["inner_r"])))
            mapping = dict(zip(PARAMETER_NAMES, ANTENNA1_NAMES))
            for reason in self._antenna2_violations(reflected):
                for source, target in mapping.items():
                    reason = reason.replace(source, target)
                failures.append("Antenna 1: " + reason)
            for name in FORK_NAMES:
                # User specified an inclusive floor, with no extra clearance.
                if values[name] < self.minimum_fork_length_mm:
                    failures.append(f"{name} must be at least {self.minimum_fork_length_mm:g} mm")
        return failures

    def _antenna2_violations(self, values: Mapping[str, float]) -> list[str]:
        """Shared one-bend checks in positive radius/angle coordinates (mm/deg)."""
        failures = []
        if values["Lin2"] <= 0:
            failures.append("Lin2 must be positive (mm)")
        for name, minimum in (("DownHeight2", self.minimum_down_height_mm),
                              ("UpperHeight2", self.minimum_upper_height_mm)):
            if values[name] < minimum + self.clearance_mm:
                failures.append(f"{name} must exceed model minimum {minimum:g} mm by clearance_mm")
        if values["Lin2"] < values["DownHeight2"] + self.clearance_mm:
            failures.append("Lin2 - DownHeight2 must be at least clearance_mm")
        radius = values["inner_r2"]
        angle = values["inner_angle3"]
        if radius < self.conductor_radius_mm + self.clearance_mm:
            failures.append("inner_r2 - conductor_radius_mm must be at least clearance_mm")
        if not 0 < angle < 180:
            failures.append("inner_angle3 must lie strictly between 0 and 180 degrees")
        if angle > self.maximum_bend_angle_deg:
            failures.append(f"inner_angle3 exceeds model maximum {self.maximum_bend_angle_deg:g} degrees")
        if radius > self.conductor_radius_mm and 0 < angle < 180:
            # mm, degrees: same centerline displacement as WF2/WF3's 1-cos
            # constraint. Its lower bound protects this template's face topology;
            # it is distinct from the full swept-surface upper envelope below.
            projection = radius * (1 - math.cos(math.radians(angle)))
            if self.bend_segments == 2:
                # User's double-bend template: P=2R(1-cos(theta)), mm/degrees.
                # Inclusive centerline bounds replace the single swept-arc envelope.
                # 1e-10 mm permits only inverse-trigonometry roundoff at endpoints.
                if not self.minimum_centerline_projection_mm - 1e-10 <= 2 * projection <= self.flange_radius_mm + 1e-10:
                    failures.append("Double-bend projection is outside inclusive model bounds (mm)")
                return failures
            if projection < self.minimum_centerline_projection_mm + self.clearance_mm:
                failures.append("Bend centerline projection is below model minimum plus clearance (mm)")
            extent = radial_envelope(radius, angle, self.conductor_radius_mm)
            if extent + self.clearance_mm > self.flange_radius_mm:
                failures.append("Swept conductor radial envelope exceeds flange clearance (mm)")
        return failures

    def feasible(self, parameters: Mapping[str, float]) -> bool:
        """Whether all analytic preflight checks pass; CST rebuild is still required."""
        return not self.violations(parameters)
