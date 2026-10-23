"""Transverse coverage scheduling without weakening final impedance acceptance.

Impedances are reconstructed ohm / ohm per metre; stage costs are seconds.
The 3000 ohm admission line is exploratory, not a new physical target.
"""
from __future__ import annotations
import numpy as np
from .screening import reconstruction_uncertainty, search_metrics, ranking_metrics


def transverse_admitted(config, candidate: dict) -> bool:
    """Admit X/Y on a finite, noncontradictory full-band longitudinal envelope."""
    u = reconstruction_uncertainty(candidate).get('longitudinal', {})
    return bool(u.get('full_band_coverage') and not u.get('unbounded', True)
                and not u.get('contradictory_evidence', False)
                and u.get('upper') is not None
                and u['upper'] <= config.search.transverse_admission_ohm)


def thermal_shortlist(campaign) -> set[str]:
    """Keep heat independent of the X/Y exploration ledger, on promising wakes."""
    config = campaign.config
    candidates = [c for c in campaign.state['candidates'] if not c['failed']
                  and all(k in search_metrics(config, c) for k in ('longitudinal', 'transverse'))]
    def order(c):
        m = ranking_metrics(config, c)
        # Saturate longitudinal reward at its FINAL target; uncertain upper
        # penalties are search scores, never physical confidence bounds.
        return (max(1., m['longitudinal']/config.physics.longitudinal_limit),
                m['transverse']/config.physics.transverse_limit)
    candidates.sort(key=order)
    return {c['id'] for c in candidates[:config.runtime.retain_pareto]}


def select_action(campaign) -> tuple[dict, str, str | None]:
    """Prioritize repairs, protected cross-gate coverage, then cost-aware actions.

    Only gated X/Y time consumes the near/global ledger. Projected admission
    limits oversubscription; real solve time, including overrun, is charged by
    Store.tick. No candidate failure or missing metric becomes a GP target.
    """
    cfg = campaign.config
    state = campaign.state
    excluded = getattr(campaign, 'excluded_candidate_ids', set())
    exposure = state['exploration_seconds']
    total = state['active_seconds']
    fraction = cfg.search.exploration_fraction
    group = 'near' if exposure['near'] <= exposure['global'] else 'global'

    def allowance(stage):
        cost = campaign.estimate(stage)
        return sum(exposure.values()) + cost <= fraction*(total + cost)

    for c in state['candidates']:
        if c['id'] in excluded or c['failed'] or c['complete'] or not c.get('repair_stage'):
            continue
        stage = campaign.next_stage(c)
        if stage is None:
            continue
        gated = campaign.gated(c, stage)
        if not gated or allowance(stage):
            return c, stage, group if gated else None

    # Explicit user-requested backlog precedes exploration/new geometries.
    # Persist IDs in state so resume preserves the order. Completed/failed or
    # no-longer-admitted geometries fall back to ordinary policy; no gate bypass.
    by_id = {c['id']: c for c in state['candidates']}
    for candidate_id in state.get('priority_transverse', []):
        c = by_id[candidate_id]
        stage = campaign.next_stage(c)
        if c['id'] not in excluded and not c['failed'] and stage in ('x', 'y') and transverse_admitted(cfg, c):
            return c, stage, None

    campaign.controller.fit()
    shortlist = thermal_shortlist(campaign)
    measured = [campaign.controller.encode(c['parameters']) for c in state['candidates']
                if 'transverse' in search_metrics(cfg, c)]
    regular, exploration = [], []
    for c in state['candidates']:
        if c['id'] in excluded or c['failed'] or c['complete']:
            continue
        stage = campaign.next_stage(c)
        if stage is None or (stage == 'thermal' and c['id'] not in shortlist):
            continue
        gated = campaign.gated(c, stage)
        if gated and not allowance(stage):
            continue
        stages = ('thermal',) if stage == 'thermal' else ('axis', 'x', 'y')
        cost = sum(campaign.estimate(s) for s in stages if s not in c['stages'])
        x = campaign.controller.encode(c['parameters'])[None, :]
        score = float(campaign.controller.score(x, cost, search_metrics(cfg, c),
                      reconstruction_uncertainty(c))[0])
        if gated and group == 'global':
            distance = min((float(np.linalg.norm(x[0]-p)) for p in measured), default=1.)
            score = (distance + 1e-6*campaign.controller.rng.random())/max(cost, 1.)
        # A small tie preference completes an already half-observed transverse
        # matrix. Its smaller remaining cost supplies the main preference.
        if stage == 'y':
            score *= 1.05
        (exploration if gated else regular).append((score, c, stage, group if gated else None))

    # Protected coverage competes outside GP merit: otherwise a GP can suppress
    # precisely the longitudinal-poor / transverse-unknown regions of interest.
    if exploration:
        _, c, stage, group = max(exploration, key=lambda item: item[0])
        state['rng'] = campaign.controller.rng.bit_generator.state
        return c, stage, group
    parameters, source = campaign.controller.propose()
    x = campaign.controller.encode(parameters)[None, :]
    newscore = float(campaign.controller.score(x, sum(campaign.estimate(s) for s in ('axis','x','y')))[0])
    if regular and max(regular, key=lambda item: item[0])[0] >= newscore:
        _, c, stage, group = max(regular, key=lambda item: item[0])
        return c, stage, group
    return campaign.new_candidate(parameters, source), 'axis', None
