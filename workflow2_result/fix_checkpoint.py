"""Rebuild workflow_2.ckpt with correct phases_done from index.jsonl."""
import json, os, pickle, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from cst_optimization.checkpoint import EvalRecord, CheckpointManager

CKPT = os.path.join(os.path.dirname(__file__), 'workflow_2.ckpt')
INDEX = os.path.join(os.path.dirname(__file__), 'raw_curves', 'index.jsonl')

# ── Load index.jsonl ──────────────────────────────────────────────
index_entries = []
with open(INDEX, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            index_entries.append(json.loads(line))

# Collect the BEST phases_done per iter number (longest list wins)
best_phases: dict[int, list[str]] = defaultdict(list)
best_solver_ok: dict[int, bool] = {}
best_has_full: dict[int, bool] = {}
best_params: dict[int, dict] = {}

for e in index_entries:
    it = e.get('iter', -1)
    if it < 0:
        continue
    pd = e.get('phases_done') or []
    if len(pd) > len(best_phases[it]):
        best_phases[it] = list(pd)
    params = e.get('params', {})
    if params and len(params) >= 10:
        best_params[it] = params
    if e.get('solver_ok'):
        best_solver_ok[it] = True
    if e.get('has_f2f') and e.get('has_f2w') and e.get('has_f2wo'):
        best_has_full[it] = True

print(f'Index entries: {len(index_entries)}')
print(f'Iters with phases: {dict((k,v) for k,v in best_phases.items() if v)}')
print(f'Iters with full data: {dict(best_has_full)}')

# ── Load checkpoint ───────────────────────────────────────────────
with open(CKPT, 'rb') as f:
    data = pickle.load(f)
records = data['records']

# Build iter→record_index map from the checkpoint (dedup: last record wins)
# The checkpoint records are ordered by add_pending calls, not by iter.
# We use the params to match against index.jsonl.
PARAM_NAMES = [
    'selfangle1','selfangle2','inner_angle','inner_angle3',
    'FolkHeight','FolkHeight2','UpperHeight1','UpperHeight2',
    'DownHeight1','DownHeight2','Lin2','inner_r2','Lin','inner_r',
]

def x_to_params(x):
    return dict(zip(PARAM_NAMES, [round(v, 4) for v in x]))

# For each checkpoint pending record, find the iter with matching params
fixed = 0
for i, r in enumerate(records):
    if not hasattr(r, 'x') or len(r.x) < 14:
        continue
    rp = x_to_params(r.x)
    # Find matching iter in index
    matched_iter = None
    for it, ip in best_params.items():
        if not ip:
            continue
        # Compare first 3 params as fingerprint
        match = True
        for k in list(ip.keys())[:4]:
            if k in rp and abs(rp[k] - ip.get(k, 999)) > 0.1:
                match = False
                break
        if match:
            matched_iter = it
            break

    if matched_iter is None:
        continue

    phases = best_phases.get(matched_iter, [])
    is_full = best_has_full.get(matched_iter, False)

    if is_full and r.status == 'pending':
        r.status = 'completed'
        r.solver_ok = best_solver_ok.get(matched_iter, True)
        r.error = ''
        r.tier_exhausted = False
        r.phases_done = phases
        fixed += 1
        print(f'[{i:3d}] iter={matched_iter:2d} pending→completed  phases={phases}')
    elif r.status == 'pending' and phases:
        r.phases_done = phases
        fixed += 1
        print(f'[{i:3d}] iter={matched_iter:2d} set phases_done={phases}')

# ── Save ──────────────────────────────────────────────────────────
bak = CKPT + '.bak2'
os.replace(CKPT, bak)
print(f'Backup: {bak}')
with open(CKPT, 'wb') as f:
    pickle.dump(data, f)
print(f'Fixed {fixed} records.  Saved.')
