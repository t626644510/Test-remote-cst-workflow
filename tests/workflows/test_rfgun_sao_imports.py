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

def test_no_legacy_recovery_import():
    for py_file in WF1_PACKAGE.glob('*.py'):
        src2 = py_file.read_text('utf-8')
        assert 'cst_optimization.workflows.recovery' not in src2, \
            f'{py_file.name} imports from legacy recovery'
def test_evaluator_static_source_has_no_factory_import():
    src = (WF1_PACKAGE / "evaluator.py").read_text("utf-8")
    assert "from cst_optimization.factory" not in src
    assert "import cst_optimization.factory" not in src
