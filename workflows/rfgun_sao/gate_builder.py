"""Gate builder helpers for Workflow 1 two-pass evaluation.

Extracted from ``rfgun_sao/workflow.py`` in Phase 11.
"""

from __future__ import annotations

from workflows.rfgun_sao.gates import FrequencyGate, S11DepthGate, MultiDipDetector


def _build_frequency_gate(eval_cfg: dict) -> FrequencyGate:
    cfg = eval_cfg.get("frequency_gate", {})
    return FrequencyGate(
        enabled=bool(cfg.get("enabled", False)),
        target_ghz=float(cfg.get("target_ghz", 11.424)),
        max_abs_offset_mhz=float(cfg.get("max_abs_offset_mhz", 20.0)),
    )


def _build_s11_depth_gate(eval_cfg: dict) -> S11DepthGate:
    cfg = eval_cfg.get("s11_depth_gate", {})
    return S11DepthGate(
        enabled=bool(cfg.get("enabled", False)),
        threshold_db=float(cfg.get("threshold_db", -1.0)),
    )


def _build_multi_dip_detector(eval_cfg: dict) -> MultiDipDetector:
    cfg = eval_cfg.get("multi_dip_detection", {})
    return MultiDipDetector(
        enabled=bool(cfg.get("enabled", False)),
        mode_spacing_ghz=float(cfg.get("mode_spacing_ghz", 0.04)),
    )


def resolve_two_pass_settings(config: dict) -> dict:
    """Resolve two-pass evaluation settings from workflow config."""
    eval_cfg = config.get("evaluation", {})
    return {
        "mode": str(eval_cfg.get("mode", "single_pass")).strip().lower(),
        "target_freq_ghz": float(eval_cfg.get("target_freq_ghz", 11.424)),
        "calibration_guess_ghz": float(eval_cfg.get("calibration_guess_ghz", 11.424)),
        "inter_pass_recovery": bool(eval_cfg.get("inter_pass_recovery", False)),
        "frequency_gate": _build_frequency_gate(eval_cfg),
        "s11_depth_gate": _build_s11_depth_gate(eval_cfg),
        "multi_dip_detector": _build_multi_dip_detector(eval_cfg),
    }
