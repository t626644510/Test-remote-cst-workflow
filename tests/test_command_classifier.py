import pytest

from cst_history_extractor.command_classifier import classify_history_items
from cst_history_extractor.macro_parser import HistoryItem
from cst_history_extractor.macro_parser import parse_history_text


pytestmark = pytest.mark.no_cst


def test_classifier_recognizes_core_command_families():
    text = """' History Item: set units
With Units
     .SetUnit "Length", "mm"
End With

' History Item: discrete port
With DiscretePort
     .PortNumber "1"
     .Create
End With

' History Item: eigenmode solver settings
ChangeSolverType "Eigenmode"
With EigenmodeSolver
     .Modes "5"
End With

' History Item: unknown macro
DoSomethingPrivate "value"
"""

    commands = classify_history_items(parse_history_text(text))

    assert (commands[0].category, commands[0].subcategory) == ("project", "units")
    assert (commands[1].category, commands[1].subcategory) == ("ports", "discrete_port")
    assert (commands[2].category, commands[2].subcategory) == ("solver", "eigenmode_solver")
    assert (commands[3].category, commands[3].subcategory) == ("unknown", "unclassified")
    assert commands[2].confidence > 0.9
    assert commands[3].confidence == 0.0


def test_geometry_with_material_property_stays_geometry():
    text = """With Brick
     .Name "cavity"
     .Component "component1"
     .Material "PEC"
     .Create
End With
"""

    commands = classify_history_items(parse_history_text(text))

    assert len(commands) == 1
    assert commands[0].category == "geometry"
    assert commands[0].subcategory == "primitive_creation"


def test_common_modelhistory_geometry_details_are_not_unknown():
    items = [
        HistoryItem(1, "blend edges", 'Solid.BlendEdge "chamferW"', 0, 0, "modelhistory_json", ""),
        HistoryItem(2, "change component", 'Solid.ChangeComponent "component1:solid1", "component3"', 0, 0, "modelhistory_json", ""),
        HistoryItem(3, "trim curves", 'With TrimCurves\n  .Reset\n  .Curve "curve1"\n  .Trim\nEnd With', 0, 0, "modelhistory_json", ""),
        HistoryItem(4, "delete curve item", 'Curve.DeleteCurveItem "curve1", "polygon1"', 0, 0, "modelhistory_json", ""),
    ]

    commands = classify_history_items(items)

    assert [command.subcategory for command in commands] == [
        "fillet_chamfer",
        "component_solid_management",
        "boolean",
        "component_solid_management",
    ]
    assert all(command.category == "geometry" for command in commands)


def test_modelhistory_generic_port_is_classified_as_port():
    item = HistoryItem(
        1,
        "define port: 1",
        'With Port\n  .PortNumber "1"\n  .Create\nEnd With',
        0,
        0,
        "modelhistory_json",
        "",
    )

    command = classify_history_items([item])[0]

    assert (command.category, command.subcategory) == ("ports", "waveguide_port")


def test_named_coaxial_solid_pick_does_not_become_port():
    item = HistoryItem(
        1,
        "pick face",
        'Pick.PickFaceFromId "fpc:coaxial", "12"',
        0,
        0,
        "modelhistory_json",
        "",
    )

    command = classify_history_items([item])[0]

    assert (command.category, command.subcategory) == ("geometry", "face_or_pick_operation")


def test_result_storage_is_not_misclassified_as_project_parameter():
    item = HistoryItem(
        1,
        "set result storage properties",
        'With ResultStorage\n  .Result "1D Results\\S-Parameters\\", "False"\nEnd With',
        0,
        0,
        "modelhistory_json",
        "",
    )

    command = classify_history_items([item])[0]

    assert (command.category, command.subcategory) == ("results", "result_template")
