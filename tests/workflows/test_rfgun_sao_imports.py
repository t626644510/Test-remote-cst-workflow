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
    ):
        self._success = success
        self._f0_ghz = f0_ghz
        self._s11_min_db = s11_min_db
        self._error = error
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
        )


class _FakeMeasurementRunner:
    """Fake measurement runner with configurable results."""
    def __init__(
        self,
        penalty_values: dict | None = None,
        raw_values: dict | None = None,
        status=None,
    ):
        from workflows.rfgun_sao.types import EvaluationStatus
        self._penalty_values = penalty_values or {"resonant_freq": 0.0}
        self._raw_values = raw_values or {"resonant_freq": 11.424}
        self._status = status or EvaluationStatus.SUCCESS
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
            error="",
            f0_ghz=11.424,
            raw_metrics=self._raw_values,
            objective_values=self._raw_values,
            penalty_values=self._penalty_values,
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
# D. Local workflow module imports without factory
# ============================================================

def test_local_workflow_module_imports_without_factory():
    sys.modules.pop("cst_optimization.factory", None)
    sys.modules.pop("workflows.rfgun_sao.workflow", None)

    import workflows.rfgun_sao.workflow as wf_mod

    assert "cst_optimization.factory" not in sys.modules
    assert hasattr(wf_mod, "build_workflow_1")

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
# F. Workflow source has no factory import
# ============================================================

def test_workflow_static_source_has_no_factory_import():
    src = (WF1_PACKAGE / "workflow.py").read_text("utf-8")
    assert "from cst_optimization.factory" not in src
    assert "import cst_optimization.factory" not in src

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

def test_workflow_build_sao_reads_n_initial_samples_key():
    src = (WF1_PACKAGE / 'workflow.py').read_text('utf-8')
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

def test_default_weights_equal():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
    w = _resolve_named_weights(None, ["a", "b", "c"])
    assert list(w) == [1/3, 1/3, 1/3]

def test_named_weights_by_objective_order():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
    w = _resolve_named_weights({"b": 5.0, "a": 3.0}, ["a", "b"])
    assert list(w) == [3/8, 5/8]

def test_weight_0_is_allowed():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
    w = _resolve_named_weights({'a': 0.0, 'b': 2.0}, ['a', 'b'])
    assert w[0] == 0.0 and w[1] == 1.0

def test_all_zero_weights_raise_error():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
    import pytest
    with pytest.raises(ValueError):
        _resolve_named_weights({'a': 0.0, 'b': 0.0}, ['a', 'b'])

def test_inf_weights_raise_error():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
    import pytest
    with pytest.raises(ValueError):
        _resolve_named_weights({'a': float('inf')}, ['a'])

def test_invalid_weights_raise_error():
    from workflows.rfgun_sao.workflow import _resolve_named_weights
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
    assert "placeholder_eval" in src
def test_workflow_source_has_objective_weights():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent.parent / "workflows" / "rfgun_sao" / "workflow.py").read_text("utf-8")
    assert "objective_weights" in src
def test_no_legacy_recovery_import():
    for py_file in WF1_PACKAGE.glob('*.py'):
        src2 = py_file.read_text('utf-8')
        assert 'cst_optimization.workflows.recovery' not in src2, \
            f'{py_file.name} imports from legacy recovery'
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
