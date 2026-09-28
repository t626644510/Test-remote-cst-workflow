"""Offline report regression tests: units, diagnostic honesty, and evidence links."""
import copy
import csv
import json
from pathlib import Path

import pytest

from workflows.rfgun_hom_target.config import (
    PARAMETER_DEFAULTS, ParameterConfig, PathsConfig, PhysicsConfig, WorkflowConfig,
)
from workflows.rfgun_hom_target.reporting import mode_report_lines
from workflows.rfgun_hom_target.search import Campaign
from workflows.rfgun_hom_target.storage import CampaignStore


pytestmark = pytest.mark.no_cst


def mode(number=1, frequency=1040e6, impedance=90000., *, valid=True):
    return dict(mode_number=number, frequency_hz=frequency, q_loaded=500.,
        quality_ok=valid, quality_reasons=[] if valid else ["overlapping_mode_linewidths"],
        metrics=dict(rq_principal_ohm_per_m=180., impedance_x_ohm_per_m=30000.,
            impedance_y_ohm_per_m=80000., impedance_principal_ohm_per_m=impedance,
            principal_angle_deg=35., quality_ok=valid,
            quality_reasons=[] if valid else ["gradient_crosscheck_failed"]))


def record(tmp_path, rows, *, valid=True, identity="evaluation_0000"):
    return dict(id=identity, status="valid" if valid else "quality_failed", objective=.5,
        worst=90000. if valid else None, parameters={}, attempt_dir=str(tmp_path / identity),
        modes=dict(modes=rows, quality_ok=valid, quality_reasons=[]))


def render(tmp_path, records=(), best=None, pending=None, threshold=125000.):
    state = dict(records=list(records), pending=pending)
    report = dict(best=best, threshold_ohm_per_m=threshold)
    text = "\n".join(mode_report_lines(tmp_path, report, state, (1030., 1060.)))
    with (tmp_path / "modes.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return text, rows


def test_best_valid_includes_every_window_mode_sorted_with_correct_units(tmp_path):
    best = record(tmp_path, [mode(8, 1055e6, 130000.), mode(2, 1030e6),
                             mode(3, 1060e6), mode(99, 1060.001e6)])
    later_failure = record(tmp_path, [mode(77)], valid=False, identity="evaluation_0001")
    before = copy.deepcopy(best)
    text, rows = render(tmp_path, [best, later_failure], best)
    assert [row["mode"] for row in rows] == ["2", "8", "3"]
    assert rows[0]["frequency_mhz"] == "1030.0"
    assert rows[0]["total_q"] == "500.0"
    assert rows[0]["rq_principal_ohm_per_m"] == "180.0"
    assert rows[0]["zx_kohm_per_m"] == "30.0"
    assert rows[0]["zy_kohm_per_m"] == "80.0"
    assert rows[0]["zmax_kohm_per_m"] == "90.0"
    assert rows[0]["principal_angle_deg"] == "35.0"
    assert rows[0]["threshold_status"] == "meets_threshold"
    assert rows[1]["threshold_status"] == "above_threshold"
    assert all(row["threshold_kohm_per_m"] == "125.0" for row in rows)
    assert "125 kΩ/m" in text and "R/Qmax (Ω/m)" in text
    assert "evaluation_0001" not in text
    assert best == before


def test_latest_failed_diagnostics_keep_values_without_claiming_pass(tmp_path):
    first = record(tmp_path, [mode(1)], valid=False)
    last = record(tmp_path, [mode(2, impedance=70000., valid=False)], valid=False,
                  identity="evaluation_0001")
    text, rows = render(tmp_path, [first, last])
    assert [row["mode"] for row in rows] == ["2"]
    assert rows[0]["zmax_kohm_per_m"] == "70.0"
    assert rows[0]["quality_status"] == "invalid_or_unverified"
    assert rows[0]["threshold_status"] == "undetermined"
    assert "gradient_crosscheck_failed" in rows[0]["quality_reasons"]
    assert "overlapping_mode_linewidths" in rows[0]["quality_reasons"]
    assert "Diagnostic only" in text and "compliance is undetermined" in text
    assert "meets_threshold" not in text


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf")])
def test_missing_or_nonfinite_impedance_is_blank_and_never_zero_or_pass(tmp_path, missing):
    item = mode()
    item["metrics"]["impedance_principal_ohm_per_m"] = missing
    best = record(tmp_path, [item])
    text, rows = render(tmp_path, [best], best)
    assert rows[0]["zmax_kohm_per_m"] == ""
    assert rows[0]["threshold_status"] == "undetermined"
    assert "missing_or_nonfinite_metrics" in rows[0]["quality_reasons"]
    assert "—" in text


def test_missing_all_field_metrics_keeps_native_frequency_and_q(tmp_path):
    item = mode(valid=False)
    item["metrics"] = None
    failed = record(tmp_path, [item], valid=False)
    text, rows = render(tmp_path, [failed])
    assert rows[0]["frequency_mhz"] == "1040.0"
    assert rows[0]["total_q"] == "500.0"
    assert rows[0]["rq_principal_ohm_per_m"] == ""
    assert rows[0]["zmax_kohm_per_m"] == ""
    assert "meets_threshold" not in text


def test_pending_recovery_uses_latest_archived_analysis_and_preserves_raw_evidence(tmp_path):
    evaluation = tmp_path / "evaluations" / "evaluation_0000"
    older = evaluation / "attempt_000" / "postprocess_000" / "analysis.json"
    newer = evaluation / "attempt_001" / "postprocess_002" / "analysis.json"
    for path, number in ((older, 1), (newer, 5)):
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(modes=[mode(number, valid=False)], quality_ok=False)))
    raw = newer.parent / "fields" / "mode_5"
    raw.mkdir(parents=True)
    (raw / "tracks.csv").write_bytes(b"raw field evidence")
    original = {p: p.read_bytes() for p in evaluation.rglob("*") if p.is_file()}
    pending = dict(id="evaluation_0000", attempt_dir=str(evaluation))
    text, rows = render(tmp_path, pending=pending)
    assert [row["mode"] for row in rows] == ["5"]
    assert rows[0]["analysis_path"] == str(newer)
    assert rows[0]["raw_evidence_path"] == str(raw)
    assert rows[0]["evaluation_status"] == "pending"
    assert rows[0]["threshold_status"] == "undetermined"
    assert str(newer) in text
    assert {p: p.read_bytes() for p in original} == original


def test_committed_best_does_not_use_newer_mismatched_analysis(tmp_path):
    best = record(tmp_path, [mode(2)])
    # Actual TransverseMetrics.to_dict retains tuples until journal serialization.
    best["modes"]["modes"][0]["metrics"]["quality_reasons"] = ()
    bundle = Path(best["attempt_dir"]) / "attempt_000" / "postprocess_000"
    later = bundle.with_name("postprocess_001")
    for path, payload in ((bundle, best["modes"]), (later, dict(modes=[mode(9)], quality_ok=True))):
        path.mkdir(parents=True)
        (path / "analysis.json").write_text(json.dumps(payload))
    (bundle / "fields" / "mode_2").mkdir(parents=True)
    _, rows = render(tmp_path, [best], best)
    assert [row["mode"] for row in rows] == ["2"]
    assert rows[0]["analysis_path"] == str(bundle / "analysis.json")


def test_no_data_rewrites_stale_csv_and_empty_band_has_no_fabricated_zero_row(tmp_path):
    best = record(tmp_path, [mode()])
    render(tmp_path, [best], best)
    text, rows = render(tmp_path)
    assert rows == []
    assert "No window mode metrics" in text
    empty = record(tmp_path, [])
    empty["modes"].update(empty_band=True, coverage_complete=True)
    text, rows = render(tmp_path, [empty], empty)
    assert rows == []
    assert "complete coverage and an empty band" in text


def test_campaign_report_calls_helper_and_displays_configured_threshold(tmp_path):
    config = WorkflowConfig(PathsConfig(tmp_path / "source.cst", tmp_path / "run"),
        tuple(ParameterConfig(*p) for p in PARAMETER_DEFAULTS),
        PhysicsConfig(z_range_mm=(-235., 235.), threshold_ohm_per_m=75000.))
    store = CampaignStore(config.paths.output_dir, "report-test", 40)
    try:
        failed = record(tmp_path, [mode(4, valid=False)], valid=False)
        failed["objective"] = None
        store.state.update(records=[failed], status="baseline_failed", error="quality failed")
        campaign = Campaign(config, store, lambda *args: pytest.fail("must not evaluate or solve"))
        report = campaign.report()
        text = (store.root / "report.md").read_text(encoding="utf-8")
        assert "Threshold: 75 kΩ/m." in text
        assert "| Frequency (MHz) | Total-Q |" in text
        assert "Diagnostic only" in text
        assert (store.root / "modes.csv").is_file()
        assert report["best"] is None
        assert store.state["solve_count"] == 0
    finally:
        store.close()


def test_largest_two_report_lists_selected_modes_and_keeps_raw_record(tmp_path):
    best = record(tmp_path,[mode(1,impedance=90000),mode(4,impedance=150000),mode(9,impedance=3)])
    best["modes"].update(mode_policy="largest_two",objective_mode_numbers=[4,1])
    _, rows = render(tmp_path,[best],best)
    assert {row["mode"] for row in rows} == {"1","4"}
    assert len(best["modes"]["modes"]) == 3
