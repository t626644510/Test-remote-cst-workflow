from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from workflows.rfgun_tolerance.campaign_cli import (
    CampaignDatabase,
    DEFAULT_ACCEPTANCE_RULES,
    parse_database_spec,
    run_cli,
)
from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord,
    ParameterIdentity,
    RawEvaluationPayload,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig,
    SQLiteEvaluationDatabase,
)


def test_parse_database_spec() -> None:
    result = parse_database_spec(r"7.5=runs\tolerance\level.db")

    assert result == CampaignDatabase(
        level_um=7.5,
        path=Path(r"runs\tolerance\level.db"),
    )


@pytest.mark.parametrize(
    "value",
    ["", "3", "=file.db", "bad=file.db", "0=file.db", "-2=file.db"],
)
def test_parse_database_spec_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_database_spec(value)


def test_run_cli_requires_two_databases(tmp_path: Path, capsys) -> None:
    database = tmp_path / "one.db"
    database.write_bytes(b"placeholder")
    config = tmp_path / "config.yaml"
    config.write_text("tolerance:\n  parameters: []\n", encoding="utf-8")

    exit_code = run_cli(
        [
            "--config",
            str(config),
            "--db",
            f"3={database}",
        ]
    )

    assert exit_code == 2
    assert "at least two" in capsys.readouterr().err


def test_run_cli_writes_cross_level_report(tmp_path: Path) -> None:
    first = tmp_path / "3um.db"
    second = tmp_path / "5um.db"
    _write_database(first, level_scale=1.0)
    _write_database(second, level_scale=2.0)
    config = tmp_path / "config.yaml"
    config.write_text(
        """
tolerance:
  parameters:
    - name: x
      nominal: 1.0
      tolerance_abs: 0.003
      unit: mm
      enabled: true
""".lstrip(),
        encoding="utf-8",
    )
    output = tmp_path / "campaign.md"

    exit_code = run_cli(
        [
            "--config",
            str(config),
            "--db",
            f"3={first}",
            "--db",
            f"5={second}",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = output.read_text(encoding="utf-8")
    assert "# Tolerance Sweep Analysis Report" in report
    assert "3 um" in report
    assert "5 um" in report
    assert "Per-Parameter Tolerance Budget" in report


def test_default_acceptance_rules_use_fractional_failure_rates() -> None:
    assert {
        rule["max_failure_rate"]
        for rule in DEFAULT_ACCEPTANCE_RULES.values()
    } == {0.20}
    assert DEFAULT_ACCEPTANCE_RULES["resonant_freq"]["max_mean"] == 1.0
    assert "target_mean" not in DEFAULT_ACCEPTANCE_RULES["coupling_beta"]


def _write_database(path: Path, *, level_scale: float) -> None:
    database = SQLiteEvaluationDatabase(
        EvaluationDatabaseConfig(path=str(path), enabled=True)
    )
    database.open()
    try:
        for index in range(6):
            offset = (index - 2.5) * 0.001 * level_scale
            metrics = {
                "resonant_freq": 11.424 + offset,
                "coupling_beta": 2.0 + offset * 10,
                "q0": 18000.0 - offset * 1000,
                "peak_e_field": 90_000.0 + offset * 100,
                "field_flatness": abs(offset),
                "max_modified_poynting": 4.0e12 + offset * 1.0e10,
                "pulsed_heating": 25.0 + offset * 10,
            }
            database.insert_final_record(
                EvaluationDatabaseRecord(
                    parameter_identity=ParameterIdentity(
                        param_names=["x"],
                        values=[1.0 + offset],
                    ),
                    status="success",
                    raw_payload=RawEvaluationPayload(
                        raw_metrics=metrics,
                        objective_values=metrics,
                    ),
                    source="test",
                )
            )
    finally:
        database.close()
