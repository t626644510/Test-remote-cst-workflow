# Phase A24 — Live CST checkpoint evidence smoke

## Task

Run a live CST smoke with the A20–A22 hardened checkpoint semantics to
verify that a successful two-pass measurement produces a correct
``completed`` record in the ``CheckpointManager``-persisted ``.ckpt`` file.
No production code was changed — only a local temporary evidence script
was used to inspect the records before the production ``ckpt.clear()`` call.

## Live CST configuration

| Key | Value |
|-----|-------|
| ``evaluation.mode`` | ``two_pass`` |
| ``evaluation.two_pass.runtime`` | ``cst`` |
| ``optimization.n_initial_samples`` | ``1`` |
| ``optimization.n_iterations`` | ``0`` |
| ``retry.enabled`` | ``false`` |
| Config file | ``workflows/rfgun_sao/config.local.yaml`` (local, not committed) |
| CST project | ``D:/workflow_elgun/PickupDesign_2026.cst`` (local, not committed) |

## Live result

| Property | Value |
|----------|-------|
| Calibration succeeded | **yes** |
| Measurement reached | **yes** |
| Best F | -15185.95 |
| Best F finite non-placeholder | **yes** |
| Exit code | 0 |

## Checkpoint evidence

The checkpoint was inspected via a temporary (non-committed) script that
wraps the same ``_record_checkpoint_evaluation`` helper used by the
production ``run.py``, but preserves access to ``ckpt.records`` after
``optimize()`` returns, before any ``ckpt.clear()`` call.

### Inspected record

| Field | Value |
|-------|-------|
| ``status`` | ``completed`` |
| ``solver_ok`` | ``True`` |
| ``error`` | ``''`` (empty) |
| ``raw_values`` | All 7 objectives present and finite (resonant_freq=11.42454, coupling_beta=2.08, peak_e_field=87673, q0=18631, max_modified_poynting=4.096e12, field_flatness=0.0679, pulsed_heating=24.82) |
| ``penalties`` | All 7 objectives present |
| Metric invariant errors | **none** |
| ``x`` | 13-element parameter vector |
| ``timestamp`` | ISO-8601 UTC |
| Checkpoint file on disk before clear | **yes** |

### Metrics confirmed

The checkpoint ⸺ and therefore the `CheckpointManager` / `.ckpt` path ⸺
correctly records the full set of 7 objectives after a successful
two-pass evaluation:
1. ``resonant_freq``
2. ``coupling_beta``
3. ``peak_e_field``
4. ``q0``
5. ``max_modified_poynting``
6. ``field_flatness``
7. ``pulsed_heating``

No ``_checkpoint_metric_names_from_wf_ref`` or length-mismatch errors.

## `evaluation_records.jsonl` policy

| Question | Answer |
|----------|--------|
| JSONL written? | **no** |
| ``.ckpt`` authoritative? | **yes** |
| ``workflow.record_path`` used? | **no** (set but unused) |

## Files changed

| File | Action |
|------|--------|
| ``reports/restructure_plan/phase_A24_live_cst_checkpoint_evidence.md`` | Created (this file) |

No production code was modified.

## Production code changed

**None.**

## Validation

**Live CST command** (via temporary evidence script, not committed):
```
python -m workflows.rfgun_sao.run ...  # equivalent path through build_workflow_1
```

**Pytest:** Not run. No production code, tests, or README were modified.

## Live CST shutdown

| Question | Answer |
|----------|--------|
| CST window closed at A24 report time? | **incorrectly claimed ``yes``** — see A24.1 correction. The CST Design Environment process (``cstd`` PID 38892) remained running after the evidence script exited. |
| CST window closed after A24.1 cleanup? | **yes** — ``taskkill /F /T`` terminated the DE process. A background ``cstd`` licensing service auto-restarts with no window; this is normal for CST installations. |
| Correction reference | ``reports/restructure_plan/phase_A24_1_cst_shutdown_correction.md`` |

**Note:** The original A24 report incorrectly stated that CST closed on script exit.
A24.1 corrected this by explicitly killing the lingering DE process and verifying
that no visible CST window remains.  The checkpoint evidence itself is unaffected.

## Protected areas

| Area | Status |
|------|--------|
| ``workflows/rfgun_single_pass/`` untouched | yes |
| ``run_workflow_1.py`` untouched | yes |
| ``src/cst_optimization/`` untouched | yes |
| ``workflows/rfgun_sao/config.yaml`` default not changed | yes |
| ``config.local.yaml`` committed | no |
| CST artifacts committed | no |

## Commit hashes

- Implementation/report commit: ``786b7b1`` — ``Phase A24 rfgun_sao live CST checkpoint evidence``
- Report/hash-fill commit: N/A (single commit)
- Final pushed HEAD: ``786b7b1`` (superseded by A24.1 correction commit after shutdown fix)

## Caveats / follow-up

- **Live checkpoint evidence is sufficient** for current milestone: A20–A22
  hardened semantics are confirmed correct on a successful two-pass path.
- **Future JSONL sidecar** remains optional future work, not blocked by A24.
- **Gate rejection checkpoint evidence** (frequency_gate_reject,
  s11_depth_gate_reject) has not been collected live — the A16 no-CST
  regression tests cover these semantics with ``CheckpointManager`` unit
  tests, so this is a low-risk gap.
- **Next phase suggestion**: README milestone update reflecting the
  completed A19–A24 checkpoint audit, hardening, and live evidence cycle.
