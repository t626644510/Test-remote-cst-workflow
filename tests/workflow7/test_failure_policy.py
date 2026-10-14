"""Deterministic initializer failures must not spend identical EM retries."""
from dataclasses import asdict
from pathlib import Path
import sys
import traceback

import pytest

from workflows.rfgun_wakis import worker
from workflows.rfgun_wakis.campaign import Campaign, StageFailure
from workflows.rfgun_wakis.config import Config, Paths
from workflows.rfgun_wakis.failures import classify_failure
from workflows.rfgun_wakis.geometry import Geometry
from workflows.rfgun_wakis.io import atomic_json, digest, read_json
from workflows.rfgun_wakis.processes import OwnershipError


def guard_trace(message='0.5210513107130209', filename=None):
    # Exercise an actual Python traceback without importing CUDA or running EM.
    filename = filename or str(Path(worker.__file__).parent/'backend/surface_copper.py')
    scope = {}
    exec(compile('def __init__():\n    raise RuntimeError(' +
                 repr('Surface explicit coupling bound too large: '+message) + ')', filename, 'exec'), scope)
    try:
        scope['__init__']()
    except RuntimeError:
        return traceback.format_exc()


def campaign_with_prepared_candidate(tmp_path):
    import numpy as np
    config = Config(Paths('source', str(tmp_path/'round'), str(tmp_path/'bulk'), 'python', 'wakis', 'cst'))
    config_path = tmp_path/'config.json'
    atomic_json(config_path, config.as_dict())
    campaign = Campaign(config_path)
    parameters = Geometry(config).sample(np.random.default_rng(3), 1)[0]
    prepared = tmp_path/'prepared'
    atomic_json(prepared/'manifest.json', {})
    candidate = dict(id='candidate_0000', parameters=parameters, prepared=str(prepared),
                     observations={}, status='axis_pending', forced_transverse=True)
    campaign.store.data['candidates'] = [candidate]
    campaign.store.activate(0)
    campaign.store.begin(dict(key='candidate_0000_axis', candidate_index=0, stage='axis'))
    return campaign, candidate


@pytest.mark.parametrize('bound', ['0.5', '0.5210513107130209', 'inf'])
def test_initializer_guard_has_structured_no_retry_policy(bound):
    policy = classify_failure('solve', guard_trace(bound))
    assert not policy.retry_identical
    assert policy.category == 'surface_coupling_initialization_guard'
    assert policy.numerical_steps_started is False
    assert policy.guard_limit == 0.5


@pytest.mark.parametrize('phase,trace', [
    ('prepare', guard_trace()),
    ('analyze', guard_trace()),
    ('solve', guard_trace('nan')),
    ('solve', guard_trace('0.49')),
    ('solve', guard_trace('invalid')),
    ('solve', guard_trace(filename='unrelated.py')),
    ('solve', guard_trace()+'RuntimeError: later unrelated error\n'),
    ('solve', 'RuntimeError: Surface explicit coupling bound too large: 0.6\n'),
])
def test_unrelated_failures_keep_bounded_retry_policy(phase, trace):
    assert classify_failure(phase, trace).retry_identical


def test_worker_preserves_trace_and_serializes_policy(tmp_path, monkeypatch):
    request_path = tmp_path/'request.json'
    atomic_json(request_path, dict(phase='solve', request_id='request', contract='contract'))
    scope = {}
    source = 'def fail(request):\n    return __init__()\ndef __init__():\n    raise RuntimeError("Surface explicit coupling bound too large: 0.6")'
    exec(compile(source, str(Path(worker.__file__).parent/'backend/surface_copper.py'), 'exec'), scope)
    monkeypatch.setattr(worker, 'execute', scope['fail'])
    monkeypatch.setattr(sys, 'argv', ['worker', str(request_path)])
    assert worker.main() == 1
    reply = read_json(request_path.with_suffix('.reply.json'))
    assert reply['status'] == 'failed'
    assert reply['request_id'] == 'request' and reply['contract'] == 'contract'
    assert reply['traceback'].endswith('RuntimeError: Surface explicit coupling bound too large: 0.6\n')
    assert reply['failure_policy']['retry_identical'] is False


@pytest.mark.parametrize('legacy_replay', [False, True])
def test_known_guard_stops_after_first_attempt_including_saved_reply(tmp_path, monkeypatch, legacy_replay):
    campaign, candidate = campaign_with_prepared_candidate(tmp_path)
    reply = dict(status='failed', traceback=guard_trace())
    if not legacy_replay:
        reply['failure_policy'] = asdict(classify_failure('solve', reply['traceback']))
    request_path = campaign.root/'jobs/candidate_0000_axis/axis_solve_00.json'
    saved_reply = request_path.with_suffix('.reply.json')
    if legacy_replay:
        atomic_json(request_path, dict(phase='solve', request_id='saved', contract=campaign.config.digest()))
        campaign.store.data['pending']['phase_requests'] = {'axis_solve_00': str(request_path)}
        atomic_json(saved_reply, reply)
        before = digest(saved_reply)
    calls = []
    def run(request, timeout):
        calls.append(request)
        return read_json(saved_reply) if legacy_replay else reply
    monkeypatch.setattr(campaign.supervisor, 'run', run)
    with pytest.raises(StageFailure) as failure:
        campaign.execute_stage()
    assert not failure.value.retry_identical
    assert calls == [request_path]
    assert candidate['observations'] == {}
    assert not campaign.store.data['completed_stage_keys']
    failure_record = read_json(campaign.store.path)['pending']['phase_failures']['axis_solve_00']
    assert failure_record['failure_policy']['numerical_steps_started'] is False
    assert failure_record['traceback'] == reply['traceback']
    if legacy_replay:
        assert digest(saved_reply) == before


def test_unknown_transient_failure_keeps_configured_retries(tmp_path, monkeypatch):
    campaign, _ = campaign_with_prepared_candidate(tmp_path)
    calls = []
    def run(request, timeout):
        calls.append(request)
        return dict(status='failed', error='Host memory protection')
    monkeypatch.setattr(campaign.supervisor, 'run', run)
    with pytest.raises(StageFailure):
        campaign.execute_stage()
    assert len(calls) == campaign.config.runtime.retries+1 == 3


def test_completed_fields_take_precedence_over_failed_reply(tmp_path, monkeypatch):
    campaign, candidate = campaign_with_prepared_candidate(tmp_path)
    field = campaign.bulk/'candidate_0000/axis_00'
    calls = []
    def run(request, timeout):
        spec = read_json(request)
        calls.append(spec['phase'])
        if spec['phase'] == 'solve':
            atomic_json(field/'field_complete.json', dict(steps=100, complete_steps=100))
            return dict(status='failed', traceback=guard_trace())
        return dict(status='completed', result=dict(stage='axis', parameters=candidate['parameters'],
                    observations={}, field_directory=str(field)))
    monkeypatch.setattr(campaign.supervisor, 'run', run)
    campaign.execute_stage()
    assert calls == ['solve', 'analyze']
    assert campaign.store.data['pending'] is None
    assert candidate['axis_directory'] == str(field)


def test_ownership_fault_is_not_converted_into_candidate_skip(tmp_path, monkeypatch):
    campaign, _ = campaign_with_prepared_candidate(tmp_path)
    def run(request, timeout):
        raise OwnershipError('Foreign phase reply')
    monkeypatch.setattr(campaign.supervisor, 'run', run)
    with pytest.raises(OwnershipError):
        campaign.execute_stage()
    assert campaign.store.data['pending'] is not None
    assert not campaign.store.data['failures']
