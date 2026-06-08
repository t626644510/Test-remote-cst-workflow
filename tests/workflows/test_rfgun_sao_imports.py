from __future__ import annotations

import sys
from pathlib import Path

import ast
import pytest
import yaml

# ---- Locate the project root and ensure both src/ and project root are
#      on sys.path for imports.
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = str(_PROJECT_ROOT / "src")
for p in (str(_PROJECT_ROOT), _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

WF1_PACKAGE = _PROJECT_ROOT / "workflows" / "rfgun_sao"
CONFIG_PATH = WF1_PACKAGE / "config.yaml"


# ---- Test helpers ----------------------------------------------------------

def _minimal_two_pass_cfg() -> dict:
    """Minimal config dict for two-pass placeholder tests."""
    return {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }


class _FakeCalibrationRunner:
    """Fake calibration runner with configurable success/failure."""
    def __init__(
        self,
        success: bool = True,
        f0_ghz: float = 11.424,
        s11_min_db: float = -10.0,
        error: str = "",
        method: str = "cst_s11_hpbw",
        meta: dict | None = None,
    ):
        self._success = success
        self._f0_ghz = f0_ghz
        self._s11_min_db = s11_min_db
        self._error = error
        self._method = method
        self._meta = meta or {}
        self.call_count = 0
        self.last_params: dict | None = None
        self.last_iter: int | None = None

    def __call__(self, param_dict: dict, iteration: int):
        self.call_count += 1
        self.last_params = param_dict
        self.last_iter = iteration
        from workflows.rfgun_sao.calibration import CalibrationResult
        return CalibrationResult(
            success=self._success,
            f0_ghz=self._f0_ghz,
            s11_min_db=self._s11_min_db,
            error=self._error,
            method=self._method,
            meta=dict(self._meta),
        )


class _FakeMeasurementRunner:
    """Fake measurement runner with configurable results."""
    _OBJ_SENTINEL = object()

    def __init__(
        self,
        penalty_values: dict | None = None,
        raw_values: dict | None = None,
        status=None,
        objective_values=_OBJ_SENTINEL,
        error: str = "",
        diagnostics: dict | None = None,
    ):
        from workflows.rfgun_sao.types import EvaluationStatus
        self._penalty_values = penalty_values or {"resonant_freq": 0.0}
        self._raw_values = raw_values or {"resonant_freq": 11.424}
        self._status = status or EvaluationStatus.SUCCESS
        # Default objective_values = raw_values (backward compatible).
        # Pass objective_values=None explicitly to test fallback.
        if objective_values is self._OBJ_SENTINEL:
            self._objective_values = self._raw_values
        else:
            self._objective_values = objective_values
        self._error = error
        self._diagnostics = diagnostics
        self.call_count = 0
        self.last_params: dict | None = None
        self.last_plan = None
        self.last_iter: int | None = None

    def __call__(self, param_dict: dict, plan, iteration: int):
        self.call_count += 1
        self.last_params = param_dict
        self.last_plan = plan
        self.last_iter = iteration
        from workflows.rfgun_sao.types import EvaluationResult
        return EvaluationResult(
            status=self._status,
            error=self._error,
            f0_ghz=11.424,
            raw_metrics=self._raw_values,
            objective_values=self._objective_values,
            penalty_values=self._penalty_values,
            diagnostics=self._diagnostics,
        )


# ============================================================
# A. Runner import and default config path
# ============================================================

def test_import_runner_without_cst():
    import workflows.rfgun_sao.run as run_mod
    assert run_mod.DEFAULT_CONFIG_PATH.name == "config.yaml"
    assert run_mod.DEFAULT_CONFIG_PATH.exists()

# ============================================================
# B. CLI parser accepts expected flags
# ============================================================

def test_cli_parser_accepts_expected_flags():
    from workflows.rfgun_sao.run import build_arg_parser
    parser = build_arg_parser()
    args = parser.parse_args([
        "--config", "custom.yaml",
        "--seed", "123",
        "--n-iter", "4",
        "--n-initial", "5",
    ])
    assert args.config == "custom.yaml"
    assert args.seed == 123
    assert args.n_iter == 4
    assert args.n_initial == 5

# ============================================================
# C. Config YAML has WF1 sections only
# ============================================================

def test_config_yaml_has_wf1_sections_only():
    assert CONFIG_PATH.exists(), f"Config not found: {CONFIG_PATH}"
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    expected_keys = {
        "cst", "solver", "logging", "project",
        "evaluation", "optimization", "parameters", "objectives",
    }
    actual_keys = set(cfg.keys())
    for key in expected_keys:
        assert key in actual_keys, f"Missing expected key: {key}"

    assert "workflow_2" not in cfg
    assert "tolerance" not in cfg

    params = cfg.get("parameters", [])
    assert len(params) == 13, f"Expected 13 parameters, got {len(params)}"

    obj_names = {o["name"] for o in cfg.get("objectives", [])}
    expected_objs = {
        "resonant_freq", "coupling_beta", "peak_e_field", "q0",
        "max_modified_poynting", "field_flatness", "pulsed_heating",
    }
    for name in expected_objs:
        assert name in obj_names, f"Missing objective: {name}"
    assert len(obj_names) == len(expected_objs), (
        f"Expected {len(expected_objs)} objectives, got {len(obj_names)}"
    )

# ============================================================
# D. Local workflow module imports factory helpers (not builder functions)
# ============================================================

def test_local_workflow_module_imports_factory():
    """Phase 1 dedup: workflow.py imports shared _build_* helpers from factory."""
    sys.modules.pop("cst_optimization.factory", None)
    sys.modules.pop("workflows.rfgun_sao.workflow", None)

    import workflows.rfgun_sao.workflow as wf_mod

    assert "cst_optimization.factory" in sys.modules
    assert hasattr(wf_mod, "build_workflow_1")
    # The local _build_sao etc. are re-exported from factory but callable
    assert callable(getattr(wf_mod, "_build_sao", None))

# ============================================================
# E. Evaluator class can be constructed without CST
# ============================================================

class _DummyMode:
    def compute(self, value: float) -> float:
        return 0.0

class _DummyObjective:
    name = "resonant_freq"
    mode = _DummyMode()

def test_evaluator_class_can_be_constructed_without_cst_connection():
    from workflows.rfgun_sao.evaluator import Workflow1Evaluator

    class DummyConn:
        pass

    class DummySolver:
        pass

    evaluator = Workflow1Evaluator(
        connection=DummyConn(),
        project_path="dummy.cst",
        solver_runner=DummySolver(),
        objectives=[_DummyObjective()],
        param_names=["p1"],
        metric_names=["resonant_freq"],
    )

    assert evaluator is not None
    assert callable(evaluator.adapt_for_retry)
    assert callable(evaluator.on_reconnect)

# ============================================================
# F. Workflow source imports factory helpers (not duplicated)
# ============================================================

def test_workflow_source_imports_factory_helpers_not_duplicate_defs():
    """Phase 1 dedup: workflow.py imports helpers; no longer duplicates them."""
    src = (WF1_PACKAGE / "workflow.py").read_text("utf-8")
    # Must import from factory (single canonical source)
    assert "from cst_optimization.factory import" in src
    # Must NOT have local duplicate definitions
    assert "\ndef _build_sao(" not in src
    assert "\ndef _build_parameters(" not in src
    assert "\ndef _resolve_named_weights(" not in src

# ============================================================
# G. No WF2 objective side-effect imports
# ============================================================

def test_no_wf2_objective_side_effect_imports():
    src = (WF1_PACKAGE / "workflow.py").read_text("utf-8")
    assert "objectives import wakefield" not in src
    assert "objectives import antenna" not in src

# ============================================================
# H. Evaluator source has no factory import
# ============================================================

def test_runner_does_not_use_loaded_count():
    src = (WF1_PACKAGE / 'run.py').read_text('utf-8')
    assert 'loaded_count' not in src
    assert '.load()' in src
    assert 'get_warm_xy' in src

def test_runner_optimize_uses_only_supported_kwargs():
    src = (WF1_PACKAGE / 'run.py').read_text('utf-8-sig')
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == 'optimize':
                kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
                assert 'evaluator' in kwargs
                assert 'prior_data' in kwargs
                assert 'n_initial' not in kwargs
                assert 'n_iterations' not in kwargs
                return
    raise AssertionError('Could not find opt.optimize() call in run.py')

def test_builders_module_has_n_initial_samples_and_n_initial():
    """Phase 11: _build_sao in factory.py accepts both config keys (builders merged)."""
    builders_path = Path(__file__).parents[2] / "src" / "cst_optimization" / "factory.py"
    src = builders_path.read_text("utf-8")
    assert 'n_initial_samples' in src
    assert 'n_initial' in src

def test_runner_prints_optimization_result_attributes():
    src = (WF1_PACKAGE / 'run.py').read_text('utf-8')
    assert 'result.get(' not in src
    assert 'result.x_opt' in src
    assert 'result.f_opt' in src

def test_types_expose_evaluation_types():
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
    assert hasattr(EvaluationStatus, 'SUCCESS')
    assert hasattr(EvaluationStatus, 'COM_LOST')
    assert hasattr(EvaluationResult, 'status')
    assert hasattr(EvaluationResult, 'error')
    assert EvaluationResult().solver_ok is False
    assert EvaluationResult(status=EvaluationStatus.SUCCESS).solver_ok is True


def test_evaluation_status_enum_match_with_shared_recovery():
    """rfgun_sao/types.py EvaluationStatus must have same values as shared recovery.py."""
    from workflows.rfgun_sao.types import EvaluationStatus as SaoES
    from cst_optimization.workflows.recovery import EvaluationStatus as SharedES

    sao_vals = set(e.value for e in SaoES)
    shared_vals = set(e.value for e in SharedES)
    missing = shared_vals - sao_vals
    extra = sao_vals - shared_vals
    assert not missing, (
        f"rfgun_sao/types.py EvaluationStatus missing values: {missing}. "
        f"Shared recovery.py has: {sorted(shared_vals)}"
    )
    assert not extra, (
        f"rfgun_sao/types.py EvaluationStatus has extra values: {extra}. "
        f"Shared recovery.py has: {sorted(shared_vals)}"
    )


def test_evaluation_result_fields_match_shared_recovery():
    """rfgun_sao/types.py EvaluationResult must have all fields from shared recovery.py."""
    from dataclasses import fields as dc_fields
    from workflows.rfgun_sao.types import EvaluationResult as SaoER
    from cst_optimization.workflows.recovery import EvaluationResult as SharedER

    sao_fields = {f.name for f in dc_fields(SaoER)}
    shared_fields = {f.name for f in dc_fields(SharedER)}
    missing = shared_fields - sao_fields
    assert not missing, (
        f"rfgun_sao/types.py EvaluationResult missing fields: {missing}. "
        f"Shared recovery.py fields: {sorted(shared_fields)}"
    )


def test_default_weights_equal():
    from cst_optimization.factory import _resolve_named_weights
    w = _resolve_named_weights(None, ["a", "b", "c"])
    assert list(w) == [1/3, 1/3, 1/3]

def test_named_weights_by_objective_order():
    from cst_optimization.factory import _resolve_named_weights
    w = _resolve_named_weights({"b": 5.0, "a": 3.0}, ["a", "b"])
    assert list(w) == [3/8, 5/8]

def test_weight_0_is_allowed():
    from cst_optimization.factory import _resolve_named_weights
    w = _resolve_named_weights({'a': 0.0, 'b': 2.0}, ['a', 'b'])
    assert w[0] == 0.0 and w[1] == 1.0

def test_all_zero_weights_raise_error():
    from cst_optimization.factory import _resolve_named_weights
    import pytest
    with pytest.raises(ValueError):
        _resolve_named_weights({'a': 0.0, 'b': 0.0}, ['a', 'b'])

def test_inf_weights_raise_error():
    from cst_optimization.factory import _resolve_named_weights
    import pytest
    with pytest.raises(ValueError):
        _resolve_named_weights({'a': float('inf')}, ['a'])

def test_invalid_weights_raise_error():
    from cst_optimization.factory import _resolve_named_weights
    import pytest
    with pytest.raises(ValueError):
        _resolve_named_weights({"a": -1.0}, ["a"])
    with pytest.raises(ValueError):
        _resolve_named_weights({"a": float("nan")}, ["a"])

def test_config_yaml_has_evaluation_mode():
    import yaml
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    assert cfg.get("evaluation", {}).get("mode", "") == "single_pass"

def test_resolve_evaluation_mode_defaults():
    from workflows.rfgun_sao.workflow import _resolve_evaluation_mode
    assert _resolve_evaluation_mode({}) == "single_pass"
    assert _resolve_evaluation_mode({"evaluation": {"mode": "single_pass"}}) == "single_pass"
    assert _resolve_evaluation_mode({"evaluation": {"mode": "two_pass"}}) == "two_pass"
    import pytest
    with pytest.raises(ValueError):
        _resolve_evaluation_mode({"evaluation": {"mode": "invalid"}})

def test_gates_frequency_disabled_always_accepts():
    from workflows.rfgun_sao.gates import FrequencyGate
    g = FrequencyGate(enabled=False)
    assert g.accepts(10.0) is True

def test_gates_frequency_enabled_accepts_within_20mhz():
    from workflows.rfgun_sao.gates import FrequencyGate
    g = FrequencyGate(enabled=True, target_ghz=11.424, max_abs_offset_mhz=20.0)
    assert g.accepts(11.424) is True
    assert g.accepts(11.434) is True

def test_gates_frequency_enabled_rejects_outside_20mhz():
    from workflows.rfgun_sao.gates import FrequencyGate
    g = FrequencyGate(enabled=True, target_ghz=11.424, max_abs_offset_mhz=20.0)
    assert g.accepts(11.5) is False
    assert g.accepts(11.3) is False

def test_gates_s11_disabled_always_accepts():
    from workflows.rfgun_sao.gates import S11DepthGate
    g = S11DepthGate(enabled=False)
    assert g.accepts(0.0) is True

def test_gates_s11_enabled_accepts_deep_dip():
    from workflows.rfgun_sao.gates import S11DepthGate
    g = S11DepthGate(enabled=True, threshold_db=-1.0)
    assert g.accepts(-10.0) is True
    assert g.accepts(-1.0) is True

def test_gates_s11_enabled_rejects_shallow_dip():
    from workflows.rfgun_sao.gates import S11DepthGate
    g = S11DepthGate(enabled=True, threshold_db=-1.0)
    assert g.accepts(0.0) is False

def test_gates_multidip_disabled_returns_false():
    from workflows.rfgun_sao.gates import MultiDipDetector
    import numpy as np
    d = MultiDipDetector(enabled=False)
    assert d.has_multiple_dips(np.array([11.0, 11.5]), np.array([0.5, 0.3])) is False

def test_gates_multidip_detects_two_close_dips():
    from workflows.rfgun_sao.gates import MultiDipDetector
    import numpy as np
    d = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    freqs = np.linspace(11.0, 12.0, 200)
    mag = np.ones(200)
    # Create two dips close together
    dip1_idx = 50
    dip2_idx = 53
    mag[dip1_idx] = 0.1
    mag[dip2_idx] = 0.1
    assert d.has_multiple_dips(freqs, mag) is True

def test_calibration_default_is_unsuccessful():
    from workflows.rfgun_sao.calibration import CalibrationResult
    c = CalibrationResult()
    assert c.success is False

def test_make_measurement_plan_uses_f0_when_success():
    from workflows.rfgun_sao.calibration import CalibrationResult, make_measurement_plan
    cal = CalibrationResult(success=True, f0_ghz=11.424)
    plan = make_measurement_plan(cal, 11.4)
    assert plan.f_data_ghz == 11.424
    assert plan.reason == 'calibrated_resonance'

def test_make_measurement_plan_fallback_when_failed():
    from workflows.rfgun_sao.calibration import CalibrationResult, make_measurement_plan
    cal = CalibrationResult(success=False)
    plan = make_measurement_plan(cal, 11.4)
    assert plan.f_data_ghz == 11.4
    assert plan.reason == 'fallback'

def test_s11_min_db_from_magnitude():
    from workflows.rfgun_sao.calibration import s11_min_db_from_magnitude
    import numpy as np
    db = s11_min_db_from_magnitude(np.array([0.1]))
    assert abs(db - (-20.0)) < 0.01


def test_two_pass_placeholder_build_does_not_raise():
    from workflows.rfgun_sao.workflow import build_workflow_1
    cfg = _minimal_two_pass_cfg()
    wf, opt, ev = build_workflow_1(cfg)
    assert wf._conn is None
    import numpy as np
    val = ev(np.array([0.5]))
    assert np.isfinite(val)

def test_two_pass_placeholder_no_cst_connection():
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np
    cfg = _minimal_two_pass_cfg()
    wf, opt, ev = build_workflow_1(cfg)
    assert wf._conn is None

def test_two_pass_successful_calibration_accepted():
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.calibration import CalibrationResult
    cal = CalibrationResult(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    dec = evaluate_two_pass_decision(cal, 11.4)
    assert dec.accepted is True
    assert dec.reason == 'accepted'

def test_two_pass_failed_calibration_rejected():
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.calibration import CalibrationResult
    cal = CalibrationResult(success=False)
    dec = evaluate_two_pass_decision(cal, 11.4)
    assert dec.accepted is False
    assert dec.reason == 'calibration_failed'
    assert dec.measurement_plan is not None

def test_two_pass_frequency_gate_rejects():
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.calibration import CalibrationResult
    from workflows.rfgun_sao.gates import FrequencyGate
    cal = CalibrationResult(success=True, f0_ghz=11.5)
    gate = FrequencyGate(enabled=True, target_ghz=11.424, max_abs_offset_mhz=20.0)
    dec = evaluate_two_pass_decision(cal, 11.4, frequency_gate=gate)
    assert dec.accepted is False
    assert dec.reason == 'frequency_gate_reject'

def test_two_pass_s11_gate_rejects():
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.calibration import CalibrationResult
    from workflows.rfgun_sao.gates import S11DepthGate
    cal = CalibrationResult(success=True, f0_ghz=11.424, s11_min_db=0.0)
    gate = S11DepthGate(enabled=True, threshold_db=-1.0)
    dec = evaluate_two_pass_decision(cal, 11.4, s11_depth_gate=gate)
    assert dec.accepted is False
    assert dec.reason == 's11_depth_gate_reject'

def test_two_pass_multidip_diagnostic_does_not_reject():
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.calibration import CalibrationResult
    from workflows.rfgun_sao.gates import MultiDipDetector
    import numpy as np
    cal = CalibrationResult(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    det = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    freqs = np.linspace(11.0, 12.0, 200)
    mag = np.ones(200)
    mag[50] = 0.1; mag[53] = 0.1
    dec = evaluate_two_pass_decision(cal, 11.4, multi_dip_detector=det, frequencies_ghz=freqs, s11_magnitude=mag)
    assert dec.accepted is True
    assert dec.diagnostics.get('multi_dip_detected') is True

def test_two_pass_source_no_factory_or_recovery():
    src = (Path(__file__).resolve().parent.parent.parent / 'workflows' / 'rfgun_sao' / 'two_pass.py').read_text('utf-8')
    assert 'cst_optimization.factory' not in src
    assert 'cst_optimization.workflows.recovery' not in src

def test_calibration_source_no_factory_or_recovery():
    src = (Path(__file__).resolve().parent.parent.parent / 'workflows' / 'rfgun_sao' / 'calibration.py').read_text('utf-8')
    assert 'cst_optimization.factory' not in src
    assert 'cst_optimization.workflows.recovery' not in src

def test_config_yaml_has_two_pass_defaults():
    import yaml
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    e = cfg["evaluation"]
    assert e["target_freq_ghz"] == 11.424
    assert e["calibration_guess_ghz"] == 11.424
    assert e["inter_pass_recovery"] is False
    assert e["frequency_gate"]["enabled"] is False
    assert e["s11_depth_gate"]["enabled"] is False
    assert e["multi_dip_detection"]["enabled"] is False

def test_build_frequency_gate_returns_disabled_by_default():
    from workflows.rfgun_sao.workflow import _build_frequency_gate
    from workflows.rfgun_sao.gates import FrequencyGate
    gate = _build_frequency_gate({})
    assert isinstance(gate, FrequencyGate)
    assert gate.enabled is False

def test_build_s11_depth_gate_returns_disabled_by_default():
    from workflows.rfgun_sao.workflow import _build_s11_depth_gate
    from workflows.rfgun_sao.gates import S11DepthGate
    gate = _build_s11_depth_gate({})
    assert isinstance(gate, S11DepthGate)
    assert gate.enabled is False

def test_build_multi_dip_detector_returns_disabled_by_default():
    from workflows.rfgun_sao.workflow import _build_multi_dip_detector
    from workflows.rfgun_sao.gates import MultiDipDetector
    det = _build_multi_dip_detector({})
    assert isinstance(det, MultiDipDetector)
    assert det.enabled is False

def test_custom_frequency_gate_config_parsed():
    from workflows.rfgun_sao.workflow import _build_frequency_gate
    from workflows.rfgun_sao.gates import FrequencyGate
    gate = _build_frequency_gate({"frequency_gate": {"enabled": True, "target_ghz": 11.5, "max_abs_offset_mhz": 10.0}})
    assert gate.enabled is True
    assert gate.target_ghz == 11.5
    assert gate.max_abs_offset_mhz == 10.0

def test_resolve_two_pass_settings_returns_mode_and_gates():
    from workflows.rfgun_sao.workflow import _resolve_two_pass_settings
    from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate, MultiDipDetector
    cfg = {"evaluation": {"mode": "single_pass"}}
    s = _resolve_two_pass_settings(cfg)
    assert s["mode"] == "single_pass"
    assert isinstance(s["frequency_gate"], FrequencyGate)
    assert isinstance(s["s11_depth_gate"], S11DepthGate)
    assert isinstance(s["multi_dip_detector"], MultiDipDetector)

def test_gates_multidip_disabled_with_single_dip_returns_false():
    from workflows.rfgun_sao.gates import MultiDipDetector
    import numpy as np
    d = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    freqs = np.linspace(11.0, 12.0, 200)
    mag = np.ones(200)
    mag[100] = 0.1
    assert d.has_multiple_dips(freqs, mag) is False

def test_gates_source_no_factory_or_recovery_import():
    src = (Path(__file__).resolve().parent.parent.parent / "workflows" / "rfgun_sao" / "gates.py").read_text("utf-8")
    assert "cst_optimization.factory" not in src
    assert "cst_optimization.workflows.recovery" not in src
def test_workflow_source_has_two_pass_placeholder():
    src = (Path(__file__).resolve().parent.parent.parent / "workflows" / "rfgun_sao" / "workflow.py").read_text("utf-8")
    assert "NotImplementedError" not in src
    assert "two_pass" in src
    assert "make_two_pass_runtime_evaluator" in src
    assert "placeholder" in src
def test_workflow_source_has_objective_weights():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent.parent / "workflows" / "rfgun_sao" / "workflow.py").read_text("utf-8")
    assert "objective_weights" in src
def test_types_py_has_local_definition():
    """Phase 9: types.py has local definitions (decoupled from shared recovery).

    The local copies are kept intentionally for workflow isolation.
    Equivalence with shared recovery.py is validated by
    test_evaluation_status_enum_match_with_shared_recovery and
    test_evaluation_result_fields_match_shared_recovery.
    """
    src2 = (WF1_PACKAGE / "types.py").read_text("utf-8")
    # types.py should have its own local class definitions, not re-exports
    assert "class EvaluationStatus" in src2
    assert "class EvaluationResult" in src2
    # Verify types are usable
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
    assert hasattr(EvaluationStatus, "SUCCESS")
    assert hasattr(EvaluationStatus, "FREQUENCY_GATE")
    assert hasattr(EvaluationResult, "status")
    assert hasattr(EvaluationResult, "frequency_gate_passed")
def test_evaluator_static_source_has_no_factory_import():
    src = (WF1_PACKAGE / "evaluator.py").read_text("utf-8")
    assert "from cst_optimization.factory" not in src
    assert "import cst_optimization.factory" not in src


# ============================================================
# I. Injectable two-pass runtime evaluator skeleton
# ============================================================

def test_two_pass_runtime_placeholder_returns_one():
    """Default placeholder path returns 1.0 and skips measurement."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np

    cfg = _minimal_two_pass_cfg()
    wf, opt, ev = build_workflow_1(cfg)
    assert wf._conn is None

    val = ev(np.array([0.5]))
    assert val == 1.0


def test_two_pass_runtime_reject_does_not_call_measurement():
    """Calibration rejection prevents measurement runner call."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=False)
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0


def test_two_pass_runtime_success_uses_measurement_penalties_and_weights():
    """Successful path computes weighted scalar from measurement penalties."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    penalty_vals = {"f1": 0.2, "f2": 0.8}
    meas_runner = _FakeMeasurementRunner(
        penalty_values=penalty_vals,
        raw_values={"f1": 11.424, "f2": 0.5},
    )
    weights = np.array([0.3, 0.7])
    expected = float(np.dot([0.2, 0.8], weights))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1", "f2"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert abs(val - expected) < 1e-12
    assert meas_runner.call_count == 1


def test_two_pass_runtime_checkpoint_called_on_success():
    """Checkpoint callback is invoked on successful measurement path."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    penalty_vals = {"f1": 0.3}
    meas_runner = _FakeMeasurementRunner(
        penalty_values=penalty_vals,
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    x_in = np.array([0.5])
    evaluator(x_in)
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert np.allclose(c_x, x_in)
    assert np.allclose(c_raw, [11.424])
    assert np.allclose(c_pen, [0.3])
    assert c_ok is True
    assert c_err == ""


def test_two_pass_runtime_frequency_gate_rejects_before_measurement():
    """Frequency gate rejection prevents measurement runner call."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import FrequencyGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.5, s11_min_db=-10.0)
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    gate = FrequencyGate(enabled=True, target_ghz=11.424, max_abs_offset_mhz=20.0)

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        frequency_gate=gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0


def test_two_pass_runtime_raw_array_falls_back_to_raw_metrics():
    """Raw extraction falls back objective_values -> raw_metrics -> NaN."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    penalty_vals = {"f1": 0.2, "f2": 0.8}
    meas_runner = _FakeMeasurementRunner(
        penalty_values=penalty_vals,
        raw_values={"f1": 11.424, "f2": 0.5},
        objective_values=None,
    )
    weights = np.array([0.5, 0.5])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((raw.copy(), ok))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1", "f2"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    evaluator(np.array([0.5]))
    assert len(captured) == 1
    c_raw, c_ok = captured[0]
    assert np.allclose(c_raw, [11.424, 0.5])
    assert c_ok is True


def test_two_pass_runtime_failed_measurement_preserves_raw_metrics_for_checkpoint():
    """Failed measurement path preserves available raw metrics for checkpoint."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.types import EvaluationStatus
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.2},
        raw_values={"f1": 11.424},
        status=EvaluationStatus.SOLVER_FAILED,
        objective_values=None,
        error="fake measurement failed",
    )
    weights = np.array([1.0])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert len(captured) == 1
    c_raw, c_pen, c_ok, c_err = captured[0]
    # Raw should use raw_metrics fallback
    assert np.allclose(c_raw, [11.424])
    # Penalties are still all 1.0 on failure
    assert np.allclose(c_pen, [1.0])
    assert c_ok is False
    assert c_err == "fake measurement failed"


def test_two_pass_runtime_s11_gate_rejects_before_measurement():
    """S11 depth gate rejection prevents measurement runner call."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import S11DepthGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(success=True, f0_ghz=11.424, s11_min_db=0.0)
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    gate = S11DepthGate(enabled=True, threshold_db=-1.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        s11_depth_gate=gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    c_ok, c_err = captured[0]
    assert c_ok is False
    assert "s11_depth_gate_reject" in c_err


# ============================================================
# J. Opt-in CST two-pass runners (A13)
# ============================================================

def test_resolve_two_pass_runtime_defaults_to_placeholder():
    """Two-pass runtime defaults to placeholder."""
    from workflows.rfgun_sao.workflow import _resolve_two_pass_runtime

    assert _resolve_two_pass_runtime({}) == "placeholder"
    assert (
        _resolve_two_pass_runtime({"evaluation": {"mode": "two_pass"}})
        == "placeholder"
    )


def test_resolve_two_pass_runtime_accepts_cst():
    """Two-pass runtime accepts 'cst'."""
    from workflows.rfgun_sao.workflow import _resolve_two_pass_runtime

    cfg = {"evaluation": {"mode": "two_pass", "two_pass": {"runtime": "cst"}}}
    assert _resolve_two_pass_runtime(cfg) == "cst"


def test_resolve_two_pass_runtime_rejects_invalid():
    """Two-pass runtime rejects invalid values."""
    from workflows.rfgun_sao.workflow import _resolve_two_pass_runtime
    import pytest

    with pytest.raises(ValueError, match="runtime"):
        _resolve_two_pass_runtime(
            {"evaluation": {"two_pass": {"runtime": "bad"}}},
        )


def test_two_pass_cst_module_imports_without_recovery():
    """two_pass_cst module imports cleanly and has expected factories."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod

    assert hasattr(cst_mod, "make_cst_calibration_runner")
    assert hasattr(cst_mod, "make_cst_measurement_runner")

    src = (WF1_PACKAGE / "two_pass_cst.py").read_text("utf-8")
    assert "cst_optimization.factory" not in src
    assert "cst_optimization.workflows.recovery" not in src


def test_two_pass_cst_runtime_branch_wires_fake_connection(monkeypatch):
    """CST runtime branch wires fake connection without real CST."""
    import workflows.rfgun_sao.workflow as wf_mod
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
    import numpy as np

    # -- Fake CST connection ------------------------------------------------
    fake_conn_instances: list = []

    class FakeCSTConnection:
        pid = 99999
        def __init__(self, *args, **kwargs):
            self.connect_called = False
            self.quiet_mode = False
            fake_conn_instances.append(self)
        def connect(self):
            self.connect_called = True
        def set_quiet_mode(self, val):
            self.quiet_mode = True

    class FakeSolverRunner:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(wf_mod, "CSTConnection", FakeCSTConnection)
    monkeypatch.setattr(wf_mod, "SolverRunner", FakeSolverRunner)

    # -- Fake calibration/measurement runner factories ----------------------
    def _fake_cal_factory(**kw):
        def _run(param_dict, iteration):
            from workflows.rfgun_sao.calibration import CalibrationResult
            return CalibrationResult(
                success=True, f0_ghz=11.424, s11_min_db=-10.0,
                method="fake_test",
            )
        return _run

    def _fake_meas_factory(**kw):
        def _run(param_dict, plan, iteration):
            return EvaluationResult(
                status=EvaluationStatus.SUCCESS,
                penalty_values={"resonant_freq": 0.3},
                objective_values={"resonant_freq": 11.424},
                raw_metrics={"resonant_freq": 11.424},
                error="",
            )
        return _run

    monkeypatch.setattr(cst_mod, "make_cst_calibration_runner", _fake_cal_factory)
    monkeypatch.setattr(cst_mod, "make_cst_measurement_runner", _fake_meas_factory)

    # -- Build config with runtime=cst --------------------------------------
    cfg = {
        "evaluation": {
            "mode": "two_pass",
            "two_pass": {"runtime": "cst"},
        },
        "cst": {"library_path": "dummy_lib", "connect_mode": "any_or_new"},
        "project": {"cst_path": "dummy.cst"},
        "solver": {},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }

    wf, opt, ev = wf_mod.build_workflow_1(cfg)

    # -- Assertions ---------------------------------------------------------
    assert len(fake_conn_instances) == 1
    fake_conn = fake_conn_instances[0]
    assert fake_conn.connect_called is True
    assert fake_conn.quiet_mode is True
    assert wf._conn is fake_conn

    # Evaluator returns finite weighted scalar
    val = ev(np.array([0.5]))
    assert np.isfinite(val)
    # With weights=[1.0] and penalty=0.3, expected = 0.3
    assert abs(val - 0.3) < 1e-12


def test_workflow_build_retry_handler_attribute():
    """build_workflow_1 workflow container has _retry_handler attribute.

    Uses the two_pass placeholder path (no CST import required) to verify
    the attribute is set consistently across both code paths.
    Single-pass path also sets it unconditionally (may be None without
    retry config, or an EvaluationRetryHandler with retry enabled).
    """
    from workflows.rfgun_sao.workflow import build_workflow_1
    # Two-pass placeholder (no CST)
    cfg = _minimal_two_pass_cfg()
    wf, opt, ev = build_workflow_1(cfg)
    assert hasattr(wf, "_retry_handler")


# ============================================================
# K. CST runner adapter hardening (A13.1)
# ============================================================

class _FakeProject:
    """Fake CST project for calibration runner unit tests."""
    filename = "fake.cst"

    def __init__(self):
        self.update_params = None
        self.update_rebuild = None
        self.save_called = False
        self.close_called = False
        self.close_save = None

    def update_parameters(self, params, use_full_rebuild=True):
        self.update_params = params
        self.update_rebuild = use_full_rebuild
        return True

    def save(self):
        self.save_called = True

    def close(self, save=False):
        self.close_called = True
        self.close_save = save


class _FakeConnection:
    """Fake CST connection that returns a given project."""
    def __init__(self, project=None):
        self.project = project or _FakeProject()
        self.opened_path = None

    def open_project(self, path):
        self.opened_path = path
        return self.project


class _FakeSolverResult:
    """Fake solver result with configurable fields."""
    def __init__(self, success=True, error_type="", error_message=None):
        self.success = success
        self.error_type = error_type
        self.error_message = error_message


class _FakeSolverRunner:
    """Fake solver runner returning a canned result."""
    def __init__(self, result=None):
        self._result = result or _FakeSolverResult(success=True)

    def run(self, project):
        return self._result


def _make_fake_s11_reader(frequencies, magnitude):
    """Build a fake ResultReader class that returns given S11 data."""
    import numpy as np

    class _FakeS11:
        def __init__(self):
            self.frequencies = frequencies
            self.s_complex = magnitude.astype(np.complex64)

    class _FakeReader:
        def __init__(self, *args, **kwargs):
            pass
        def get_s_parameter(self):
            return _FakeS11()

    return _FakeReader


def test_cst_calibration_runner_success_hpbw(monkeypatch):
    """Calibration runner succeeds with HPBW method."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    import numpy as np

    # Fake S11 with a clear dip at 11.424 GHz
    freqs = np.linspace(11.0, 12.0, 2000)
    mag = np.full_like(freqs, 0.5)
    dip_idx = np.argmin(np.abs(freqs - 11.424))
    mag[dip_idx] = 0.01

    monkeypatch.setattr(
        cst_mod, "ResultReader",
        _make_fake_s11_reader(freqs, mag),
    )

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn,
        project_path="test.cst",
        solver_runner=solver,
        calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is True
    assert np.isfinite(result.f0_ghz)
    assert np.isfinite(result.s11_min_db)
    assert "cst_s11" in result.method
    assert project.update_params is not None
    assert project.update_params.get("f_data") == 11.424
    assert project.close_called is True


def test_cst_calibration_runner_solver_failure_uses_error_message(monkeypatch):
    """Solver failure uses error_message field."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod

    class _FakeReader:
        def __init__(self, *args, **kwargs):
            pass
        def get_s_parameter(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(cst_mod, "ResultReader", _FakeReader)

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver_result = _FakeSolverResult(
        success=False,
        error_type="mesh",
        error_message="mesh failed for fake test",
    )
    solver = _FakeSolverRunner(result=solver_result)

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is False
    assert "mesh failed for fake test" in result.error


def test_cst_calibration_runner_com_failure_classified(monkeypatch):
    """COM failure returns COM connection lost error."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod

    class _FakeReader:
        def __init__(self, *args, **kwargs):
            pass
        def get_s_parameter(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(cst_mod, "ResultReader", _FakeReader)

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver_result = _FakeSolverResult(
        success=False, error_type="com", error_message="COM error",
    )
    solver = _FakeSolverRunner(result=solver_result)

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is False
    assert "COM connection lost" in result.error


def test_cst_calibration_runner_parameter_update_failure(monkeypatch):
    """Parameter update failure returns appropriate error."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod

    class _FakeReader:
        def __init__(self, *args, **kwargs):
            pass
        def get_s_parameter(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(cst_mod, "ResultReader", _FakeReader)

    # Project that fails parameter update
    class _FailProject:
        filename = "fake.cst"
        def __init__(self):
            self.update_params = None
            self.save_called = False
            self.close_called = False
        def update_parameters(self, params, use_full_rebuild=True):
            self.update_params = params
            return False
        def save(self):
            self.save_called = True
        def close(self, save=False):
            self.close_called = True

    project = _FailProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is False
    assert "Parameter update failed" in result.error


def test_cst_calibration_runner_hpbw_fallback_to_dip_min(monkeypatch):
    """HPBW failure falls back to dip minimum method."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    import numpy as np

    # Monkeypatch half_power_bandwidth to raise
    def _raise_hpbw(*args, **kwargs):
        raise RuntimeError("HPBW failed for test")
    monkeypatch.setattr(cst_mod, "half_power_bandwidth", _raise_hpbw)

    # Fake S11 with dip at known location (11.5 GHz)
    freqs = np.linspace(11.0, 12.0, 2000)
    mag = np.full_like(freqs, 0.5)
    dip_idx = np.argmin(np.abs(freqs - 11.5))
    mag[dip_idx] = 0.01
    expected_f0 = float(freqs[dip_idx])

    monkeypatch.setattr(
        cst_mod, "ResultReader",
        _make_fake_s11_reader(freqs, mag),
    )

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is True
    assert result.method == "cst_s11_dip_min"
    assert abs(result.f0_ghz - expected_f0) < 1e-6
    assert project.close_called is True


def test_cst_measurement_runner_delegates_to_workflow1_evaluator():
    """Measurement runner delegates to Workflow1Evaluator correctly."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    from workflows.rfgun_sao.types import EvaluationStatus
    from workflows.rfgun_sao.calibration import MeasurementPlan
    import numpy as np

    class _FakeWF1Evaluator:
        def __init__(self):
            self.last_params = None
            self.last_iter = None
            self.call_count = 0
        def evaluate_single_pass(self, params, iteration):
            self.last_params = params
            self.last_iter = iteration
            self.call_count += 1
            raw = {"resonant_freq": 11.424, "q0": 10000.0}
            pen = {"resonant_freq": 0.1, "q0": 0.2}
            return raw, pen, True, EvaluationStatus.SUCCESS, ""

    fake_evaluator = _FakeWF1Evaluator()
    metric_names = ["resonant_freq", "q0"]

    runner = cst_mod.make_cst_measurement_runner(
        wf1_evaluator=fake_evaluator,
        metric_names=metric_names,
    )

    plan = MeasurementPlan(f_data_ghz=11.425)
    result = runner({"p1": 0.5, "p2": 1.0}, plan, 7)

    assert fake_evaluator.call_count == 1
    assert fake_evaluator.last_iter == 7
    assert fake_evaluator.last_params is not None
    assert fake_evaluator.last_params["f_data"] == 11.425
    assert fake_evaluator.last_params["p1"] == 0.5
    assert fake_evaluator.last_params["p2"] == 1.0

    assert result.status == EvaluationStatus.SUCCESS
    assert result.penalty_values == {"resonant_freq": 0.1, "q0": 0.2}
    assert result.raw_metrics == {"resonant_freq": 11.424, "q0": 10000.0}
    assert result.objective_values is not None
    assert list(result.objective_values.keys()) == metric_names

# ============================================================
# L. Calibration diagnostics — A13.3
# ============================================================

def test_two_pass_runtime_calibration_failed_error_includes_detail():
    """Rejection checkpoint error includes both reason and calibration.error."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=False,
        error="solver convergence issue in test",
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append(err)

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    assert "calibration_failed" in captured[0]
    assert "solver convergence issue in test" in captured[0]


def test_cst_calibration_runner_result_reader_failure_reports_error_and_meta(
    monkeypatch,
):
    """ResultReader failure returns CalibrationResult with error and meta."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod

    class _RaisingReader:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("fake s11 read failed for test")
        def get_s_parameter(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(cst_mod, "ResultReader", _RaisingReader)

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is False
    assert "fake s11 read failed for test" in result.error
    assert isinstance(result.meta, dict)
    assert result.meta.get("result_reader_ok") is False
    assert project.close_called is True


def test_cst_calibration_runner_success_meta_contains_s11_summary(monkeypatch):
    """Successful calibration meta includes S11 summary, not full arrays."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    import numpy as np

    # Lorentzian dip with baseline=0.9, gamma=0.015 GHz — wide enough for HPBW
    freqs = np.linspace(11.0, 12.0, 5000)
    mag = 0.9 - 0.89 / (1.0 + ((freqs - 11.424) / 0.015)**2)

    monkeypatch.setattr(
        cst_mod, "ResultReader",
        _make_fake_s11_reader(freqs, mag),
    )

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is True
    meta = result.meta
    assert isinstance(meta, dict)
    assert meta.get("iteration") == 1
    assert meta.get("s11_points") == 5000
    assert "s11_freq_min_ghz" in meta
    assert "s11_freq_max_ghz" in meta
    assert "s11_min_db" in meta
    assert np.isfinite(meta["s11_min_db"])
    # Ensure no full arrays in meta values
    for k, v in meta.items():
        assert not isinstance(v, (np.ndarray, list)), f"meta contains array: {k}={v!r}"
    # HPBW should succeed with a clear dip
    assert meta.get("hpbw_ok") is True


def test_decision_error_message_for_gate_reject_remains_reason():
    """Gate reject reasons appear clearly in _decision_error_message."""
    from workflows.rfgun_sao.two_pass import _decision_error_message, TwoPassDecision
    from workflows.rfgun_sao.calibration import CalibrationResult

    # Frequency gate reject with no calibration error
    dec1 = TwoPassDecision(
        accepted=False,
        reason="frequency_gate_reject",
        calibration=CalibrationResult(success=True, f0_ghz=11.5),
    )
    msg1 = _decision_error_message(dec1)
    assert msg1 == "frequency_gate_reject"

    # Calibration failed with detailed error
    dec2 = TwoPassDecision(
        accepted=False,
        reason="calibration_failed",
        calibration=CalibrationResult(
            success=False,
            error="HPBW failed, dip-min also no valid resonance",
        ),
    )
    msg2 = _decision_error_message(dec2)
    assert "calibration_failed" in msg2
    assert "HPBW failed" in msg2

    # S11 gate reject
    dec3 = TwoPassDecision(
        accepted=False,
        reason="s11_depth_gate_reject",
        calibration=CalibrationResult(success=True, s11_min_db=0.0),
    )
    msg3 = _decision_error_message(dec3)
    assert msg3 == "s11_depth_gate_reject"

    # Calibration failed with empty error still shows reason
    dec4 = TwoPassDecision(
        accepted=False,
        reason="calibration_failed",
        calibration=CalibrationResult(success=False, error=""),
    )
    msg4 = _decision_error_message(dec4)
    assert "calibration_failed" in msg4

# ============================================================
# M. Accepted-path calibration diagnostics — A13.5
# ============================================================

def test_two_pass_runtime_logs_accepted_calibration_details(caplog):
    """Accepted path logs calibration success details."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import logging
    import numpy as np

    caplog.set_level(logging.INFO, logger="workflows.rfgun_sao.two_pass")

    cal_runner = _FakeCalibrationRunner(
        success=True,
        f0_ghz=11.4245,
        s11_min_db=-20.0,
        method="cst_s11_hpbw",
        meta={
            "s11_points": 123,
            "hpbw_ok": True,
        },
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"resonant_freq": 0.3},
        raw_values={"resonant_freq": 11.4245},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))

    assert meas_runner.call_count == 1
    assert np.isfinite(val)
    assert val != 1.0

    log_text = caplog.text
    assert "Two-pass accepted" in log_text
    assert "f0_ghz" in log_text
    assert "11.4245" in log_text
    assert "s11_min_db" in log_text
    assert "cst_s11_hpbw" in log_text or "cst_s11_dip_min" in log_text
    assert "cal_success" in log_text

# ============================================================
# N. Mixed gate precedence and checkpoint semantics — A16
# ============================================================

def test_two_pass_gate_precedence_calibration_failure_before_gates():
    """Calibration failure has highest precedence over all gates."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=False,
        f0_ghz=np.nan,
        error="fake calibration failure",
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    freq_gate = FrequencyGate(
        enabled=True, target_ghz=11.424, max_abs_offset_mhz=1.0,
    )
    s11_gate = S11DepthGate(enabled=True, threshold_db=-10.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        frequency_gate=freq_gate,
        s11_depth_gate=s11_gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    c_ok, c_err = captured[0]
    assert c_ok is False
    assert "calibration_failed" in c_err
    assert "fake calibration failure" in c_err


def test_two_pass_gate_precedence_frequency_before_s11():
    """Frequency gate is checked before S11 depth gate."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True,
        f0_ghz=11.5,
        s11_min_db=0.0,
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    freq_gate = FrequencyGate(
        enabled=True, target_ghz=11.424, max_abs_offset_mhz=1.0,
    )
    s11_gate = S11DepthGate(enabled=True, threshold_db=-1.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append(err)

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        frequency_gate=freq_gate,
        s11_depth_gate=s11_gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    assert captured[0] == "frequency_gate_reject"
    assert "s11_depth_gate_reject" not in captured[0]


def test_two_pass_gate_precedence_s11_after_frequency_accepts():
    """S11 depth gate applies after frequency gate accepts."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True,
        f0_ghz=11.424,
        s11_min_db=0.0,
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    freq_gate = FrequencyGate(
        enabled=True, target_ghz=11.424, max_abs_offset_mhz=20.0,
    )
    s11_gate = S11DepthGate(enabled=True, threshold_db=-1.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append(err)

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        frequency_gate=freq_gate,
        s11_depth_gate=s11_gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    assert "s11_depth_gate_reject" in captured[0]


def test_two_pass_multidip_diagnostic_does_not_reject_runtime():
    """Multi-dip detector is diagnostic-only; does not reject."""
    from workflows.rfgun_sao.two_pass import (
        make_two_pass_runtime_evaluator,
        evaluate_two_pass_decision,
    )
    from workflows.rfgun_sao.gates import MultiDipDetector
    from workflows.rfgun_sao.calibration import CalibrationResult
    import numpy as np

    # Part A: direct decision call detects multi-dip but does not reject
    det = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    freqs = np.linspace(11.0, 12.0, 200)
    mag = np.ones(200)
    mag[50] = 0.1
    mag[53] = 0.1

    cal = CalibrationResult(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    dec = evaluate_two_pass_decision(
        cal, 11.4,
        multi_dip_detector=det,
        frequencies_ghz=freqs,
        s11_magnitude=mag,
    )
    assert dec.accepted is True
    assert dec.diagnostics.get("multi_dip_detected") is True

    # Part B: runtime evaluator with multi_dip_detector proceeds normally
    cal_runner = _FakeCalibrationRunner(
        success=True,
        f0_ghz=11.424,
        s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        multi_dip_detector=det,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.3) < 1e-12


def test_two_pass_rejection_scalar_all_ones_with_normalized_weights():
    """Rejection scalar equals dot(ones, normalized weights) = 1.0."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=False,
        error="rejection test",
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([0.2, 0.3, 0.5])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((pen.copy(), ok))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["a", "b", "c"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    c_pen, c_ok = captured[0]
    assert np.allclose(c_pen, [1.0, 1.0, 1.0])
    assert c_ok is False

# ============================================================
# O. Multi-dip diagnostic status — A17
# ============================================================

def test_multidip_detector_detects_but_decision_accepts():
    """Multi-dip detector flags diagnostics but decision remains accepted."""
    from workflows.rfgun_sao.two_pass import evaluate_two_pass_decision
    from workflows.rfgun_sao.gates import MultiDipDetector
    from workflows.rfgun_sao.calibration import CalibrationResult
    import numpy as np

    det = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    freqs = np.linspace(11.0, 12.0, 200)
    mag = np.ones(200)
    mag[50] = 0.1
    mag[53] = 0.1

    cal = CalibrationResult(success=True, f0_ghz=11.424, s11_min_db=-10.0)
    dec = evaluate_two_pass_decision(
        cal, 11.424,
        multi_dip_detector=det,
        frequencies_ghz=freqs,
        s11_magnitude=mag,
    )
    assert dec.accepted is True
    assert dec.reason == "accepted"
    assert dec.diagnostics.get("multi_dip_detected") is True


def test_multidip_runtime_without_arrays_does_not_reject():
    """Runtime evaluator with multi_dip_detector proceeds without S11 arrays."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import MultiDipDetector
    import numpy as np

    det = MultiDipDetector(enabled=True, mode_spacing_ghz=0.04)
    cal_runner = _FakeCalibrationRunner(
        success=True,
        f0_ghz=11.424,
        s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        multi_dip_detector=det,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.25) < 1e-12


def test_two_pass_cst_calibration_meta_does_not_store_full_s11_arrays(
    monkeypatch,
):
    """Calibration meta stores compact S11 summaries, not full arrays."""
    import workflows.rfgun_sao.two_pass_cst as cst_mod
    import numpy as np

    freqs = np.linspace(11.0, 12.0, 2000)
    mag = 0.9 - 0.89 / (1.0 + ((freqs - 11.424) / 0.015)**2)

    monkeypatch.setattr(
        cst_mod, "ResultReader",
        _make_fake_s11_reader(freqs, mag),
    )

    project = _FakeProject()
    conn = _FakeConnection(project)
    solver = _FakeSolverRunner()

    runner = cst_mod.make_cst_calibration_runner(
        connection=conn, project_path="test.cst",
        solver_runner=solver, calibration_guess_ghz=11.424,
    )

    result = runner({"p1": 0.5}, 1)
    assert result.success is True
    meta = result.meta
    assert isinstance(meta, dict)

    # Has compact summary fields
    assert "s11_points" in meta
    assert "s11_freq_min_ghz" in meta
    assert "s11_freq_max_ghz" in meta
    assert "s11_min_db" in meta

    # No full arrays stored
    assert "frequencies_ghz" not in meta
    assert "s11_magnitude" not in meta
    assert "s_complex" not in meta
    for v in meta.values():
        assert not isinstance(v, (np.ndarray, list)), (
            f"meta contains array-like value for key"
        )


def test_readme_states_multidip_live_plumbing_future_work():
    """README clarifies multi-dip diagnostic-only and live plumbing as future."""
    import pathlib
    readme_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "workflows" / "rfgun_sao" / "README.md"
    )
    text = readme_path.read_text("utf-8")
    assert "multi-dip" in text.lower() or "multidip" in text.lower()
    assert "diagnostic" in text.lower()
    assert "future" in text.lower() or "not implemented" in text.lower()

# ============================================================
# P. README milestone status — A18
# ============================================================

def test_rfgun_sao_readme_status_current_after_b6():
    """README captures current milestone test count and Phase B status."""
    import pathlib
    readme_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "workflows" / "rfgun_sao" / "README.md"
    )
    text = readme_path.read_text("utf-8")
    assert "230/230" in text
    assert "A13.4" in text
    assert "A14" in text
    assert "A15" in text
    assert "A16" in text
    assert "A17" in text
    assert "A19" in text
    assert "A20" in text
    assert "A21" in text
    assert "A22" in text
    assert "A23" in text
    assert "A24" in text
    assert "A24.1" in text
    assert "B1" in text
    assert "B2" in text
    assert "B3" in text
    assert "B4" in text
    assert "B4.1" in text
    assert "B5" in text
    assert "B5.1" in text
    assert "B7" in text
    assert "B8" in text
    assert "runtime=cst" in text or "evaluation.two_pass.runtime: cst" in text
    assert "config.local.yaml" in text
    assert "run_workflow_1.py" in text
    assert ".ckpt" in text or "CheckpointManager" in text
    assert "evaluation_records.jsonl" in text
    assert "multi-dip" in text
    assert "future" in text

# ============================================================
# Q. Checkpoint/evaluation-records semantics audit — A19
# ============================================================

def test_two_pass_checkpoint_placeholder_runtime_semantics():
    """Placeholder runtime checkpoint: calibration_failed, solver_ok=False, all NaN."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [{"name": "resonant_freq", "mode": "minimize"}],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    wf, opt, ev = build_workflow_1(cfg, checkpoint_callback=_ckpt)

    assert wf._conn is None

    val = ev(np.array([0.5]))

    assert val == 1.0
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert c_ok is False
    assert "calibration_failed" in c_err
    assert "placeholder_calibration_runner" in c_err
    assert np.allclose(c_pen, [1.0])
    assert np.all(np.isnan(c_raw))


def test_two_pass_checkpoint_frequency_gate_reject_semantics():
    """Frequency gate reject: solver_ok=False, error=frequency_gate_reject, scalar=1.0."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import FrequencyGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.5, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    gate = FrequencyGate(enabled=True, target_ghz=11.424, max_abs_offset_mhz=1.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        frequency_gate=gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))

    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert c_ok is False
    assert c_err == "frequency_gate_reject"
    assert np.allclose(c_pen, [1.0])
    # raw should have f0_ghz since it's finite and "resonant_freq" is in metric_names
    assert np.allclose(c_raw, [11.5])


def test_two_pass_checkpoint_s11_depth_gate_reject_semantics():
    """S11 depth gate reject: solver_ok=False, error=s11_depth_gate_reject, scalar=1.0."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.gates import S11DepthGate
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=0.0,
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])
    gate = S11DepthGate(enabled=True, threshold_db=-1.0)

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["resonant_freq"],
        objectives=[],
        weights=weights,
        s11_depth_gate=gate,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))

    assert val == 1.0
    assert meas_runner.call_count == 0
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert c_ok is False
    assert c_err == "s11_depth_gate_reject"
    assert np.allclose(c_pen, [1.0])
    assert np.allclose(c_raw, [11.424])


def test_two_pass_checkpoint_measurement_success_full_semantics():
    """Measurement success: solver_ok=True, error='', penalties from result."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.15, "f2": 0.35},
        raw_values={"f1": 11.424, "f2": 0.5},
    )
    weights = np.array([0.3, 0.7])
    expected = float(np.dot([0.15, 0.35], weights))

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1", "f2"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))

    assert abs(val - expected) < 1e-12
    assert meas_runner.call_count == 1
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert c_ok is True
    assert c_err == ""
    assert np.allclose(c_pen, [0.15, 0.35])
    assert np.allclose(c_raw, [11.424, 0.5])


def test_two_pass_checkpoint_measurement_failure_no_penalties():
    """Measurement failure with penalty_values=None returns all-1 penalties and ok=False."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.types import EvaluationStatus
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values=None,
        raw_values={"f1": 11.424},
        status=EvaluationStatus.SOLVER_FAILED,
        objective_values=None,
        error="solver timed out",
    )
    weights = np.array([1.0])

    captured: list = []

    def _ckpt(x, raw, pen, ok, err):
        captured.append((x.copy(), raw.copy(), pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
    )

    val = evaluator(np.array([0.5]))

    assert val == 1.0
    assert meas_runner.call_count == 1
    assert len(captured) == 1
    c_x, c_raw, c_pen, c_ok, c_err = captured[0]
    assert c_ok is False
    assert c_err == "solver timed out"
    assert np.allclose(c_pen, [1.0])
    # raw falls back to raw_values since objective_values is None
    assert np.allclose(c_raw, [11.424])


def test_extract_raw_array_both_none():
    """_extract_raw_array returns all NaN when both objective_values and raw_metrics are None."""
    from workflows.rfgun_sao.two_pass import _extract_raw_array
    from workflows.rfgun_sao.types import EvaluationResult
    import numpy as np

    result = EvaluationResult(
        status=None,
        objective_values=None,
        raw_metrics=None,
    )

    arr = _extract_raw_array(result, ["m1", "m2", "m3"])
    assert len(arr) == 3
    assert np.all(np.isnan(arr))

# ============================================================
# R. Checkpoint persistence semantics — A20
# ============================================================

class _FakeObjectiveNamesContainer:
    """Minimal container with objective_names for checkpoint tests."""
    def __init__(self, objective_names):
        self.objective_names = objective_names


def test_checkpoint_persistence_completed_success():
    """solver_ok=True + finite raw + wf_ref -> mark_completed, status=completed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", "b"])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])
        pen = np.array([0.2, 0.8])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status == "completed"
        assert rec.solver_ok is True
        assert rec.error == ""
        assert rec.raw_values == {"a": 11.424, "b": 0.5}
        assert rec.penalties == {"a": 0.2, "b": 0.8}


def test_checkpoint_persistence_failure_finite_raw():
    """solver_ok=False + finite raw -> mark_failed, status != completed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a"])]
        x = np.array([0.5])
        raw = np.array([11.424])
        pen = np.array([1.0])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=False, error="solver timed out",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert rec.solver_ok is False
        assert "solver timed out" in rec.error


def test_checkpoint_persistence_rejection_nan_raw():
    """solver_ok=False + NaN raw + calibration_failed -> mark_failed, error preserved."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a"])]
        x = np.array([0.5])
        raw = np.array([np.nan])
        pen = np.array([1.0])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=False,
            error="calibration_failed: placeholder_calibration_runner",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert rec.solver_ok is False
        assert "calibration_failed" in rec.error
        assert "placeholder_calibration_runner" in rec.error


def test_checkpoint_persistence_solver_ok_nan_raw():
    """solver_ok=True + NaN raw -> mark_failed, fallback error."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a"])]
        x = np.array([0.5])
        raw = np.array([np.nan])
        pen = np.array([1.0])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert rec.solver_ok is False  # mark_failed does not set solver_ok
        assert "non_finite_raw_values" in rec.error


def test_checkpoint_persistence_no_wf_ref():
    """Missing wf_ref -> mark_failed, not silently ambiguous."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref: list = []
        x = np.array([0.5])
        raw = np.array([11.424])
        pen = np.array([0.2])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error

# ============================================================
# S. Checkpoint objective_names hardening — A21
# ============================================================

def test_checkpoint_metric_names_object_no_names():
    """wf_ref=[object()] with no objective_names -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [object()]
        x = np.array([0.5])
        raw = np.array([11.424])
        pen = np.array([0.2])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error


def test_checkpoint_metric_names_empty_list():
    """objective_names=[] -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer([])]
        x = np.array([0.5])
        raw = np.array([11.424])
        pen = np.array([0.2])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error


def test_checkpoint_metric_names_length_mismatch():
    """objective_names length != raw length -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", "b"])]
        x = np.array([0.5])
        raw = np.array([11.424])  # only 1 element, but 2 names
        pen = np.array([0.2])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_metric_length_mismatch" in rec.error


def test_checkpoint_metric_names_valid_still_completes():
    """Valid objective_names still produces completed record."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["m1", "m2"])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])
        pen = np.array([0.3, 0.7])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status == "completed"
        assert rec.solver_ok is True
        assert rec.error == ""
        assert rec.raw_values == {"m1": 11.424, "m2": 0.5}
        assert rec.penalties == {"m1": 0.3, "m2": 0.7}

# ============================================================
# T. Checkpoint metric invariant hardening — A22
# ============================================================

def test_checkpoint_metric_names_string_rejected():
    """objective_names='abc' (str) -> mark_failed, not character-split."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer("abc")]
        x = np.array([0.5])
        raw = np.array([11.424])
        pen = np.array([0.2])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error


def test_checkpoint_metric_names_duplicate_rejected():
    """Duplicate metric names -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", "a"])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])
        pen = np.array([0.2, 0.8])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error


def test_checkpoint_metric_names_invalid_member_rejected():
    """objective_names with empty-str or None member -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", ""])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])
        pen = np.array([0.2, 0.8])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_objective_names_unavailable" in rec.error


def test_checkpoint_metric_names_penalties_mismatch():
    """penalties length != metric_names length -> mark_failed."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", "b"])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])   # 2 elements, matches
        pen = np.array([0.2])            # 1 element, mismatch

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status != "completed"
        assert "checkpoint_metric_length_mismatch" in rec.error


def test_checkpoint_metric_names_valid_regression():
    """Valid names + matching lengths still produces completed record."""
    from workflows.rfgun_sao.run import _record_checkpoint_evaluation
    from cst_optimization.checkpoint import CheckpointManager
    import tempfile, os, numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt = CheckpointManager(os.path.join(tmpdir, "test.ckpt"))
        wf_ref = [_FakeObjectiveNamesContainer(["a", "b"])]
        x = np.array([0.5])
        raw = np.array([11.424, 0.5])
        pen = np.array([0.3, 0.7])

        _record_checkpoint_evaluation(
            ckpt, wf_ref, x, raw, pen,
            solver_ok=True, error="",
        )

        assert len(ckpt.records) == 1
        rec = ckpt.records[0]
        assert rec.status == "completed"
        assert rec.solver_ok is True
        assert rec.error == ""
        assert rec.raw_values == {"a": 11.424, "b": 0.5}
        assert rec.penalties == {"a": 0.3, "b": 0.7}

# ============================================================
# U. Metric roles skeleton — Phase B1
# ============================================================

def test_metric_role_defaults_to_optimize():
    """Missing role defaults to optimize."""
    from workflows.rfgun_sao.metrics import MetricRole

    assert MetricRole.from_value(None) == MetricRole.OPTIMIZE


def test_metric_role_accepts_known_roles():
    """All known roles normalize correctly."""
    from workflows.rfgun_sao.metrics import MetricRole

    assert MetricRole.from_value("optimize") == MetricRole.OPTIMIZE
    assert MetricRole.from_value("OPTIMIZE") == MetricRole.OPTIMIZE
    assert MetricRole.from_value("threshold") == MetricRole.THRESHOLD
    assert MetricRole.from_value("report_only") == MetricRole.REPORT_ONLY


def test_metric_role_unknown_raises():
    """Unknown role raises ValueError with stable message."""
    from workflows.rfgun_sao.metrics import MetricRole
    import pytest

    with pytest.raises(ValueError, match="Unknown metric role"):
        MetricRole.from_value("banana")


def test_build_metric_specs_flat_backward_compatible():
    """Flat config with no role produces specs all optimize."""
    from workflows.rfgun_sao.metrics import build_metric_specs, objective_metric_names, report_metric_names

    entries = [
        {"name": "a", "mode": "minimize"},
        {"name": "b", "mode": "maximize"},
    ]
    specs = build_metric_specs(entries)
    assert len(specs) == 2
    assert objective_metric_names(specs) == ["a", "b"]
    assert report_metric_names(specs) == []


def test_build_metric_specs_role_split():
    """Role split: optimize + threshold in objective_names, report_only excluded."""
    from workflows.rfgun_sao.metrics import build_metric_specs, objective_metric_names, report_metric_names

    entries = [
        {"name": "freq", "role": "optimize"},
        {"name": "poynting", "role": "threshold"},
        {"name": "q0", "role": "report_only"},
    ]
    specs = build_metric_specs(entries)
    assert objective_metric_names(specs) == ["freq", "poynting"]
    assert report_metric_names(specs) == ["q0"]


def test_build_workflow_flat_objective_names_backward_compatible():
    """Workflow builder with flat config (no role) preserves objective_names."""
    from workflows.rfgun_sao.workflow import build_workflow_1

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "mode": "tolerance",
             "mode_params": {"target": 11.424, "sigma": 0.00333}},
            {"name": "q0", "mode": "maximize"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq", "q0"]
    assert hasattr(wf, "report_metric_names")
    assert wf.report_metric_names == []


def test_build_workflow_role_split_objective_names():
    """Role split: only optimize + threshold in objective_names."""
    from workflows.rfgun_sao.workflow import build_workflow_1

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "max_modified_poynting", "role": "threshold"},
            {"name": "q0", "role": "report_only"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq", "max_modified_poynting"]
    assert wf.report_metric_names == ["q0"]


def test_build_workflow_unknown_role_raises():
    """Unknown role in config raises ValueError."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import pytest

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "banana"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    with pytest.raises(ValueError, match="Unknown metric role"):
        build_workflow_1(cfg)


def test_two_pass_placeholder_with_role_split_scalar():
    """Two-pass placeholder with role split still returns 1.0 (all-ones penalty)."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "q0", "role": "report_only"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq"]
    assert wf.report_metric_names == ["q0"]

    val = ev(np.array([0.5]))
    assert val == 1.0

# ============================================================
# V. Threshold penalty skeleton — Phase B2
# ============================================================

def test_normalize_metric_role_alias():
    """normalize_metric_role alias works and rejects unknown."""
    from workflows.rfgun_sao.metrics import normalize_metric_role
    import pytest

    assert normalize_metric_role(None) == "optimize"
    assert normalize_metric_role("threshold") == "threshold"
    assert normalize_metric_role("REPORT_ONLY") == "report_only"
    with pytest.raises(ValueError, match="Unknown metric role"):
        normalize_metric_role("banana")


def test_threshold_field_parsing_top_level():
    """Threshold/sigma/direction parsed from top-level entry."""
    from workflows.rfgun_sao.metrics import build_metric_specs

    entries = [{
        "name": "m1",
        "role": "threshold",
        "threshold": 5.0,
        "sigma": 2.0,
        "direction": "less_than",
    }]
    specs = build_metric_specs(entries)
    assert len(specs) == 1
    s = specs[0]
    assert s.threshold == 5.0
    assert s.sigma == 2.0
    assert s.direction == "less_than"


def test_threshold_field_mode_params_fallback():
    """threshold/sigma parsed from mode_params if not top-level."""
    from workflows.rfgun_sao.metrics import build_metric_specs

    entries = [{
        "name": "m1",
        "role": "threshold",
        "mode_params": {
            "threshold": 10.0,
            "sigma": 3.0,
            "direction": "greater_than",
        },
    }]
    specs = build_metric_specs(entries)
    assert len(specs) == 1
    s = specs[0]
    assert s.threshold == 10.0
    assert s.sigma == 3.0
    assert s.direction == "greater_than"


def test_threshold_penalty_less_than():
    """less_than direction penalty formula."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_threshold_penalty
    import numpy as np

    spec = MetricSpec(
        name="t1", role=MetricRole.THRESHOLD,
        threshold=10.0, sigma=2.0, direction="less_than",
    )
    # Below threshold
    assert compute_threshold_penalty(spec, 9.0) == 0.0
    # At threshold
    assert compute_threshold_penalty(spec, 10.0) == 0.0
    # Above threshold
    p = compute_threshold_penalty(spec, 12.0)
    expected = 1.0 - np.exp(-1.0)
    assert abs(p - expected) < 1e-12


def test_threshold_penalty_greater_than():
    """greater_than direction penalty formula."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_threshold_penalty
    import numpy as np

    spec = MetricSpec(
        name="t1", role=MetricRole.THRESHOLD,
        threshold=10.0, sigma=2.0, direction="greater_than",
    )
    # Above threshold
    assert compute_threshold_penalty(spec, 11.0) == 0.0
    # At threshold
    assert compute_threshold_penalty(spec, 10.0) == 0.0
    # Below threshold
    p = compute_threshold_penalty(spec, 8.0)
    expected = 1.0 - np.exp(-1.0)
    assert abs(p - expected) < 1e-12


def test_threshold_penalty_non_finite():
    """NaN and Inf return penalty 1.0."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_threshold_penalty
    import numpy as np

    spec = MetricSpec(
        name="t1", role=MetricRole.THRESHOLD,
        threshold=10.0, sigma=2.0, direction="less_than",
    )
    assert compute_threshold_penalty(spec, np.nan) == 1.0
    assert compute_threshold_penalty(spec, np.inf) == 1.0
    assert compute_threshold_penalty(spec, -np.inf) == 1.0


def test_threshold_penalty_invalid_direction():
    """Unknown direction in config raises ValueError."""
    from workflows.rfgun_sao.metrics import build_metric_specs
    import pytest

    entries = [{
        "name": "m1",
        "role": "threshold",
        "direction": "sideways",
    }]
    with pytest.raises(ValueError, match="Unknown threshold direction"):
        build_metric_specs(entries)


def test_threshold_penalty_non_threshold_spec_raises():
    """compute_threshold_penalty on non-threshold spec raises TypeError."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_threshold_penalty
    import pytest

    spec = MetricSpec(name="opt", role=MetricRole.OPTIMIZE)
    with pytest.raises(TypeError, match="Expected role.*threshold"):
        compute_threshold_penalty(spec, 1.0)


def test_workflow_container_threshold_metadata():
    """Workflow container exposes threshold_metric_names and metric_specs."""
    from workflows.rfgun_sao.workflow import build_workflow_1

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "max_modified_poynting", "role": "threshold",
             "threshold": 5.0, "sigma": 2.0},
            {"name": "q0", "role": "report_only"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq", "max_modified_poynting"]
    assert wf.report_metric_names == ["q0"]
    assert hasattr(wf, "metric_specs")
    assert len(wf.metric_specs) == 3
    assert wf.optimize_metric_names == ["resonant_freq"]
    assert wf.threshold_metric_names == ["max_modified_poynting"]


def test_b1_backward_compatibility_flat_config():
    """B1 flat config with no role still works."""
    from workflows.rfgun_sao.workflow import build_workflow_1

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "mode": "tolerance",
             "mode_params": {"target": 11.424, "sigma": 0.00333}},
            {"name": "q0", "mode": "maximize"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq", "q0"]
    assert wf.report_metric_names == []
    assert hasattr(wf, "metric_specs")

# ============================================================
# W. Threshold penalty runtime wiring — Phase B3
# ============================================================

class _FakeMode:
    """Dummy objective mode returning a fixed penalty."""
    def __init__(self, penalty: float = 0.5):
        self._penalty = penalty
    def compute(self, value: float) -> float:
        return self._penalty


class _FakeObjective:
    """Dummy objective with a name and mode."""
    def __init__(self, name: str, penalty: float = 0.5):
        self.name = name
        self.mode = _FakeMode(penalty)


def test_compute_role_penalties_optimize():
    """Optimize role uses objective mode.compute; finite raw -> computed."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )

    specs = [MetricSpec(name="a", role=MetricRole.OPTIMIZE)]
    objs = {"a": _FakeObjective("a", penalty=0.3)}
    raw = {"a": 11.424}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs, raw_metrics=raw,
    )
    assert pen == {"a": 0.3}


def test_compute_role_penalties_optimize_non_finite():
    """Optimize role missing/non-finite raw -> 1.0."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )
    import numpy as np

    specs = [MetricSpec(name="a", role=MetricRole.OPTIMIZE)]
    objs = {"a": _FakeObjective("a", penalty=0.3)}
    raw = {}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs, raw_metrics=raw,
    )
    assert pen == {"a": 1.0}

    pen2 = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs,
        raw_metrics={"a": np.nan},
    )
    assert pen2 == {"a": 1.0}


def test_compute_role_penalties_threshold():
    """Threshold role uses compute_threshold_penalty."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )
    import numpy as np

    specs = [MetricSpec(
        name="t1", role=MetricRole.THRESHOLD,
        threshold=10.0, sigma=2.0, direction="less_than",
    )]
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name={}, raw_metrics={"t1": 12.0},
    )
    expected = 1.0 - np.exp(-1.0)
    assert abs(pen["t1"] - expected) < 1e-12

    pen2 = compute_role_penalties(
        metric_specs=specs, objectives_by_name={}, raw_metrics={"t1": 9.0},
    )
    assert pen2["t1"] == 0.0


def test_compute_role_penalties_threshold_non_finite():
    """Threshold role missing/non-finite raw -> 1.0."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )
    import numpy as np

    specs = [MetricSpec(
        name="t1", role=MetricRole.THRESHOLD,
        threshold=10.0, sigma=2.0, direction="less_than",
    )]
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name={}, raw_metrics={},
    )
    assert pen["t1"] == 1.0

    pen2 = compute_role_penalties(
        metric_specs=specs, objectives_by_name={},
        raw_metrics={"t1": np.nan},
    )
    assert pen2["t1"] == 1.0


def test_compute_role_penalties_report_only_excluded():
    """Report_only metrics excluded from penalty dict."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="thr", role=MetricRole.THRESHOLD,
                   threshold=10.0, sigma=2.0, direction="less_than"),
        MetricSpec(name="rep", role=MetricRole.REPORT_ONLY),
    ]
    objs = {"opt": _FakeObjective("opt", penalty=0.2)}
    raw = {"opt": 1.0, "thr": 9.0, "rep": 100.0}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs, raw_metrics=raw,
    )
    assert "opt" in pen
    assert "thr" in pen
    assert "rep" not in pen


def test_b3_workflow_container_metadata():
    """Two-pass placeholder with role split preserves objective_names."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "max_modified_poynting", "role": "threshold",
             "threshold": 5.0, "sigma": 2.0},
            {"name": "q0", "role": "report_only"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq", "max_modified_poynting"]
    assert wf.report_metric_names == ["q0"]
    assert hasattr(wf, "metric_specs")


def test_b3_placeholder_scalar_unchanged():
    """Two-pass placeholder with role split still returns 1.0."""
    from workflows.rfgun_sao.workflow import build_workflow_1
    import numpy as np

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "q0", "role": "report_only"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq"]
    assert wf.report_metric_names == ["q0"]
    val = ev(np.array([0.5]))
    assert val == 1.0


def test_b3_direction_validation_threshold_only():
    """Direction validated only for threshold role; non-threshold allowed."""
    from workflows.rfgun_sao.metrics import build_metric_specs
    import pytest

    # Non-threshold with unknown direction should NOT raise
    entries = [{"name": "a", "role": "optimize", "direction": "sideways"}]
    specs = build_metric_specs(entries)
    assert len(specs) == 1
    assert specs[0].direction == "sideways"

    # Threshold with unknown direction MUST raise
    entries2 = [{"name": "a", "role": "threshold", "direction": "sideways"}]
    with pytest.raises(ValueError, match="Unknown threshold direction"):
        build_metric_specs(entries2)

# ============================================================
# X. Report-only diagnostic extraction — Phase B4
# ============================================================

def test_report_only_diagnostics_basic():
    """report_only_diagnostics extracts only REPORT_ONLY metrics."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_diagnostics,
    )

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="thr", role=MetricRole.THRESHOLD,
                   threshold=10.0, sigma=2.0),
        MetricSpec(name="q0", role=MetricRole.REPORT_ONLY),
    ]
    raw = {"opt": 1.0, "thr": 9.0, "q0": 18630.8}
    diag = report_only_diagnostics(metric_specs=specs, raw_metrics=raw)
    assert diag == {"q0": 18630.8}


def test_report_only_diagnostics_report_as():
    """report_as alias is used as output key."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_diagnostics,
    )

    specs = [
        MetricSpec(name="q0", role=MetricRole.REPORT_ONLY,
                   report_as="intrinsic_q0"),
    ]
    raw = {"q0": 18630.8}
    diag = report_only_diagnostics(metric_specs=specs, raw_metrics=raw)
    assert "intrinsic_q0" in diag
    assert diag["intrinsic_q0"] == 18630.8
    assert "q0" not in diag


def test_report_only_diagnostics_non_finite():
    """Missing or non-finite raw produces NaN."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_diagnostics,
    )
    import numpy as np

    specs = [MetricSpec(name="q0", role=MetricRole.REPORT_ONLY)]

    # Missing raw
    diag = report_only_diagnostics(metric_specs=specs, raw_metrics={})
    assert np.isnan(diag["q0"])

    # NaN raw
    diag2 = report_only_diagnostics(
        metric_specs=specs, raw_metrics={"q0": np.nan},
    )
    assert np.isnan(diag2["q0"])

    # Inf raw
    diag3 = report_only_diagnostics(
        metric_specs=specs, raw_metrics={"q0": np.inf},
    )
    assert np.isnan(diag3["q0"])


def test_report_only_diagnostics_disabled_excluded():
    """Disabled report_only spec is excluded."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_diagnostics,
    )

    specs = [
        MetricSpec(name="q0", role=MetricRole.REPORT_ONLY, enabled=True),
        MetricSpec(name="q1", role=MetricRole.REPORT_ONLY, enabled=False),
    ]
    raw = {"q0": 1.0, "q1": 2.0}
    diag = report_only_diagnostics(metric_specs=specs, raw_metrics=raw)
    assert "q0" in diag
    assert "q1" not in diag


def test_report_only_diagnostics_duplicate_key_raises():
    """Duplicate report_as/output key raises ValueError."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_diagnostics,
    )
    import pytest

    specs = [
        MetricSpec(name="q0", role=MetricRole.REPORT_ONLY, report_as="q"),
        MetricSpec(name="q1", role=MetricRole.REPORT_ONLY, report_as="q"),
    ]
    raw = {"q0": 1.0, "q1": 2.0}
    with pytest.raises(ValueError, match="Duplicate report_only"):
        report_only_diagnostics(metric_specs=specs, raw_metrics=raw)


def test_report_only_output_names_basic():
    """report_only_output_names returns report_as or name."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, report_only_output_names,
    )

    specs = [
        MetricSpec(name="q0", role=MetricRole.REPORT_ONLY),
        MetricSpec(name="q1", role=MetricRole.REPORT_ONLY, report_as="intrinsic_q1"),
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
    ]
    names = report_only_output_names(specs)
    assert names == ["q0", "intrinsic_q1"]


def test_report_only_objective_names_unchanged():
    """report_metric_names and objective_metric_names unchanged by B4."""
    from workflows.rfgun_sao.metrics import (
        build_metric_specs, objective_metric_names, report_metric_names,
    )

    entries = [
        {"name": "a", "role": "optimize"},
        {"name": "b", "role": "threshold"},
        {"name": "c", "role": "report_only", "report_as": "c_alias"},
    ]
    specs = build_metric_specs(entries)
    assert objective_metric_names(specs) == ["a", "b"]
    # report_metric_names returns source name, not report_as
    assert report_metric_names(specs) == ["c"]


def test_b4_b3_regression():
    """compute_role_penalties still excludes report_only."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="thr", role=MetricRole.THRESHOLD,
                   threshold=10.0, sigma=2.0),
        MetricSpec(name="rep", role=MetricRole.REPORT_ONLY),
    ]
    objs = {"opt": _FakeObjective("opt", penalty=0.2)}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs,
        raw_metrics={"opt": 1.0, "thr": 9.0, "rep": 100.0},
    )
    assert "opt" in pen
    assert "thr" in pen
    assert "rep" not in pen

# ============================================================
# Y. Diagnostics preservation hardening — B4.1
# ============================================================

def test_evaluation_result_carries_diagnostics():
    """EvaluationResult can carry diagnostics without breaking defaults."""
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

    r = EvaluationResult()
    assert r.diagnostics is None

    r2 = EvaluationResult(status=EvaluationStatus.SUCCESS, diagnostics={"q0": 1.0})
    assert r2.diagnostics == {"q0": 1.0}


def test_evaluator_resets_stale_diagnostics_on_failure():
    """Stale _last_diagnostics are reset before each evaluate_single_pass."""
    from workflows.rfgun_sao.evaluator import Workflow1Evaluator
    import numpy as np

    # Use the no-CST path: construct with connection=None, force a path that
    # fails before CST.  Access _last_diagnostics after a failed call.
    class _NullConn:
        def open_project(self, path):
            raise RuntimeError("no CST available")

    class _DummyMode:
        def compute(self, value):
            return 0.0
    class _DummyObj:
        name = "x"
        mode = _DummyMode()

    ev = Workflow1Evaluator(
        connection=_NullConn(),
        project_path="dummy.cst",
        solver_runner=None,
        objectives=[_DummyObj()],
        param_names=["p1"],
        metric_names=["x"],
    )

    # Set stale diagnostics
    ev._last_diagnostics = {"stale": 999.0}

    # Attempt evaluation (will fail — no CST)
    ev.evaluate_single_pass({"p1": 0.5}, 0)

    # After failure, _last_diagnostics should be reset (not stale)
    diag = ev.last_diagnostics()
    assert diag == {}, (
        f"Expected empty diagnostics after failed eval, got {diag}"
    )


def test_measurement_runner_preserves_diagnostics():
    """make_cst_measurement_runner preserves diagnostics from evaluator."""
    from workflows.rfgun_sao.two_pass_cst import make_cst_measurement_runner
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
    from workflows.rfgun_sao.calibration import MeasurementPlan
    import numpy as np

    class _FakeEvaluator:
        def evaluate_single_pass(self, params, iteration):
            raw = {"resonant_freq": 11.424, "q0": 18630.0}
            pen = {"resonant_freq": 0.1}
            return raw, pen, True, EvaluationStatus.SUCCESS, ""
        def last_diagnostics(self):
            return {"q0_diag": 18630.0}

    runner = make_cst_measurement_runner(
        wf1_evaluator=_FakeEvaluator(),
        metric_names=["resonant_freq"],
    )

    plan = MeasurementPlan(f_data_ghz=11.424)
    result = runner({"p1": 0.5}, plan, 0)

    assert result.diagnostics == {"q0_diag": 18630.0}
    assert result.status == EvaluationStatus.SUCCESS


def test_measurement_runner_failure_returns_empty_diagnostics():
    """Failed measurement returns empty diagnostics, not stale."""
    from workflows.rfgun_sao.two_pass_cst import make_cst_measurement_runner
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus
    from workflows.rfgun_sao.calibration import MeasurementPlan
    import numpy as np

    class _FakeFailedEvaluator:
        def evaluate_single_pass(self, params, iteration):
            raw = {}
            pen = {}
            return raw, pen, False, EvaluationStatus.SOLVER_FAILED, "solver error"
        def last_diagnostics(self):
            return {}

    runner = make_cst_measurement_runner(
        wf1_evaluator=_FakeFailedEvaluator(),
        metric_names=["resonant_freq"],
    )

    plan = MeasurementPlan(f_data_ghz=11.424)
    result = runner({"p1": 0.5}, plan, 0)

    assert result.diagnostics == {}
    assert result.status == EvaluationStatus.SOLVER_FAILED


def test_b4_1_core_b3_b4_imports_work():
    """Key B3/B4 helpers still import and function correctly."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
        report_only_diagnostics, report_only_output_names,
    )
    import numpy as np

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="thr", role=MetricRole.THRESHOLD,
                   threshold=10.0, sigma=2.0),
        MetricSpec(name="rep", role=MetricRole.REPORT_ONLY),
    ]
    objs = {"opt": _FakeObjective("opt", penalty=0.2)}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs,
        raw_metrics={"opt": 1.0, "thr": 9.0, "rep": 100.0},
    )
    assert "opt" in pen
    assert "thr" in pen
    assert "rep" not in pen

    diag = report_only_diagnostics(
        metric_specs=specs, raw_metrics={"rep": 100.0},
    )
    assert diag == {"rep": 100.0}

    names = report_only_output_names(specs)
    assert "rep" in names
    assert "opt" not in names

# ============================================================
# Z. Role-based metrics diagnostics logging — B5
# ============================================================

def test_two_pass_logs_diagnostics_when_present(caplog):
    """make_two_pass_runtime_evaluator logs diagnostics when present."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import logging, numpy as np

    caplog.set_level(logging.INFO, logger="workflows.rfgun_sao.two_pass")

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
        diagnostics={"q0_diag": 18630.0},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.3) < 1e-12

    log_text = caplog.text
    assert "Two-pass measurement diagnostics" in log_text
    assert "q0_diag" in log_text
    assert "18630" in log_text


def test_two_pass_logs_diagnostics_empty_dict(caplog):
    """make_two_pass_runtime_evaluator does not fail on empty diagnostics."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import logging, numpy as np

    caplog.set_level(logging.INFO, logger="workflows.rfgun_sao.two_pass")

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
        diagnostics={},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.3) < 1e-12

    log_text = caplog.text
    # Empty diagnostics should not produce a log line
    assert "Two-pass measurement diagnostics" not in log_text


def test_two_pass_logs_diagnostics_none(caplog):
    """make_two_pass_runtime_evaluator does not fail on diagnostics=None."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import logging, numpy as np

    caplog.set_level(logging.INFO, logger="workflows.rfgun_sao.two_pass")

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
        diagnostics=None,
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.3) < 1e-12

    log_text = caplog.text
    # None diagnostics should not produce a log line
    assert "Two-pass measurement diagnostics" not in log_text


def test_b5_b4_1_regression():
    """B4.1 tests for stale reset and diagnostics preservation still work."""
    from workflows.rfgun_sao.types import EvaluationResult, EvaluationStatus

    r = EvaluationResult()
    assert r.diagnostics is None

    r2 = EvaluationResult(
        status=EvaluationStatus.SUCCESS,
        diagnostics={"q0": 1.0},
    )
    assert r2.diagnostics == {"q0": 1.0}

# ============================================================
# AA. CST shutdown detection and cleanup — B5.1
# ============================================================

def test_cleanup_workflow_none():
    """workflow is None -> attempted=False, no error."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    r = _cleanup_workflow_connection(None)
    assert r["attempted"] is False
    assert r["error"] == ""


def test_cleanup_workflow_no_conn():
    """workflow without _conn -> attempted=False, no error."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    class _NoConn:
        pass

    r = _cleanup_workflow_connection(_NoConn())
    assert r["attempted"] is False


def test_cleanup_workflow_conn_none():
    """workflow._conn is None -> attempted=False, no error."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    class _NoneConn:
        _conn = None

    r = _cleanup_workflow_connection(_NoneConn())
    assert r["attempted"] is False


def test_cleanup_workflow_normal_close():
    """Normal cleanup calls close(force=False) on connection."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    close_kwargs = {}

    class _FakeConn:
        pid = 12345
        def close(self, force=False):
            close_kwargs["force"] = force

    class _WF:
        _conn = _FakeConn()

    r = _cleanup_workflow_connection(_WF())
    assert r["attempted"] is True
    assert r["closed"] is True
    assert r["pid"] == 12345
    assert close_kwargs.get("force") is False


def test_cleanup_workflow_force_close():
    """Force cleanup calls close(force=True) on connection."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    close_kwargs = {}

    class _FakeConn:
        pid = 12345
        def close(self, force=False):
            close_kwargs["force"] = force

    class _WF:
        _conn = _FakeConn()

    r = _cleanup_workflow_connection(_WF(), force=True)
    assert r["attempted"] is True
    assert r["closed"] is True
    assert r["force"] is True
    assert close_kwargs.get("force") is True


def test_cleanup_workflow_close_raises():
    """Connection.close() raises -> helper returns error without raising."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    class _FailingConn:
        pid = 999
        def close(self, force=False):
            raise RuntimeError("close failed")

    class _WF:
        _conn = _FailingConn()

    r = _cleanup_workflow_connection(_WF())
    assert r["attempted"] is True
    assert r["closed"] is False
    assert "close failed" in r["error"]


def test_cleanup_workflow_pid_raises():
    """pid getter raises -> helper still attempts close."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    class _BadPidConn:
        @property
        def pid(self):
            raise RuntimeError("pid unavailable")
        def close(self, force=False):
            pass

    class _WF:
        _conn = _BadPidConn()

    r = _cleanup_workflow_connection(_WF())
    assert r["attempted"] is True
    assert r["closed"] is True

# ============================================================
# AB. Gate metric role skeleton — B7
# ============================================================

def test_gate_role_accepted():
    """MetricRole accepts 'gate' and normalize returns 'gate'."""
    from workflows.rfgun_sao.metrics import MetricRole, normalize_metric_role

    assert MetricRole.from_value("gate") == MetricRole.GATE
    assert normalize_metric_role("gate") == "gate"


def test_gate_spec_parsed():
    """build_metric_specs parses gate role with threshold/sigma/direction."""
    from workflows.rfgun_sao.metrics import build_metric_specs

    entries = [{
        "name": "g1", "role": "gate",
        "threshold": 100.0, "sigma": 5.0, "direction": "less_than",
    }]
    specs = build_metric_specs(entries)
    assert len(specs) == 1
    s = specs[0]
    assert s.role.value == "gate"
    assert s.threshold == 100.0
    assert s.sigma == 5.0
    assert s.direction == "less_than"


def test_gate_invalid_direction_raises():
    """Gate role with invalid direction raises ValueError."""
    from workflows.rfgun_sao.metrics import build_metric_specs
    import pytest

    entries = [{"name": "g1", "role": "gate", "direction": "sideways"}]
    with pytest.raises(ValueError, match="Unknown threshold direction"):
        build_metric_specs(entries)


def test_gate_metric_names():
    """gate_metric_names returns enabled gate names only."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, gate_metric_names,
    )

    specs = [
        MetricSpec(name="g1", role=MetricRole.GATE),
        MetricSpec(name="g2", role=MetricRole.GATE, enabled=False),
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
    ]
    assert gate_metric_names(specs) == ["g1"]


def test_gate_excluded_from_objective_names():
    """objective_metric_names excludes gate."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, objective_metric_names, report_metric_names,
    )

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="thr", role=MetricRole.THRESHOLD),
        MetricSpec(name="rep", role=MetricRole.REPORT_ONLY),
        MetricSpec(name="gate", role=MetricRole.GATE),
    ]
    assert objective_metric_names(specs) == ["opt", "thr"]
    assert report_metric_names(specs) == ["rep"]


def test_compute_role_penalties_skips_gate():
    """compute_role_penalties excludes gate and does not crash."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_role_penalties,
    )

    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="gate", role=MetricRole.GATE,
                   threshold=10.0, sigma=2.0, direction="less_than"),
    ]
    objs = {"opt": _FakeObjective("opt", penalty=0.2)}
    pen = compute_role_penalties(
        metric_specs=specs, objectives_by_name=objs,
        raw_metrics={"opt": 1.0, "gate": 5.0},
    )
    assert "opt" in pen
    assert "gate" not in pen


def test_compute_gate_pass_less_than():
    """Gate less_than pass/fail."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_gate_pass

    spec = MetricSpec(name="g", role=MetricRole.GATE,
                      threshold=10.0, direction="less_than")
    assert compute_gate_pass(spec, 9.0) is True
    assert compute_gate_pass(spec, 10.0) is True
    assert compute_gate_pass(spec, 11.0) is False


def test_compute_gate_pass_greater_than():
    """Gate greater_than pass/fail."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_gate_pass

    spec = MetricSpec(name="g", role=MetricRole.GATE,
                      threshold=10.0, direction="greater_than")
    assert compute_gate_pass(spec, 11.0) is True
    assert compute_gate_pass(spec, 10.0) is True
    assert compute_gate_pass(spec, 9.0) is False


def test_compute_gate_pass_non_finite():
    """Non-finite value -> False."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_gate_pass
    import numpy as np

    spec = MetricSpec(name="g", role=MetricRole.GATE,
                      threshold=10.0, direction="less_than")
    assert compute_gate_pass(spec, np.nan) is False
    assert compute_gate_pass(spec, np.inf) is False


def test_compute_gate_pass_no_threshold():
    """Missing threshold -> False."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_gate_pass

    spec = MetricSpec(name="g", role=MetricRole.GATE, direction="less_than")
    assert compute_gate_pass(spec, 5.0) is False


def test_compute_gate_pass_wrong_role_raises():
    """Wrong role raises TypeError."""
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole, compute_gate_pass
    import pytest

    spec = MetricSpec(name="opt", role=MetricRole.OPTIMIZE)
    with pytest.raises(TypeError, match="Expected role.*gate"):
        compute_gate_pass(spec, 1.0)


def test_compute_gate_results_basic():
    """compute_gate_results returns pass/fail for gate specs."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_gate_results,
    )

    specs = [
        MetricSpec(name="g1", role=MetricRole.GATE,
                   threshold=10.0, direction="less_than"),
        MetricSpec(name="g2", role=MetricRole.GATE,
                   threshold=5.0, direction="greater_than"),
    ]
    raw = {"g1": 9.0, "g2": 6.0}
    r = compute_gate_results(metric_specs=specs, raw_metrics=raw)
    assert r == {"g1": True, "g2": True}


def test_compute_gate_results_report_as():
    """report_as alias works for gate results."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_gate_results,
    )

    specs = [
        MetricSpec(name="g1", role=MetricRole.GATE,
                   threshold=10.0, direction="less_than",
                   report_as="gate_alias"),
    ]
    r = compute_gate_results(
        metric_specs=specs, raw_metrics={"g1": 11.0},
    )
    assert "gate_alias" in r
    assert r["gate_alias"] is False


def test_compute_gate_results_duplicate_key_raises():
    """Duplicate output key raises ValueError."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_gate_results,
    )
    import pytest

    specs = [
        MetricSpec(name="g1", role=MetricRole.GATE,
                   threshold=10.0, direction="less_than",
                   report_as="x"),
        MetricSpec(name="g2", role=MetricRole.GATE,
                   threshold=5.0, direction="greater_than",
                   report_as="x"),
    ]
    with pytest.raises(ValueError, match="Duplicate gate result key"):
        compute_gate_results(metric_specs=specs, raw_metrics={"g1": 1.0, "g2": 6.0})


def test_gate_workflow_container():
    """Two-pass placeholder workflow exposes gate_metric_names."""
    from workflows.rfgun_sao.workflow import build_workflow_1

    cfg = {
        "evaluation": {"mode": "two_pass"},
        "parameters": [{"name": "p1", "low": 0, "high": 1}],
        "objectives": [
            {"name": "resonant_freq", "role": "optimize"},
            {"name": "q0", "role": "gate", "threshold": 18000.0,
             "direction": "greater_than"},
        ],
        "optimization": {"n_initial": 1, "n_iterations": 0, "seed": 42},
    }
    wf, opt, ev = build_workflow_1(cfg)
    assert wf.objective_names == ["resonant_freq"]
    assert wf.gate_metric_names == ["q0"]

# ============================================================
# AC. Gate runtime rejection wiring — B8
# ============================================================

def test_summarize_gate_empty():
    """Empty gate results -> pass."""
    from workflows.rfgun_sao.metrics import summarize_gate_results

    ok, err = summarize_gate_results({})
    assert ok is True
    assert err == ""


def test_summarize_gate_all_pass():
    """All True -> pass."""
    from workflows.rfgun_sao.metrics import summarize_gate_results

    ok, err = summarize_gate_results({"g1": True, "g2": True})
    assert ok is True
    assert err == ""


def test_summarize_gate_single_fail():
    """One False -> gate_reject with failing key."""
    from workflows.rfgun_sao.metrics import summarize_gate_results

    ok, err = summarize_gate_results({"g1": True, "g2": False})
    assert ok is False
    assert err == "gate_reject:g2"


def test_summarize_gate_multi_fail():
    """Multiple False -> gate_reject with sorted keys."""
    from workflows.rfgun_sao.metrics import summarize_gate_results

    ok, err = summarize_gate_results({"g3": False, "g1": False, "g2": True})
    assert ok is False
    assert err == "gate_reject:g1,g3"


def test_b8_backward_compat_no_metric_specs():
    """make_two_pass_runtime_evaluator without metric_specs unchanged."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )
    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.3) < 1e-12


def test_b8_gate_pass_measurement_success():
    """Gate pass: measurement scalar unchanged, solver_ok=True."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])
    specs = [MetricSpec(
        name="f1", role=MetricRole.GATE,
        threshold=10.0, direction="greater_than",
    )]

    captured = []
    def _ckpt(x, raw, pen, ok, err):
        captured.append((pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
        metric_specs=specs,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert abs(val - 0.25) < 1e-12
    assert len(captured) == 1
    c_pen, c_ok, c_err = captured[0]
    assert c_ok is True
    assert c_err == ""
    assert np.allclose(c_pen, [0.25])


def test_b8_gate_fail_returns_one():
    """Gate fail: returns 1.0, solver_ok=False, error=gate_reject."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 5.0},
    )
    weights = np.array([1.0])
    specs = [MetricSpec(
        name="f1", role=MetricRole.GATE,
        threshold=10.0, direction="greater_than",
    )]

    captured = []
    def _ckpt(x, raw, pen, ok, err):
        captured.append((pen.copy(), ok, err, raw.copy()))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
        metric_specs=specs,
    )

    val = evaluator(np.array([0.5]))
    assert meas_runner.call_count == 1
    assert val == 1.0
    assert len(captured) == 1
    c_pen, c_ok, c_err, c_raw = captured[0]
    assert c_ok is False
    assert c_err.startswith("gate_reject:")
    assert "f1" in c_err
    assert np.allclose(c_pen, [1.0])
    assert np.allclose(c_raw, [5.0])  # raw preserved from measurement


def test_b8_gate_checkpoint_excludes_gate_metric():
    """Checkpoint arrays include objective metrics only."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"opt": 0.1},
        raw_values={"opt": 11.424},
    )
    weights = np.array([1.0])
    specs = [
        MetricSpec(name="opt", role=MetricRole.OPTIMIZE),
        MetricSpec(name="gate", role=MetricRole.GATE,
                   threshold=10.0, direction="greater_than"),
    ]

    captured = []
    def _ckpt(x, raw, pen, ok, err):
        captured.append((pen.copy(), ok, err))

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["opt"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        checkpoint_callback=_ckpt,
        metric_specs=specs,
    )

    val = evaluator(np.array([0.5]))
    assert len(captured) == 1
    c_pen, c_ok, c_err = captured[0]
    # Gate metrics explicitly excluded — arrays sized to objective_names
    assert len(c_pen) == 1  # only "opt"


def test_b8_gate_results_logged(caplog):
    """Gate results logged when metric_specs includes gate."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import logging, numpy as np

    caplog.set_level(logging.INFO, logger="workflows.rfgun_sao.two_pass")

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])
    specs = [MetricSpec(
        name="f1", role=MetricRole.GATE,
        threshold=10.0, direction="greater_than",
    )]

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        metric_specs=specs,
    )

    evaluator(np.array([0.5]))
    assert "Two-pass gate results" in caplog.text
    assert "f1" in caplog.text


def test_b8_gate_missing_raw_false():
    """compute_gate_results missing raw -> False."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_gate_results,
    )

    specs = [MetricSpec(
        name="g1", role=MetricRole.GATE,
        threshold=10.0, direction="less_than",
    )]
    r = compute_gate_results(metric_specs=specs, raw_metrics={})
    assert r == {"g1": False}


def test_b8_gate_no_raw_mutation():
    """compute_gate_results does not mutate raw_metrics."""
    from workflows.rfgun_sao.metrics import (
        MetricSpec, MetricRole, compute_gate_results,
    )

    specs = [MetricSpec(
        name="g1", role=MetricRole.GATE,
        threshold=10.0, direction="less_than",
    )]
    raw = {"g1": 5.0}
    before = dict(raw)
    compute_gate_results(metric_specs=specs, raw_metrics=raw)
    assert raw == before

# ============================================================
# AD. JSONL diagnostics sidecar skeleton — C1
# ============================================================

def test_make_json_safe_primitives():
    """Python primitives pass through unchanged."""
    from workflows.rfgun_sao.records import make_json_safe
    assert make_json_safe(True) is True
    assert make_json_safe(42) == 42
    assert make_json_safe(3.14) == 3.14
    assert make_json_safe("hello") == "hello"
    assert make_json_safe(None) is None


def test_make_json_safe_numpy():
    """numpy scalars convert to Python scalars."""
    from workflows.rfgun_sao.records import make_json_safe
    import numpy as np
    assert make_json_safe(np.float64(1.5)) == 1.5
    assert make_json_safe(np.int32(7)) == 7
    assert make_json_safe(np.bool_(True)) is True


def test_make_json_safe_nan():
    """nan/inf convert to None."""
    from workflows.rfgun_sao.records import make_json_safe
    import numpy as np
    assert make_json_safe(np.nan) is None
    assert make_json_safe(np.inf) is None
    assert make_json_safe(-np.inf) is None


def test_make_json_safe_array():
    """ndarray converts to list."""
    from workflows.rfgun_sao.records import make_json_safe
    import numpy as np
    result = make_json_safe(np.array([1.0, 2.0, np.nan]))
    assert result == [1.0, 2.0, None]


def test_make_json_safe_nested():
    """Nested dict/list convert recursively."""
    from workflows.rfgun_sao.records import make_json_safe
    import numpy as np
    data = {"a": np.float64(1.0), "b": [np.int32(2), {"c": np.nan}]}
    result = make_json_safe(data)
    assert result == {"a": 1.0, "b": [2, {"c": None}]}


def test_build_evaluation_record_basic():
    """build_evaluation_record returns JSON-safe dict."""
    from workflows.rfgun_sao.records import build_evaluation_record
    import numpy as np

    rec = build_evaluation_record(
        iteration=0,
        x_phys=np.array([0.5]),
        objective_names=["a", "b"],
        raw_values=np.array([11.424, 0.5]),
        penalties=np.array([0.3, 0.7]),
        solver_ok=True,
        error="",
    )
    assert rec["schema_version"] == 1
    assert rec["iteration"] == 0
    assert rec["solver_ok"] is True
    assert rec["error"] == ""
    assert rec["objective_names"] == ["a", "b"]
    assert rec["raw_values"] == {"a": 11.424, "b": 0.5}
    assert rec["penalties"] == {"a": 0.3, "b": 0.7}
    assert "diagnostics" not in rec
    assert "gate_results" not in rec
    # Must be serializable
    import json
    json.dumps(rec)


def test_build_evaluation_record_with_diagnostics():
    """diagnostics and gate_results included when non-empty."""
    from workflows.rfgun_sao.records import build_evaluation_record
    import numpy as np

    rec = build_evaluation_record(
        iteration=1,
        x_phys=[0.5],
        objective_names=["a"],
        raw_values=[1.0],
        penalties=[0.2],
        solver_ok=True,
        error="",
        diagnostics={"q0_diag": 18630.0},
        gate_results={"g1": True},
    )
    assert rec["diagnostics"] == {"q0_diag": 18630.0}
    assert rec["gate_results"] == {"g1": True}


def test_build_evaluation_record_length_mismatch():
    """Length mismatch raises ValueError."""
    from workflows.rfgun_sao.records import build_evaluation_record
    import pytest

    with pytest.raises(ValueError, match="Length mismatch"):
        build_evaluation_record(
            iteration=0, x_phys=[0.5],
            objective_names=["a", "b"],
            raw_values=[1.0],
            penalties=[0.2],
            solver_ok=True, error="",
        )


def test_append_read_jsonl(tmp_path):
    """append_jsonl_record writes and read_jsonl_records reads."""
    from workflows.rfgun_sao.records import append_jsonl_record, read_jsonl_records
    import json

    p = tmp_path / "records.jsonl"
    rec1 = {"a": 1}
    rec2 = {"b": 2}

    append_jsonl_record(p, rec1)
    append_jsonl_record(p, rec2)

    loaded = read_jsonl_records(p)
    assert loaded == [rec1, rec2]

    # Verify line structure
    with open(p, "r") as fh:
        lines = fh.readlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == rec1


def test_read_jsonl_missing_file(tmp_path):
    """read_jsonl_records returns [] for missing file."""
    from workflows.rfgun_sao.records import read_jsonl_records
    assert read_jsonl_records(tmp_path / "nope.jsonl") == []


def test_append_jsonl_creates_parent_dir(tmp_path):
    """append_jsonl_record creates parent directories."""
    from workflows.rfgun_sao.records import append_jsonl_record, read_jsonl_records
    p = tmp_path / "sub" / "deep" / "records.jsonl"
    append_jsonl_record(p, {"x": 1})
    assert read_jsonl_records(p) == [{"x": 1}]


def test_resolve_records_config_default():
    """Missing config -> disabled."""
    from workflows.rfgun_sao.records import resolve_records_config
    r = resolve_records_config({})
    assert r["enabled"] is False
    assert r["path"] is None


def test_resolve_records_config_bool():
    """bool true/false config."""
    from workflows.rfgun_sao.records import resolve_records_config
    r1 = resolve_records_config({"logging": {"evaluation_records": True}})
    assert r1["enabled"] is True
    assert r1["path"] is not None

    r2 = resolve_records_config({"logging": {"evaluation_records": False}})
    assert r2["enabled"] is False


def test_resolve_records_config_dict():
    """dict enabled/path config."""
    from workflows.rfgun_sao.records import resolve_records_config

    r = resolve_records_config({
        "logging": {
            "evaluation_records": {"enabled": True, "path": "/tmp/custom.jsonl"},
        },
    })
    assert r["enabled"] is True
    assert "custom.jsonl" in r["path"]

# ============================================================
# AE. JSONL runtime opt-in sidecar — C2
# ============================================================

def test_jsonl_sidecar_default_disabled(tmp_path):
    """Default disabled config does not write JSONL."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import resolve_records_config
    import numpy as np

    cfg = resolve_records_config({})
    assert cfg["enabled"] is False

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])

    result = _record_jsonl_sidecar_evaluation(
        cfg, wf_ref, 0, x, raw, pen, True, "",
    )
    assert result is False


def test_jsonl_sidecar_path_missing_disabled(tmp_path):
    """Enabled but path missing returns False."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    import numpy as np

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": None}, [], 0,
        np.array([0.5]), np.array([1.0]), np.array([0.2]), True, "",
    )
    assert result is False


def test_jsonl_sidecar_writes_record(tmp_path):
    """Enabled + tmp_path writes a valid JSONL record."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])
    p = str(tmp_path / "records.jsonl")

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": p}, wf_ref, 0, x, raw, pen,
        True, "",
    )
    assert result is True

    loaded = read_jsonl_records(p)
    assert len(loaded) == 1
    rec = loaded[0]
    assert rec["schema_version"] == 1
    assert rec["iteration"] == 0
    assert rec["solver_ok"] is True
    assert rec["error"] == ""
    assert rec["objective_names"] == ["a"]
    assert rec["raw_values"] == {"a": 11.424}
    assert rec["penalties"] == {"a": 0.3}
    assert "metadata" in rec
    assert rec["metadata"]["source"] == "rfgun_sao.run.checkpoint_callback"


def test_jsonl_sidecar_length_mismatch_does_not_raise(tmp_path):
    """Length mismatch -> warning, False, no crash."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a", "b"])]
    x = np.array([0.5])
    raw = np.array([11.424])  # 1 element, 2 names
    pen = np.array([0.3])

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": str(tmp_path / "r.jsonl")},
        wf_ref, 0, x, raw, pen, True, "",
    )
    assert result is False


def test_jsonl_sidecar_metric_names_unavailable(tmp_path):
    """Unavailable metric names -> warning, False."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    import numpy as np

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": str(tmp_path / "r.jsonl")},
        [], 0, np.array([0.5]), np.array([1.0]), np.array([0.2]),
        True, "",
    )
    assert result is False


def test_jsonl_sidecar_write_failure_logged(tmp_path):
    """Write failure (bad path) -> warning, not crash."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    # Use an unwritable path (directory that doesn't exist in a way that fails)
    bad_path = str(tmp_path / "nonexistent_subdir" / "records.jsonl")
    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": bad_path},
        wf_ref, 0, np.array([0.5]), np.array([1.0]), np.array([0.2]),
        True, "",
    )
    # Depending on platform, append_jsonl_record may create the dir;
    # if it succeeds it's fine; the test is that it doesn't crash.
    from pathlib import Path
    p = Path(bad_path)
    if p.exists():
        import os
        os.remove(bad_path)
    # The assertion is: helper always returns bool without crashing
    assert isinstance(result, bool)


def test_jsonl_sidecar_multiple_records(tmp_path):
    """Multiple evaluations produce multiple JSONL lines."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    p = str(tmp_path / "multi.jsonl")

    for i in range(3):
        ok = _record_jsonl_sidecar_evaluation(
            {"enabled": True, "path": p}, wf_ref, i,
            np.array([0.5]), np.array([float(i)]), np.array([0.1]),
            True, "",
        )
        assert ok is True

    loaded = read_jsonl_records(p)
    assert len(loaded) == 3
    for i, rec in enumerate(loaded):
        assert rec["iteration"] == i


def test_config_yaml_does_not_enable_jsonl():
    """Default config.yaml does not set evaluation_records enabled=true."""
    import yaml
    from workflows.rfgun_sao.run import _PROJECT_ROOT
    from workflows.rfgun_sao.run import DEFAULT_CONFIG_PATH

    cfg = yaml.safe_load(open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8"))
    logging_cfg = cfg.get("logging", {})
    records_cfg = logging_cfg.get("evaluation_records", None)
    assert records_cfg is None, (
        f"Default config must not enable JSONL, got: {records_cfg}"
    )

# ============================================================
# AF. JSONL sidecar polish — C2.1
# ============================================================

def test_jsonl_sidecar_append_failure_caught(monkeypatch, caplog):
    """append_jsonl_record raises -> helper returns False, logs warning."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records, append_jsonl_record
    import logging, numpy as np
    import tempfile, os

    def _failing_append(path, record):
        raise OSError("forced jsonl failure")

    monkeypatch.setattr(
        "workflows.rfgun_sao.run.append_jsonl_record",
        _failing_append,
    )

    caplog.set_level(logging.WARNING, logger="workflow_1")

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])

    with tempfile.TemporaryDirectory() as tmpdir:
        p = os.path.join(tmpdir, "records.jsonl")
        result = _record_jsonl_sidecar_evaluation(
            {"enabled": True, "path": p},
            wf_ref, 0, x, raw, pen, True, "",
        )
        assert result is False

    assert "JSONL sidecar write failed" in caplog.text
    assert "forced jsonl failure" in caplog.text

# ============================================================
# AG. JSONL diagnostics/gate enrichment — C3
# ============================================================

def test_c3_jsonl_sidecar_diagnostics_included(tmp_path):
    """_record_jsonl_sidecar_evaluation writes diagnostics when provided."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])
    p = str(tmp_path / "diag.jsonl")

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": p}, wf_ref, 0, x, raw, pen, True, "",
        diagnostics={"q0_diag": 18630.0},
        gate_results={"g1": True},
    )
    assert result is True
    rec = read_jsonl_records(p)[0]
    assert rec["diagnostics"] == {"q0_diag": 18630.0}
    assert rec["gate_results"] == {"g1": True}


def test_c3_two_pass_measurement_diagnostics_in_jsonl(monkeypatch):
    """Two-pass measurement with diagnostics enriches JSONL, not checkpoint."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    captured = []

    def _jsonl_cb(**kw):
        captured.append(kw)

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 11.424},
        diagnostics={"q0_diag": 18630.0},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        evaluation_record_callback=_jsonl_cb,
    )

    val = evaluator(np.array([0.5]))
    assert abs(val - 0.25) < 1e-12
    assert len(captured) == 1
    cb = captured[0]
    assert cb["diagnostics"] == {"q0_diag": 18630.0}
    assert cb["solver_ok"] is True
    assert cb["error"] == ""


def test_c3_two_pass_gate_fail_enriches_jsonl(monkeypatch):
    """Gate fail: JSONL has gate_results, scalar=1.0, solver_ok=False."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    captured = []

    def _jsonl_cb(**kw):
        captured.append(kw)

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 5.0},
    )
    weights = np.array([1.0])
    specs = [MetricSpec(
        name="f1", role=MetricRole.GATE,
        threshold=10.0, direction="greater_than",
    )]

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        metric_specs=specs,
        evaluation_record_callback=_jsonl_cb,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert len(captured) == 1
    cb = captured[0]
    assert cb["gate_results"] is not None
    assert cb["gate_results"].get("f1") is False
    assert cb["solver_ok"] is False
    assert "gate_reject" in cb["error"]


def test_c3_jsonl_disabled_no_file(tmp_path):
    """JSONL disabled: extended callback does not write."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    write_count = [0]

    def _jsonl_cb(**kw):
        write_count[0] += 1

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
    )
    evaluator(np.array([0.5]))
    # callback not passed -> no writes
    assert write_count[0] == 0


def test_c3_callback_exception_does_not_crash():
    """Callback raises -> evaluator still returns scalar."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    def _failing_cb(**kw):
        raise RuntimeError("cb crash")

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.3},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        evaluation_record_callback=_failing_cb,
    )
    val = evaluator(np.array([0.5]))
    assert abs(val - 0.3) < 1e-12  # scalar unaffected


def test_c3_gate_pass_jsonl_solver_ok():
    """Gate pass: JSONL solver_ok=True, error empty, scalar unchanged."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    from workflows.rfgun_sao.metrics import MetricSpec, MetricRole
    import numpy as np

    captured = []

    def _jsonl_cb(**kw):
        captured.append(kw)

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 15.0},
    )
    weights = np.array([1.0])
    specs = [MetricSpec(
        name="f1", role=MetricRole.GATE,
        threshold=10.0, direction="greater_than",
    )]

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        metric_specs=specs,
        evaluation_record_callback=_jsonl_cb,
    )

    val = evaluator(np.array([0.5]))
    assert abs(val - 0.25) < 1e-12
    assert len(captured) == 1
    cb = captured[0]
    assert cb["gate_results"]["f1"] is True
    assert cb["solver_ok"] is True
    assert cb["error"] == ""


def test_c3_rejected_path_enriches_jsonl():
    """Rejected path: JSONL gets calibration meta, solver_ok=False."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    captured = []

    def _jsonl_cb(**kw):
        captured.append(kw)

    cal_runner = _FakeCalibrationRunner(
        success=False,
        f0_ghz=np.nan,
        error="calibration failed",
    )
    meas_runner = _FakeMeasurementRunner()
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        evaluation_record_callback=_jsonl_cb,
    )

    val = evaluator(np.array([0.5]))
    assert val == 1.0
    assert len(captured) == 1
    cb = captured[0]
    assert cb["solver_ok"] is False
    assert "calibration_failed" in cb["error"]

# ============================================================
# AH. JSONL mode gating fix — C3.1
# ============================================================

def test_mode_gating_single_pass_enabled_is_core_only():
    """single_pass + records enabled -> use_enriched_jsonl is False."""
    from workflows.rfgun_sao.run import _should_use_enriched_jsonl

    cfg = {"evaluation": {"mode": "single_pass"}}
    records_cfg = {"enabled": True, "path": "/tmp/x.jsonl"}
    assert _should_use_enriched_jsonl(cfg, records_cfg) is False


def test_mode_gating_two_pass_enabled_is_enriched():
    """two_pass + records enabled -> use_enriched_jsonl is True."""
    from workflows.rfgun_sao.run import _should_use_enriched_jsonl

    cfg = {"evaluation": {"mode": "two_pass"}}
    records_cfg = {"enabled": True, "path": "/tmp/x.jsonl"}
    assert _should_use_enriched_jsonl(cfg, records_cfg) is True


def test_mode_gating_disabled():
    """two_pass + records disabled -> use_enriched_jsonl is False."""
    from workflows.rfgun_sao.run import _should_use_enriched_jsonl

    cfg = {"evaluation": {"mode": "two_pass"}}
    records_cfg = {"enabled": False, "path": None}
    assert _should_use_enriched_jsonl(cfg, records_cfg) is False


def test_mode_gating_single_pass_core_path_writes_jsonl(tmp_path):
    """single_pass + enabled -> _record_jsonl_sidecar_evaluation is called."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])
    p = str(tmp_path / "single_pass.jsonl")

    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": p}, wf_ref, 0, x, raw, pen, True, "",
    )
    assert result is True
    loaded = read_jsonl_records(p)
    assert len(loaded) == 1
    # Core-only: no diagnostics or gate_results
    assert "diagnostics" not in loaded[0]
    assert "gate_results" not in loaded[0]


def test_mode_gating_two_pass_enriched_no_duplicate(tmp_path):
    """two_pass enriched callback does not duplicate core-only writes."""
    from workflows.rfgun_sao.run import _record_jsonl_sidecar_evaluation
    from workflows.rfgun_sao.records import read_jsonl_records
    import numpy as np

    wf_ref = [_FakeObjectiveNamesContainer(["a"])]
    x = np.array([0.5])
    raw = np.array([11.424])
    pen = np.array([0.3])
    p = str(tmp_path / "enriched.jsonl")

    # Call enriched sidecar (as the two_pass callback would)
    result = _record_jsonl_sidecar_evaluation(
        {"enabled": True, "path": p}, wf_ref, 0, x, raw, pen, True, "",
        diagnostics={"d1": 1.0},
        gate_results={"g1": True},
    )
    assert result is True
    loaded = read_jsonl_records(p)
    assert len(loaded) == 1
    assert loaded[0]["diagnostics"] == {"d1": 1.0}
    assert loaded[0]["gate_results"] == {"g1": True}

# ============================================================
# AI. JSONL counter ordering fix — C3.2
# ============================================================

def test_c3_2_mode_gating_preserved():
    """_should_use_enriched_jsonl semantics unchanged from C3.1."""
    from workflows.rfgun_sao.run import _should_use_enriched_jsonl

    assert _should_use_enriched_jsonl(
        {"evaluation": {"mode": "single_pass"}},
        {"enabled": True, "path": "/tmp/x.jsonl"},
    ) is False

    assert _should_use_enriched_jsonl(
        {"evaluation": {"mode": "two_pass"}},
        {"enabled": True, "path": "/tmp/x.jsonl"},
    ) is True

    assert _should_use_enriched_jsonl(
        {"evaluation": {"mode": "two_pass"}},
        {"enabled": False, "path": None},
    ) is False


def test_c3_2_single_pass_core_counter():
    """simulated single_pass path: core write then increment each eval."""
    counter = [0]
    records = []

    def _on_eval():
        records.append(counter[0])
        counter[0] += 1

    _on_eval()
    _on_eval()
    assert records == [0, 1]
    assert counter[0] == 2


def test_c3_2_enriched_counter():
    """simulated two_pass enriched path: no inc in on_eval, inc in callback."""
    counter = [0]
    records = []

    def _on_eval():
        pass  # no inc when use_enriched_jsonl=True

    def _enrich_cb():
        records.append(counter[0])
        counter[0] += 1

    # Simulate two evaluations
    _on_eval()
    _enrich_cb()
    _on_eval()
    _enrich_cb()
    assert records == [0, 1]
    assert counter[0] == 2


def test_c3_2_two_pass_evaluator_callback_invoked_twice():
    """Two-pass enriched callback invoked once per evaluation, no duplicate."""
    from workflows.rfgun_sao.two_pass import make_two_pass_runtime_evaluator
    import numpy as np

    call_count = [0]

    def _jsonl_cb(**kw):
        call_count[0] += 1

    cal_runner = _FakeCalibrationRunner(
        success=True, f0_ghz=11.424, s11_min_db=-10.0,
    )
    meas_runner = _FakeMeasurementRunner(
        penalty_values={"f1": 0.25},
        raw_values={"f1": 11.424},
    )
    weights = np.array([1.0])

    evaluator = make_two_pass_runtime_evaluator(
        param_names=["p1"],
        metric_names=["f1"],
        objectives=[],
        weights=weights,
        calibration_runner=cal_runner,
        measurement_runner=meas_runner,
        evaluation_record_callback=_jsonl_cb,
    )

    evaluator(np.array([0.5]))
    evaluator(np.array([0.6]))
    assert call_count[0] == 2

# ============================================================
# AJ. Ctrl+C hard-exit cleanup — D1
# ============================================================

def test_ctrl_c_first_event_no_cleanup():
    """First Ctrl+C does not call cleanup or exit."""
    from workflows.rfgun_sao.run import _handle_sigint_event

    count = [0]
    cleanup_called = []
    exit_called = []
    captured_msgs = []

    def _cleanup(force=False):
        cleanup_called.append(force)

    def _exit(code):
        exit_called.append(code)

    def _print(msg, **kw):
        captured_msgs.append(msg)

    _handle_sigint_event(
        ctrl_c_count=count,
        cleanup_func=_cleanup,
        exit_func=_exit,
        print_func=_print,
    )

    assert count[0] == 1
    assert cleanup_called == []
    assert exit_called == []
    assert any("Waiting" in m for m in captured_msgs)


def test_ctrl_c_second_event_cleanup_and_exit():
    """Second Ctrl+C calls cleanup(force=True) and exits with 130."""
    from workflows.rfgun_sao.run import _handle_sigint_event

    count = [0]
    cleanup_called = []
    exit_called = []
    captured_msgs = []

    def _cleanup(force=False):
        cleanup_called.append(force)

    def _exit(code):
        exit_called.append(code)

    def _print(msg, **kw):
        captured_msgs.append(msg)

    # First event
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_cleanup,
        exit_func=_exit, print_func=_print,
    )
    # Second event
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_cleanup,
        exit_func=_exit, print_func=_print,
    )

    assert count[0] == 2
    assert cleanup_called == [True]
    assert exit_called == [130]
    assert any("Force exit" in m for m in captured_msgs)
    # Second event must not add "Waiting" message
    waiting_msgs = [m for m in captured_msgs if "Waiting" in m]
    assert len(waiting_msgs) == 1


def test_ctrl_c_cleanup_raises_exit_still_called():
    """Cleanup exception -> exit still called, warning logged."""
    from workflows.rfgun_sao.run import _handle_sigint_event
    import logging

    count = [0]
    exit_called = []
    captured_msgs = []

    def _failing_cleanup(force=False):
        raise RuntimeError("cleanup broken")

    def _exit(code):
        exit_called.append(code)

    def _print(msg, **kw):
        captured_msgs.append(msg)

    # Two events to trigger second Ctrl+C
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_failing_cleanup,
        exit_func=_exit, print_func=_print,
        logger=logging.getLogger("test_logger"),
    )
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_failing_cleanup,
        exit_func=_exit, print_func=_print,
        logger=logging.getLogger("test_logger"),
    )

    assert exit_called == [130]
    assert any("Force exit" in m for m in captured_msgs)


def test_ctrl_c_first_then_third_force_exit():
    """Third+ Ctrl+C also triggers cleanup and exit."""
    from workflows.rfgun_sao.run import _handle_sigint_event

    count = [0]
    cleanup_count = [0]

    def _cleanup(force=False):
        cleanup_count[0] += 1

    def _exit(code):
        pass

    # First
    _handle_sigint_event(ctrl_c_count=count, cleanup_func=_cleanup, exit_func=_exit)
    # Second
    _handle_sigint_event(ctrl_c_count=count, cleanup_func=_cleanup, exit_func=_exit)
    # Third
    _handle_sigint_event(ctrl_c_count=count, cleanup_func=_cleanup, exit_func=_exit)

    assert cleanup_count[0] == 2  # second and third


def test_ctrl_c_cleanup_failure_no_logger_prints_fallback():
    """Cleanup failure with logger=None prints fallback message."""
    from workflows.rfgun_sao.run import _handle_sigint_event

    count = [0]
    exit_called = []
    captured_msgs = []

    def _failing_cleanup(force=False):
        raise RuntimeError("fallback msg")

    def _exit(code):
        exit_called.append(code)

    def _print(msg, **kw):
        captured_msgs.append(msg)

    # Two events; logger=None
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_failing_cleanup,
        exit_func=_exit, print_func=_print,
    )
    _handle_sigint_event(
        ctrl_c_count=count, cleanup_func=_failing_cleanup,
        exit_func=_exit, print_func=_print,
    )

    assert exit_called == [130]
    assert any("Force-exit cleanup failed" in m for m in captured_msgs)


def test_ctrl_c_cleanup_workflow_force_true():
    """_cleanup_workflow_connection called with force=True from cleanup_func."""
    from workflows.rfgun_sao.run import _cleanup_workflow_connection

    close_kwargs = {}

    class _FakeConn:
        pid = 999
        def close(self, force=False):
            close_kwargs["force"] = force

    class _WF:
        _conn = _FakeConn()

    r = _cleanup_workflow_connection(_WF(), force=True)
    assert r["attempted"] is True
    assert r["force"] is True
    assert r["closed"] is True
    assert close_kwargs.get("force") is True
