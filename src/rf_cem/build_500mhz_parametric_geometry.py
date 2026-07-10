"""CLI for the 500 MHz RF-CEM parametric vacuum geometry MVP."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from rf_cem.parametric_geometry.core.types import PipelineInputs
from rf_cem.parametric_geometry.pipeline.reverse_pipeline import run_reverse_pipeline


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rf_cem.build_500mhz_parametric_geometry",
        description="Recover a single-cell parametric RF vacuum profile and generated STEP for the 500 MHz baseline.",
    )
    parser.add_argument("--appendix", type=Path, required=True, help="Path to Appendix/500MHz_baseline.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output design package directory.")
    parser.add_argument("--target-body-index", type=int, default=0, help="Manual target vacuum body index.")
    parser.add_argument("--axis", choices=("x", "y", "z"), default="z", help="Requested rotation axis.")
    parser.add_argument("--deflection-mm", type=float, default=0.25, help="CadQuery tessellation deflection for diagnostics.")
    parser.add_argument("--expert-prior", type=Path, default=None, help="Optional expert_prior.v0.yaml override.")
    args = parser.parse_args(argv)
    result = run_reverse_pipeline(
        PipelineInputs(
            appendix=args.appendix,
            output_dir=args.output_dir,
            target_body_index=args.target_body_index,
            axis=args.axis,
            deflection_mm=args.deflection_mm,
            expert_prior=args.expert_prior,
        )
    )
    print(f"Wrote parametric geometry package to {result['output_dir']}")
    if result["blocking_errors"]:
        print(f"Blocking errors: {result['blocking_errors']}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
