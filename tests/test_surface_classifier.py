import pytest

from step_feature_assistant.surface_classifier import (
    axis_relation,
    classify_step_surface_type,
    face_fingerprint,
    principal_axis,
)


pytestmark = pytest.mark.no_cst


def test_classifies_common_step_surface_types():
    assert classify_step_surface_type("CYLINDRICAL_SURFACE") == "cylinder"
    assert classify_step_surface_type("TOROIDAL_SURFACE") == "torus"
    assert classify_step_surface_type("B_SPLINE_SURFACE_WITH_KNOTS") == "bspline"
    assert classify_step_surface_type("PRIVATE_SURFACE") == "unknown"


def test_axis_relation_detects_z_axisymmetric_cylinder():
    relation = axis_relation(
        points=[(5.0, 0.0, 0.0), (0.0, 5.0, 10.0), (-5.0, 0.0, 10.0)],
        model_axis="z",
        surface_type="cylinder",
        placement_axis=(0.0, 0.0, 1.0),
        placement_origin=(0.0, 0.0, 0.0),
        declared_radius=5.0,
    )

    assert relation["is_axisymmetric"] is True
    assert relation["radius_mean"] == pytest.approx(5.0)
    assert relation["z_range"] == [0.0, 10.0]


def test_principal_axis_and_fingerprint_are_stable():
    assert principal_axis((0.0, 0.0, -1.0)) == "z"

    fp1 = face_fingerprint(
        "plane",
        10.00001,
        (1.0, 2.0, 3.0),
        {"xmin": 0.0, "xmax": 2.0, "ymin": 1.0, "ymax": 3.0, "zmin": 3.0, "zmax": 3.0},
        edge_count=4,
    )
    fp2 = face_fingerprint(
        "plane",
        10.00002,
        (1.0, 2.0, 3.0),
        {"xmin": 0.0, "xmax": 2.0, "ymin": 1.0, "ymax": 3.0, "zmin": 3.0, "zmax": 3.0},
        edge_count=4,
    )
    assert fp1 == fp2
