"""Validate recorded solver evidence; fixed-tail termination is not an abort.

Counts are time steps, timestamps use the local CST log timezone. This module
does not import CST or decide whether the resulting impedance fit is reliable.
"""
from __future__ import annotations
import ast
from datetime import datetime
import re


def validate_completion(stage: str, solver: dict, log: str, messages: list,
                        started_ns: int) -> dict:
    """Require a fresh, successful solve and (for wakes) the full planned tail."""
    if solver.get('success') is not True:
        raise ValueError('Solver wrapper did not report success')
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise ValueError('Missing structured CST messages')
    if any(str(m.get('type', '')).upper() in ('ERROR', 'FATAL') for m in messages):
        raise ValueError('CST reported an error')
    text=log+'\n'+'\n'.join(str(m.get('text','')) for m in messages)
    if re.search(r'aborted|cancelled|canceled|solver failed',text,re.I):
        raise ValueError('Aborted or failed solver evidence')
    dates=re.findall(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)',log)
    if not dates or min(datetime.strptime(d,'%Y-%m-%d %H:%M:%S').timestamp() for d in dates)<started_ns/1e9-2:
        raise ValueError('Solver log is stale or has no timestamps')
    proof={'kind':stage,'warnings':[m for m in messages if str(m.get('type','')).upper()=='WARNING']}
    if stage=='thermal':
        # CST 2026 puts explicit success in structured messages, while Model.log
        # carries the dated result table and solver statistics (observed live).
        if not re.search(r'eigenmode solver successful',text,re.I) or not re.search(r'Eigenmode solver results:',log,re.I):
            raise ValueError('Missing explicit eigenmode success')
        return proof
    calculated=re.findall(r'Simulated number of time steps:\s*(\d+)',log,re.I)
    planned=re.findall(r'Maximum number of time steps:\s*(\d+)',log,re.I)
    if not calculated or not planned or int(calculated[-1])<=0 or len(set(planned))!=1 or int(calculated[-1])!=int(planned[-1]):
        raise ValueError('Fixed-tail time steps are missing or incomplete')
    if not re.search(r'Maximum number of pulse widths simulated, solver stopped\.',log,re.I) or not re.search(r'Time Domain:\s*WakefieldSolver finished at:',log,re.I):
        raise ValueError('Missing fixed-tail wake completion evidence')
    return dict(proof,calculated_steps=int(calculated[-1]),planned_steps=int(planned[-1]))


def legacy_messages(text: str) -> list:
    """Read old list repr files without executing their contents."""
    result=ast.literal_eval(text)
    if not isinstance(result,list):raise ValueError('Invalid archived messages')
    return result
