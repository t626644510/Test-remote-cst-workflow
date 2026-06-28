You are the local execution agent for a P01 follow-up.

Read first:
- `.agent/skills/multi-agent-git-dev/SKILL.md`
- `.agent/skills/multi-agent-git-dev/roles/local_executor.md`
- `.agent/stages/S01-known-main-mode-pso/stage_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/phase_plan.md`
- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/codex_drift_audit.md`
- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md`

Current phase:
- `P01-fixed-mode-core`

Required branch:
- `phase/S01-P01-fixed-mode-core`

Your task:
Fix the P01 core behavior so fixed known modes are never optimized by PSO.

Problem to fix:
The current implementation adds `KnownMode` wake to the fitted wake, but `fit_wake_with_pso()` still selects all visible peaks from the peak source and turns them into optimized `[A, Q]` variables. If the known fundamental mode is visible in the peak source, it appears both in `known_modes` and in `result.modes`.

Required behavior:
- Matching known-mode peaks must be filtered out before building the unknown-mode PSO parameter vector.
- Known modes must remain fixed contributions only.
- If all selected peaks are known modes, fitting must support zero unknown modes without calling the optimizer.
- Reconstructed impedance must still include fixed known modes when `include_in_reconstructed_impedance=True`.
- Existing no-known-mode behavior must remain unchanged.

Recommended implementation:
- Add an optional core-level frequency tolerance to `KnownMode`, for example `frequency_tolerance_hz: float = 0.0`.
- Treat a peak as known when `abs(peak.frequency_hz - known.frequency_hz) <= max(known.frequency_tolerance_hz, small_float_tolerance)`.
- Filter selected unknown peaks before constructing `fr_hz`, PSO bounds, and optimizer variables.
- Preserve or mark known/filtered peak provenance in diagnostics if it can be done simply, but do not expand the result model more than needed.
- When zero unknown peaks remain and at least one known mode exists:
  - do not call the optimizer,
  - set fitted unknown modes to an empty tuple,
  - compute `wake_fit` from known-mode wake only,
  - compute normalized error/correlation against the original target wake,
  - reconstruct impedance from included known modes only.

Allowed files:
- `workflows/rfgun_hom_antenna/pso_wake_fit.py`
- `tests/workflows/test_workflow2_pso_wake_fit.py`
- `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md`

Existing Codex-authored workflow files may already be modified or untracked in the working tree, including this follow-up prompt, `codex_drift_audit.md`, and the multi-agent skill rule updates. Do not edit those files, but you may include them unchanged in the commit/push so the remote reviewer can see the current workflow rules and follow-up instructions.

Forbidden files and behavior:
- Do not modify `wakefield_objective.py`.
- Do not parse `obj_params.pso_fit.known_modes`; that belongs to P02.
- Do not modify CST API code.
- Do not modify `src/cst_optimization/`.
- Do not implement Direction 2.
- Do not modify `stage_plan.md`.
- Do not push `main`, `stage/*`, tags, or unrelated branches.

Required tests to add or update:
- A test where the peak source contains only a known-mode peak:
  - provide that mode through `known_modes`,
  - use an optimizer that raises if called,
  - assert `result.modes == ()`,
  - assert the known mode explains the target wake.
- A test where the peak source contains both the known fundamental peak and an unknown HOM peak:
  - provide the fundamental through `known_modes`,
  - verify only the HOM remains in `result.modes` / selected unknown peaks,
  - verify the known fundamental does not appear as a fitted mode.
- Keep the existing 18 tests passing.

Required validation command:
```powershell
py -m pytest tests\workflows\test_workflow2_pso_wake_fit.py
```

Required workflow:
1. Verify current branch is `phase/S01-P01-fixed-mode-core`; stop with a blocker report if not.
2. Implement the smallest scoped fix.
3. Add/update tests.
4. Run the required validation command.
5. Update `.agent/stages/S01-known-main-mode-pso/P01-fixed-mode-core/execution_report.md` with a follow-up section including:
   - files changed,
   - tests run,
   - test results,
   - commit hash after commit,
   - push result.
6. Commit the allowed phase changes, including the updated execution report.
7. Push only the current branch:
   ```powershell
   git push -u origin phase/S01-P01-fixed-mode-core
   ```
8. If commit or push fails, stop and write a blocker report in the P01 phase folder.

Completion condition:
The branch must be visible remotely so Web Phase Reviewer can inspect the actual diff instead of relying on a local packet.
