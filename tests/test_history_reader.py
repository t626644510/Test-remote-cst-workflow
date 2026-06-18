import json

import pytest

from cst_history_extractor.history_reader import read_cst_file_history


pytestmark = pytest.mark.no_cst


def test_cst_file_reads_unpacked_modelhistory_json(tmp_path):
    cst_file = tmp_path / "Example.cst"
    cst_file.write_bytes(b"not a real cst for unit tests")
    model_history = tmp_path / "Example" / "Model" / "3D" / "ModelHistory.json"
    model_history.parent.mkdir(parents=True)
    model_history.write_text(
        json.dumps(
            {
                "general": {
                    "version": "2026.0",
                    "project_type": "MWS",
                    "length": "mm",
                    "frequency": {"unit": "MHz"},
                },
                "history": [
                    {
                        "caption": "define units",
                        "version": "2026.0|35.0.0|20250829",
                        "hidden": False,
                        "type": "vba",
                        "code": [
                            "With Units",
                            '     .SetUnit "Length", "mm"',
                            "End With",
                        ],
                    },
                    {
                        "caption": "change solver type",
                        "version": "2026.0|35.0.0|20250829",
                        "hidden": False,
                        "type": "vba",
                        "code": ['ChangeSolverType "HF Frequency Domain"'],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    source = read_cst_file_history(cst_file)

    assert source.source_type == "modelhistory_json"
    assert source.source_path == str(model_history)
    assert len(source.history_items) == 2
    assert source.history_items[0].raw_name == "define units"
    assert source.history_items[0].parser_strategy == "modelhistory_json"
    assert "' History Item: define units" in source.raw_text
    assert source.metadata["history_entry_count"] == 2
    assert source.metadata["history_entry_fields"] == [
        "caption",
        "code",
        "hidden",
        "type",
        "version",
    ]
    assert source.cst_probe["model_history_path"] == str(model_history)
