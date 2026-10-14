# WF7 — local Wakis HOM search

Canonical branch: `workflow/7-wakis-hom`. This package is workflow-specific;
the shared CST wrappers remain in `src/cst_optimization`.

Each complete candidate uses one axis wake and one +2 mm X-drive wake on
the same candidate-specific FIT mesh. Axis data also supplies the two solid1
surface heating estimates and port2/3 working-mode leakage. PW witness
derivatives stay on axis; source differencing produces only the X column
`[Zxx, Zyx]`. Y is unmeasured, never zero-filled.

## Search contract

Sixteen independent parameters: the previous fifteen plus `coaxr2`, mapped
to the template's actual `coax_r2` parameter. All lengths are mm; angles
are degrees. Both UpperHeight values remain 100 mm. `PortR2 = PortR1 + 2`;
`5.43 < coaxr2 < 22` and `coaxr2 >= PortR2`. The derived constraint also
requires `PortR1 < 20`. Samples are drawn inside the feasible domain,
without clipping invalid values onto boundaries.

Longitudinal reconstructed HOM peak <=1800 ohm; X transverse column norm
<=150000 ohm/m; each port2/3 leakage strictly <75 W. Minimize the larger
solid1 heat load and retain both component values. There is no 150 W stop.
Longitudinal excess has first priority. A finite longitudinal sensitivity
upper envelope <=3000 ohm admits X; about 20% of measured active time is
reserved for cross-gate exploration. Independent partial-observation GPs
use reconstructed estimates and heteroscedastic uncertainty, never direct
FT proxies. Earlier geometries are reference-only, not native training data.

Sigma=70 mm; wake length=35 m; HOM band=550–1462.7348957 MHz. Working-mode
power uses 500 kV peak transit-time voltage, CW, beta=1 and copper
conductivity 5.8e7 S/m. Only `component5:solid1` and `component6:solid1`
count toward heating. Net physical Poynting flux at three coax planes is
reported as leakage, not as Qe from unmeasured stored energy. Power carries
at least 20% heuristic sensitivity; poor fit/window/plane consistency is
unresolved and cannot certify feasibility. No full transverse or out-of-band
suppression claim is made.

## Run and recovery

Use an explicit untracked `config.local.json`. The GPU environment must have
CuPy, Wakis dependencies, h5py, psutil, scipy and scikit-learn. Pin the Wakis
checkout to `e0d8f2f1e0e2b58e0f675ded71b32917a18dadfe`; tracked upstream
modifications are refused. Use the repository `.venv` for no-CST tests.

```powershell
python -m workflows.rfgun_wakis.campaign init --config config.local.json --baseline baseline.json
python -m workflows.rfgun_wakis.campaign run --config config.local.json
python -m workflows.rfgun_wakis.campaign status --config config.local.json
```

An optional `import-baseline --import-spec native.json` registers the current
template's already completed axis/X preflight. It verifies geometry, expanded
parameters, current solver identity and all numeric manifests before doing so.
This path is idempotent and only available before dispatch. Its field and
analysis costs remain explicit in `native_baseline_import.json`, separate from
the subsequent round; the same native baseline is never solved or counted twice.

Launch the actual command with the configured interpreter and a hidden
window. Initialization pins the source, code and configuration. Source
templates are copied, never edited. CST only prepares geometry and dumps
FIT matrices: it explicitly sets WakeLength=35000 mm, archives resolved
port planes, deletes modal ports in the owned copy and aborts after export.
This preparation is not a completed CST wake solve. Tensor format/material
identities, exact witness nodes and preserved CST magnetic regularization
are checked before GPU evolution.

The coordinator holds a persistent OS lock. Every phase has a request,
reply and exact PID/birth/command process tree. Only proven descendants can
be stopped. Memory and phase timeouts retain failed evidence. Completed
field acquisitions go directly to postprocessing recovery; they do not
blindly consume another field solve. A numerical stability failure is not
repeated with the same inputs. Ownership or cleanup ambiguity stops dispatch.

The 48-hour round counts active coordinator wall time, including preparation,
GPU work, fitting and retries; paused idle time is excluded. At the cap or
on `STOP`, the current logical stage drains and no new stage dispatches.
Overrun is recorded. A subsequent round requires manual audit and start.
There is no automatic deletion of projects, raw traces or permanent evidence.

## Evidence and limitations

`state.json` is authoritative; `report.json` and `candidates.csv` are stage
snapshots. A false qualification flag does not mean the field solver failed.
Raw fields, signed wakes, rejected fits, local windows, uncertainty and
per-stage manifests remain available. A complete field certificate requires
all requested time steps; partial traces never become observations.

The candidate-specific CFL bound concerns the lossless FIT operator.
Surface loss and port absorbers also require live stability checks. Full
field stability and end-to-end live acceptance are separate from no-CST
test results. The RF screening model is approximate and its sensitivity
envelopes are not calibrated confidence intervals.

Upstream sources: Wakis pinned source; repository-verified CST wrappers and
installed CST 2026 documentation; the accepted local Wakis compact/copper/
port and shared-wake power experiments; WF6 measured-tail consensus and
partial-observation search. No old candidate's fitted poles or scalar FT
objectives are carried into a new candidate.
