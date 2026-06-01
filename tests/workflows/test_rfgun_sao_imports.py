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
    assert "make_two_pass_runtime_evaluator" in src
    assert "placeholder" in src
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

def test_rfgun_sao_readme_status_current_after_a25():
    """README captures current milestone test count and checkpoint phases."""
    import pathlib
    readme_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "workflows" / "rfgun_sao" / "README.md"
    )
    text = readme_path.read_text("utf-8")
    assert "107/107" in text
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
