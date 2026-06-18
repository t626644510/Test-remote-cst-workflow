from pathlib import Path

import pytest

from cst_history_extractor.macro_parser import parse_history_text


pytestmark = pytest.mark.no_cst


def test_parse_add_to_history_continuation_block():
    text = '''Sub Main()
AddToHistory "set units", _
"With Units" & vbCrLf & _
"     .SetUnit ""Length"", ""mm""" & vbCrLf & _
"End With"
End Sub
'''

    items = parse_history_text(text)

    assert len(items) == 1
    assert items[0].raw_name == "set units"
    assert items[0].parser_strategy == "add_to_history"
    assert "With Units" in items[0].macro_body
    assert '.SetUnit "Length", "mm"' in items[0].macro_body


def test_parse_comment_delimited_history_blocks():
    text = """' History Item: set project units
With Units
     .SetUnit "Length", "mm"
End With

' History Item: solver setup
ChangeSolverType "Eigenmode"
"""

    items = parse_history_text(text)

    assert [item.raw_name for item in items] == [
        "set project units",
        "solver setup",
    ]
    assert items[0].source_line_start == 1
    assert items[1].parser_strategy == "comment_delimited"


def test_parse_with_blocks_when_no_history_headers():
    text = """With Mesh
     .LinesPerWavelength "20"
End With

With Monitor
     .FieldType "Efield"
End With
"""

    items = parse_history_text(text)

    assert len(items) == 2
    assert items[0].raw_name == "With Mesh"
    assert items[1].raw_name == "With Monitor"
    assert all(item.parser_strategy == "with_block" for item in items)


def test_example_history_fixture_parses_expected_blocks():
    text = Path("examples/example_history.bas").read_text(encoding="utf-8")

    items = parse_history_text(text, source_name="example_history.bas")

    assert len(items) == 12
    assert items[0].raw_name == "set project units"
    assert items[-1].raw_name == "export 3d fields"
