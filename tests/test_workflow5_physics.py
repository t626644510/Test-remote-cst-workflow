"""No-CST analytic and fake-interface tests for WF5 scientific contracts."""

from __future__ import annotations

import json
import builtins
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from workflows.rfgun_hom_target.physics import (C_M_PER_S, calculate_transverse_metrics,
    phase_insensitive_correlation, ModeSignature, match_mode_signatures)
from workflows.rfgun_hom_target import postprocess as pp


def analytic_fields(gx=2e5, gy=1e5j, count=101, scale=1 + 0j):
    xy = pp.trajectory_coordinates((2, 4, 6))
    z = np.linspace(-0.1, 0.1, count)
    freq = 1.04e9
    voltage = (gx * xy[:, 0] + gy * xy[:, 1]) * 1e-3 + 2
    ez = scale * voltage[:, None] / np.ptp(z) * np.exp(-1j * 2 * np.pi * freq / C_M_PER_S * z)
    return xy, z, freq, ez


def metrics(gx=2e5, gy=1e5j, scale=1 + 0j, q=100):
    xy, z, freq, ez = analytic_fields(gx, gy, scale=scale)
    return calculate_transverse_metrics(ez, z, xy, frequency_hz=freq, energy_j=0.3 * abs(scale)**2, q_loaded=q)


def test_principal_real_direction_is_not_trace_or_complex_eigenvalue():
    result = metrics()
    factor = C_M_PER_S / (2 * (2 * np.pi * 1.04e9)**2 * 0.3)
    assert result.quality_ok
    assert result.rq_x_ohm_per_m == pytest.approx(factor * (2e5)**2)
    assert result.rq_y_ohm_per_m == pytest.approx(factor * (1e5)**2)
    assert result.rq_principal_ohm_per_m == pytest.approx(result.rq_x_ohm_per_m)
    assert result.impedance_principal_ohm_per_m == pytest.approx(100 * result.rq_principal_ohm_per_m)
    assert result.rq_principal_ohm_per_m < result.rq_x_ohm_per_m + result.rq_y_ohm_per_m


def test_real_polarization_and_complex_field_normalization_invariant():
    a, b = metrics(2e5, 2e5), metrics(2e5, 2e5, scale=3 * np.exp(0.73j))
    assert a.principal_angle_deg == pytest.approx(45)
    assert a.rq_principal_ohm_per_m == pytest.approx(2 * a.rq_x_ohm_per_m)
    assert b.impedance_principal_ohm_per_m == pytest.approx(a.impedance_principal_ohm_per_m)
    assert b.principal_angle_deg == pytest.approx(a.principal_angle_deg)


def test_low_q_and_vanishing_field_cannot_claim_success():
    assert metrics(q=9).impedance_principal_ohm_per_m is None
    assert not metrics(q=9).quality_ok
    xy, z, freq, ez = analytic_fields()
    zero = calculate_transverse_metrics(ez * 0, z, xy, frequency_hz=freq, energy_j=1, q_loaded=100)
    assert not zero.quality_ok


@pytest.mark.parametrize("kind", ["nan", "energy", "q", "frequency", "shape", "grid"])
def test_invalid_physics_inputs_raise(kind):
    xy, z, freq, ez = analytic_fields()
    energy, q = 1.0, 100.0
    if kind == "nan": ez[0, 0] = np.nan
    if kind == "energy": energy = 0
    if kind == "q": q = np.inf
    if kind == "frequency": freq = -1
    if kind == "shape": ez = ez[:-1]
    if kind == "grid": z[2] = z[1]
    with pytest.raises(ValueError):
        calculate_transverse_metrics(ez, z, xy, frequency_hz=freq, energy_j=energy, q_loaded=q)


def test_gradient_and_sampling_quality_are_enforced():
    xy, z, freq, ez = analytic_fields(count=9)
    nonlinear = ez + 1e20 * (xy[:, 0] * 1e-3)[:, None]**5 * np.exp(-1j * 2 * np.pi * freq / C_M_PER_S * z)
    result = calculate_transverse_metrics(nonlinear, z, xy, frequency_hz=freq, energy_j=1, q_loaded=100)
    assert "gradient_crosscheck_failed" in result.quality_reasons
    unstable = ez * (1 + 0.2 * (-1.0)**np.arange(len(z)))
    result = calculate_transverse_metrics(unstable, z, xy, frequency_hz=freq, energy_j=1, q_loaded=100)
    assert "sampling_crosscheck_failed" in result.quality_reasons


def test_field_matching_ignores_global_phase_not_shape():
    a = np.array([1, 2j, 3])
    assert phase_insensitive_correlation(a, a * np.exp(0.9j)) == pytest.approx(1)
    assert phase_insensitive_correlation(a, np.array([1, 0, 0])) < 0.5


class FakeReader:
    data = {
        r"1D Results\Mode Frequencies\Mode 2": [1040],
        r"1D Results\Mode Frequencies\Mode 7": [1065],
        r"1D Results\Q Factors\Total-Q\Mode 2": [100],
        r"1D Results\Q Factors\Total-Q\Mode 7": [120],
    }

    def __init__(self, *args, **kwargs): pass
    def list_tree_items(self): return list(self.data)
    def get_result_item(self, key): return SimpleNamespace(get_ydata=lambda: self.data[key])


def test_dynamic_discovery_preserves_mode_gaps_and_out_of_band(monkeypatch):
    monkeypatch.setattr(pp, "ResultReader", FakeReader)
    modes = pp.read_native_modes("portable.cst", pp.PostprocessConfig((-100, 100)))
    assert [m.mode_number for m in modes] == [2, 7]
    assert modes[1].frequency_hz == 1065e6


def test_discovery_missing_q_does_not_silently_drop_mode(monkeypatch):
    class MissingQ(FakeReader):
        data = {k: v for k, v in FakeReader.data.items() if "Mode 7" not in k or "Frequencies" in k}
    monkeypatch.setattr(pp, "ResultReader", MissingQ)
    with pytest.raises(KeyError):
        pp.read_native_modes("portable.cst", pp.PostprocessConfig((-100, 100)))


def write_raw(raw: Path, mode: pp.NativeMode, config: pp.PostprocessConfig):
    raw.mkdir(parents=True, exist_ok=True)
    xy, z, _, ez = analytic_fields(count=config.z_samples)
    data = np.zeros((13 * config.z_samples, 7))
    data[:, 2], data[:, 5], data[:, 6] = ez.real.ravel(), ez.imag.ravel(), -1
    np.savetxt(raw / "tracks.csv", data, delimiter=",", header="Ex_re,Ey_re,Ez_re,Ex_im,Ey_im,Ez_im,valid", comments="")
    (raw / "energy.csv").write_text("U_J,Q_wall_postprocess\n0.3,10000\n")
    (raw / "qfactor_check.txt").write_text(f"Frequency/Hz {mode.frequency_hz}\nEnergy/J 0.3\n")


@pytest.mark.parametrize("corruption", ["frequency", "energy", "nan", "invalid", "missing"])
def test_archived_mode_quality_fails_closed(tmp_path, corruption):
    config = pp.PostprocessConfig((-100, 100), z_samples=101)
    mode = pp.NativeMode(9, 1.04e9, 100)
    write_raw(tmp_path, mode, config)
    if corruption in {"frequency", "energy"}:
        text = "Frequency/Hz 1030000000\nEnergy/J 0.3\n" if corruption == "frequency" else "Frequency/Hz 1040000000\nEnergy/J 1\n"
        (tmp_path / "qfactor_check.txt").write_text(text)
    elif corruption == "missing":
        (tmp_path / "qfactor_check.txt").unlink()
    else:
        data = np.loadtxt(tmp_path / "tracks.csv", delimiter=",", skiprows=1)
        data[0, 2 if corruption == "nan" else 6] = np.nan if corruption == "nan" else 0
        np.savetxt(tmp_path / "tracks.csv", data, delimiter=",", header="header", comments="")
    with pytest.raises((ValueError, FileNotFoundError)):
        pp.analyze_mode_files(mode, tmp_path, config)


def test_collect_all_in_band_and_preserve_raw_artifacts_without_owning_session(tmp_path):
    config = pp.PostprocessConfig((-100, 100), z_samples=101, conductivity_layers={"Custom metal": {"conductivity": "5e7", "mu": 1}})
    modes = [pp.NativeMode(2, 1.04e9, 1000), pp.NativeMode(7, 1.055e9, 1000), pp.NativeMode(12, 1.07e9, 1000)]
    project_path, output = tmp_path / "copy.cst", tmp_path / "post"
    calls = []
    def execute(macro, timeout):
        calls.append(macro)
        for mode in modes:
            if f'.SetHField "Mode {mode.mode_number}"' in macro:
                write_raw(output / "fields" / f"mode_{mode.mode_number}", mode, config)
    project = SimpleNamespace(filename=str(project_path), project=SimpleNamespace(schematic=SimpleNamespace(execute_vba_code=execute)))
    result = pp.collect_and_analyze(project, project_path, output, config, (1030, 1060), native_modes=modes)
    assert [m.native.mode_number for m in result.modes] == [2, 7]
    assert len(result.native_modes) == 3 and len(calls) == 4
    assert result.quality_ok
    assert (output / "fields/mode_7/tracks.bas").exists()
    assert (output / "fields/mode_7/energy.csv").exists()
    assert json.loads((output / "analysis.json").read_text())["quality_ok"]


def test_verified_macros_configure_units_and_quote_layer_strings(tmp_path):
    config = pp.PostprocessConfig((-100, 100), geometry_unit="m")
    macro = pp.build_field_vba(pp.NativeMode(11, 1e9, 100), tmp_path, config)
    assert 'Mode 11\\e' in macro
    assert "-0.1+0.2*j/1882" in macro
    energy = pp.build_energy_vba(pp.NativeMode(11, 1e9, 100), tmp_path, {'custom "metal"': {"conductivity": "PEC", "mu": 1}})
    assert '"custom ""metal"""' in energy
    assert "GetTotalEnergy" in energy
    assert "Solver" not in energy


@pytest.mark.parametrize("failure", ["overlap", "missing_field", "no_modes"])
def test_collection_cannot_pass_overlap_missing_field_or_empty_band(tmp_path, failure):
    config = pp.PostprocessConfig((-100, 100), z_samples=101, conductivity_layers={"Metal": {"conductivity": "PEC", "mu": 1}})
    modes = [pp.NativeMode(2, 1.04e9, 100)]
    if failure == "overlap": modes.append(pp.NativeMode(3, 1.041e9, 100))
    if failure == "no_modes": modes = [pp.NativeMode(3, 1.07e9, 100)]
    source, output = tmp_path / "copy.cst", tmp_path / "post"
    def execute(macro, timeout):
        if failure == "missing_field": raise RuntimeError("Missing E field")
        for mode in modes:
            if f'.SetHField "Mode {mode.mode_number}"' in macro:
                write_raw(output / "fields" / f"mode_{mode.mode_number}", mode, config)
    project = SimpleNamespace(filename=str(source), project=SimpleNamespace(schematic=SimpleNamespace(execute_vba_code=execute)))
    result = pp.collect_and_analyze(project, source, output, config, (1030, 1060), native_modes=modes)
    assert not result.quality_ok
    assert result.worst_impedance_ohm_per_m is None
    assert (output / "analysis.json").exists()
    if failure == "overlap":
        assert all("overlapping_mode_linewidths" in m.quality_reasons for m in result.modes)


def test_configuration_and_missing_material_do_not_default_to_copper(tmp_path):
    with pytest.raises(ValueError, match="conductivity"):
        pp._layers(tmp_path / "model.cst", pp.PostprocessConfig((-100, 100)))
    with pytest.raises(ValueError): pp.PostprocessConfig((-100, 100), beta=0.5)
    with pytest.raises(ValueError): pp.PostprocessConfig((-100, 100), z_samples=100)
    with pytest.raises(ValueError): pp.PostprocessConfig((-100, 100), offsets_mm=(2, 2, 6))


def signature(label, vector, frequency=1.04e9):
    return ModeSignature(label, frequency, tuple(np.asarray(vector, dtype=complex)))


def test_signature_assignment_survives_reordering_arbitrary_phase_and_scale():
    basis = np.eye(13, dtype=complex)
    baseline = [signature("old_2", basis[0]), signature("old_7", basis[1])]
    current = [signature("new_1", basis[1] * np.exp(1.7j) * 7), signature("new_9", basis[0] * 0.2j)]
    result = match_mode_signatures(baseline, current)
    assert [row.baseline_id for row in result] == ["old_7", "old_2"]
    assert all(not row.ambiguous and row.overlap == pytest.approx(1) for row in result)


def test_degenerate_rotated_basis_is_ambiguous_not_confident_identity():
    basis = np.eye(13, dtype=complex)
    baseline = [signature("a", basis[0]), signature("b", basis[1])]
    current = [signature("c", (basis[0] + basis[1]) * np.exp(0.4j)),
               signature("d", (basis[0] - basis[1]) * np.exp(-0.9j))]
    result = match_mode_signatures(baseline, current, minimum_overlap=0.6)
    assert all(row.ambiguous for row in result)
    assert all(row.overlap == pytest.approx(2**-0.5) for row in result)
    strict = match_mode_signatures(baseline, current)
    assert all(row.baseline_id is None and row.ambiguous for row in strict)


def test_signature_matching_frequency_gate_and_missing_extra_modes():
    basis = np.eye(13, dtype=complex)
    baseline = [signature("old", basis[0])]
    current = [signature("far", basis[0], 1.09e9), signature("near", basis[0]), signature("extra", basis[2])]
    result = match_mode_signatures(baseline, current)
    assert [row.baseline_id for row in result] == [None, "old", None]
    assert len(result) == 3  # No mode removed from all-window objective.
    assert match_mode_signatures([], current)[0].reason == "no_baseline_modes"


def test_signature_from_saved_voltages_normalizes_and_validates():
    m = metrics()
    assert len(m.voltages_real_v) == 13
    value = ModeSignature.from_metrics("candidate_42", 1.04e9, m)
    assert np.linalg.norm(value.voltages) == pytest.approx(1)
    with pytest.raises(ValueError): signature("zero", np.zeros(13))
    with pytest.raises(ValueError): signature("short", np.zeros(2))


@pytest.mark.parametrize("overlap", [False, True])
def test_offline_relocated_bundle_never_imports_cst_or_reads_original(tmp_path, monkeypatch, overlap):
    config = pp.PostprocessConfig((-100, 100), z_samples=101)
    modes = [pp.NativeMode(2, 1.04e9, 1000)]
    if overlap: modes.append(pp.NativeMode(9, 1.0401e9, 1000))
    bundle = tmp_path / "relocated"
    bundle.mkdir()
    for mode in modes: write_raw(bundle / "fields" / f"mode_{mode.mode_number}", mode, config)
    (bundle / "native.json").write_text(json.dumps({"source_project": "Z:/does-not-exist.cst", "modes": [m.to_dict() for m in modes]}))
    (bundle / "field_config.json").write_text(json.dumps({**asdict(config), "xy_mm": pp.trajectory_coordinates(config.offsets_mm).tolist(), "band_mhz": [1030, 1060]}))
    snapshots = {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == "cst" or name.startswith("cst."): raise AssertionError("offline must not import CST")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(pp, "ResultReader", lambda *a, **k: pytest.fail("offline reader must not open a project"))
    result = pp.analyze_bundle(bundle)
    assert result.quality_ok is (not overlap)
    assert all(p.read_bytes() == value for p, value in snapshots.items())
    assert set(snapshots) == {p for p in bundle.rglob("*") if p.is_file()}


def test_legacy_skill_archive_reads_losses_metadata_but_missing_mode_fails(tmp_path):
    config = pp.PostprocessConfig((-100, 100), z_samples=101)
    mode = pp.NativeMode(1, 1.04e9, 1000)
    raw = tmp_path / "fields/mode_1"
    write_raw(raw, mode, config)
    (raw / "qfactor_check.txt").rename(raw / "losses.txt")
    (tmp_path / "native.json").write_text(json.dumps({"modes": {"1": {"frequency_Hz": 1.04e9, "Q_loaded": 1000}, "2": {"frequency_Hz": 1.06e9, "Q_loaded": 1000}}}))
    (tmp_path / "field_config.json").write_text(json.dumps({**asdict(config), "modes": [1], "port_groups": {"unused": [1]}}))
    result = pp.analyze_bundle(tmp_path)
    assert result.modes[0].quality_ok
    assert not result.quality_ok and len(result.modes) == 2
    assert result.modes[1].metrics is None
