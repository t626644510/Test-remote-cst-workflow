You are the local execution agent for P05-known-mode-calibration-stability.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/phase_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/known_mode_wake_tail_replay_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/feasibility_report.md`
- `.agent/stages/S01-known-main-mode-pso/P04-direction-2-feasibility-spike/phase_summary.md`
- `.agent/skills/multi-agent-git-dev/templates/execution_report.md`

Inspect only as needed:
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `workflows/rfgun_hom_antenna/wakefield_objective.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`

Required branch:
`phase/S01-P05-known-mode-calibration-stability`

Your task:
Run a report-only diagnostic analysis using existing long-wake CST data to determine whether the known fundamental mode needs a deterministic calibration layer before HOM PSO fitting.

Hard constraints:
- Fetch origin and fast-forward pull the assigned phase branch before reading local workflow files.
- Do not push to `main`.
- Do not push to `stage/*`, tags, or unrelated branches.
- Push only the current `phase/*` branch after report files are committed.
- Do not merge branches.
- Do not run new CST solves, smoke runs, geometry rebuilds, or live-CST simulations.
- Do not modify production code.
- Do not modify CST API, `src/cst_optimization/**`, `workflows/rfgun_hom_antenna/pso_wake_fit.py`, `workflows/rfgun_hom_antenna/wakefield_objective.py`, tests, scalarization semantics, or stage-level plans.
- Do not commit local plots, scratch scripts, CST files, or large generated outputs unless explicitly requested.

Allowed modified files:
- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/known_mode_calibration_stability_report.md`
- `.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/execution_report.md`

Allowed local-only scratch/output directory:
- `analysis_outputs/wf2_known_mode_calibration_stability/`

Existing data to use only if available locally:
- `D:\workflow2\Before_rebuild_backup\F2W.cst`
- `D:\workflow2\Before_rebuild_backup\F2W`

Use these longitudinal result paths from the existing data:
- `1D Results\Particle Beams\ParticleBeam1\Wake potential\Z`
- `1D Results\Particle Beams\ParticleBeam1\Wake impedance\Z`
- `1D Results\Particle Beams\ParticleBeam1\Charge distribution (distance)`

Minimum runs:
- Cover runs `1`, `5`, `10`, and `20` if available.
- If practical, summarize all available runs `1..20`.

Core interpretation rule:
Do not define the best result as a single reconstructed `|Z|` curve closest to CST sampled impedance. Use wake-domain residual and calibrated known-mode parameter stability as primary evidence. Use reconstructed `|Z|` as a secondary consistency / envelope diagnostic.

Required tests:

1. Deterministic known-mode calibration sweep
   - Baseline prior: `frequency_hz = 499.8e6`, `q = 36500`, `r_over_q_ohm = 208.6` and/or `104.3`.
   - Sweep frequency around the prior / observed sampled peak.
   - For each frequency, compute scalar projection scale and effective R/Q:
     `scale = dot(target_wake, known_wake) / dot(known_wake, known_wake)`.
   - Record best frequency, effective R/Q, residual RMS, normalized error, and wake correlation by run and fit start.

2. Q sensitivity scan
   - With frequency and effective R/Q fixed or re-projected, sweep Q over a bounded range.
   - Decide whether Q is identifiable or should remain a fixed prior.

3. Fit-start stability map
   - Use fit starts: `0`, `0.5`, `1`, `2`, `5`, `10`, `20`, `40 m` unless data quality requires adjustment.
   - Identify acceptable start intervals rather than one hidden best start.
   - Report whether a conservative fixed start such as `1 m` or `2 m` is defensible.

4. HOM PSO ensemble after known-mode calibration
   - For selected stable starts, run HOM PSO with multiple seeds/settings where supported.
   - Record wake residual metrics, fitted HOM mode spreads, and reconstructed impedance envelopes.
   - Treat single-run reconstructed `|Z|` as non-authoritative unless the ensemble is stable.

Write the main report to:
`.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/known_mode_calibration_stability_report.md`

The report must include:
- Data source and run IDs.
- Result tree paths and units.
- Reproduction or re-check of the R/Q convention finding (`208.6` vs `104.3`).
- Test 1 through Test 4 results.
- Tables or concise summaries of calibrated `frequency_hz`, effective `R/Q`, Q sensitivity, fit-start stability, and HOM PSO ensemble stability.
- Recommendation on whether a production known-mode calibration layer is needed.
- Recommended current long-wake defaults.
- Explicit statement that current implementation keeps known `frequency_hz`, `q`, and `r_over_q_ohm` fixed; `frequency_tolerance_hz` is only for peak filtering.
- Clear distinction between primary wake-domain gates and secondary reconstructed impedance review.
- Blockers or missing data, if any.

Write the execution report to:
`.agent/stages/S01-known-main-mode-pso/P05-known-mode-calibration-stability/execution_report.md`

If practical, run and record:

```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

If regression tests are not rerun because this phase is report-only, state that explicitly and explain why.

If existing CST data cannot be opened or required local dependencies are missing, stop and write the blocker in the execution report. Do not fabricate results.

After completion:
- Commit only the two allowed report files.
- Push only `phase/S01-P05-known-mode-calibration-stability`.
- Mark ready for review in the execution report.
