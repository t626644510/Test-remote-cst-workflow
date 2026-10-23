"""No-CST tests of physical geometry preflight and whole-arc projection."""

import math

import numpy as np
import pytest

from workflows.rfgun_hom_target.geometry import GeometryConstraints, radial_envelope


pytestmark = pytest.mark.no_cst


@pytest.fixture
def parameters():
    return {
        "selfangle2": 45.0, "UpperHeight2": 26.594236426398069,
        "DownHeight2": 4.19529209198384, "Lin2": 12.246956607591006,
        "inner_angle3": 71.240238233223295, "inner_r2": 12.249527232476447,
    }


@pytest.mark.parametrize("radius,angle", [
    (5.44, 0.001), (5.5, 30), (8, 60), (12.25, 71.24), (12, 90),
    (8, 120), (6, 170), (20, 179.999), (60, 35), (1000, 0.05),
])
def test_matches_dense_whole_arc_surface_oracle(radius, angle):
    """Sample the swept surface directly, independently of the closed formula."""
    conductor = 5.43
    phi = np.linspace(0, math.radians(angle), 401)[:, None]
    cross_section = np.linspace(0, 2 * np.pi, 2001)[None, :]
    # mm: actual tube surface projected onto the plane normal to its start axis.
    x = radius * (1 - np.cos(phi)) + conductor * np.cos(phi) * np.cos(cross_section)
    y = conductor * np.sin(cross_section)
    sampled_max = float(np.hypot(x, y).max())
    analytic = radial_envelope(radius, angle, conductor)
    assert analytic >= sampled_max - 1e-10
    assert analytic == pytest.approx(sampled_max, abs=3e-5)


def test_closed_angle_limits_and_quarter_turn():
    assert radial_envelope(12, 0, 5.43) == pytest.approx(5.43)
    assert radial_envelope(12, 90, 5.43) == pytest.approx(math.hypot(12, 5.43))
    assert radial_envelope(12, 180, 5.43) == pytest.approx(24 + 5.43)


@pytest.mark.parametrize("radius,angle,conductor", [
    (5.43, 10, 5.43), (4, 10, 5.43), (12, -1, 5.43),
    (12, 181, 5.43), (12, 10, 0), (float("inf"), 10, 5.43),
    (12, float("nan"), 5.43),
])
def test_radial_envelope_rejects_invalid_domain(radius, angle, conductor):
    with pytest.raises(ValueError):
        radial_envelope(radius, angle, conductor)


def test_initial_point_is_feasible(parameters):
    assert GeometryConstraints().feasible(parameters)


def test_tight_bend_at_90_is_allowed(parameters):
    parameters.update(inner_r2=6.0, inner_angle3=90.0)
    assert parameters["inner_r2"] < 2 * 5.43
    assert GeometryConstraints().feasible(parameters)


@pytest.mark.parametrize("angle", [90.000001, 94.531175, 119.773394, 160.199894])
def test_observed_returning_bends_fail_before_cst(parameters, angle):
    parameters.update(inner_r2=6., inner_angle3=angle)
    assert any("model maximum" in reason for reason in GeometryConstraints().violations(parameters))


def test_model_angle_limit_is_configurable_and_inclusive(parameters):
    parameters.update(inner_r2=6., inner_angle3=100.)
    assert GeometryConstraints(maximum_bend_angle_deg=100.).feasible(parameters)
    assert not GeometryConstraints(maximum_bend_angle_deg=99.).feasible(parameters)


def test_search_bounds_are_not_geometry_constraints(parameters):
    parameters.update(inner_r2=60, inner_angle3=30, selfangle2=270, UpperHeight2=60)
    assert GeometryConstraints().feasible(parameters)


def test_flange_clearance_boundary(parameters):
    radius = parameters["inner_r2"]
    angle = parameters["inner_angle3"]
    envelope = radial_envelope(radius, angle, 5.43)
    assert GeometryConstraints(flange_radius_mm=envelope + 0.01).feasible(parameters)
    assert not GeometryConstraints(flange_radius_mm=envelope + 0.0099).feasible(parameters)


def test_length_separation_boundary(parameters):
    parameters.update(Lin2=10, DownHeight2=9.99)
    assert GeometryConstraints().feasible(parameters)
    parameters["DownHeight2"] = 9.999
    assert not GeometryConstraints().feasible(parameters)
    parameters["DownHeight2"] = 10
    assert not GeometryConstraints().feasible(parameters)


@pytest.mark.parametrize("name,minimum", [("DownHeight2", 2.), ("UpperHeight2", 5.)])
def test_model_height_floor_and_clearance(parameters, name, minimum):
    for value in (minimum - .1, minimum, minimum + .009):
        parameters[name] = value
        assert any(name in reason for reason in GeometryConstraints().violations(parameters))
    parameters[name] = minimum + .01
    assert GeometryConstraints().feasible(parameters)


@pytest.mark.parametrize("projection,feasible", [(5.42, False), (5.43, False),
                                                   (5.439, False), (5.441, True)])
def test_centerline_lower_limit_is_distinct_from_outer_envelope(parameters, projection, feasible):
    # mm: this entire family fits the flange, but only the last clears the
    # empirical topology floor. Inverse cosine creates the independent input.
    radius = 12.
    angle = math.degrees(math.acos(1 - projection / radius))
    parameters.update(inner_r2=radius, inner_angle3=angle)
    assert 5.43 < radial_envelope(radius, angle, 5.43) < 24.99
    assert GeometryConstraints().feasible(parameters) is feasible


def test_model_floors_are_configurable(parameters):
    parameters.update(DownHeight2=1., UpperHeight2=3., inner_r2=12., inner_angle3=30.)
    assert not GeometryConstraints().feasible(parameters)
    assert GeometryConstraints(minimum_down_height_mm=.5, minimum_upper_height_mm=2.,
                               minimum_centerline_projection_mm=1.).feasible(parameters)


@pytest.mark.parametrize("radius,angle", [(17.732021786440654, 6.612681182910407),
                                         (5.509774642297066, 13.295235629140038)])
def test_observed_small_bends_are_prescreened(parameters, radius, angle):
    parameters.update(inner_r2=radius, inner_angle3=angle)
    assert any("centerline projection" in reason for reason in GeometryConstraints().violations(parameters))


@pytest.mark.parametrize("value", [0, 180, -1, 181])
def test_degenerate_or_reversed_bend_is_infeasible(parameters, value):
    parameters["inner_angle3"] = value
    assert not GeometryConstraints().feasible(parameters)


@pytest.mark.parametrize("value", [5.43, 5.435, 0, -6])
def test_radius_clearance_is_enforced(parameters, value):
    parameters["inner_r2"] = value
    assert not GeometryConstraints().feasible(parameters)


@pytest.mark.parametrize("value", [None, "bad", float("nan"), float("inf")])
def test_invalid_parameter_is_reported(parameters, value):
    parameters["UpperHeight2"] = value
    assert "UpperHeight2" in GeometryConstraints().violations(parameters)[0]


def test_missing_parameter_is_reported(parameters):
    del parameters["selfangle2"]
    assert "selfangle2" in GeometryConstraints().violations(parameters)[0]


@pytest.mark.parametrize("kwargs", [
    {"clearance_mm": 0}, {"clearance_mm": -1}, {"conductor_radius_mm": 0},
    {"flange_radius_mm": 5.43}, {"fillet_radius_mm": float("nan")},
    {"minimum_down_height_mm": -1}, {"minimum_upper_height_mm": float("inf")},
    {"minimum_centerline_projection_mm": 25},
    {"maximum_bend_angle_deg": 0}, {"maximum_bend_angle_deg": 180},
    {"maximum_bend_angle_deg": float("nan")},
])
def test_invalid_constraints_fail_early(kwargs):
    with pytest.raises(ValueError):
        GeometryConstraints(**kwargs)
