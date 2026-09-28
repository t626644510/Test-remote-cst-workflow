"""Campaign stopping and durable expensive-call accounting without CST."""

import copy
from dataclasses import replace
import json
import math

import numpy as np
import pytest

from workflows.rfgun_hom_target.config import (
    PARAMETER_DEFAULTS, ParameterConfig, PathsConfig, PhysicsConfig, SearchConfig,
    WorkflowConfig,
)
from workflows.rfgun_hom_target.search import Campaign, CandidatePlanner, objective
from workflows.rfgun_hom_target import search
from workflows.rfgun_hom_target.storage import CampaignStore


pytestmark = pytest.mark.no_cst


@pytest.fixture
def baseline():
    return dict(selfangle2=45., UpperHeight2=26., DownHeight2=4., Lin2=12.,
                inner_angle3=71., inner_r2=12.)


@pytest.fixture
def config(tmp_path):
    return WorkflowConfig(
        paths=PathsConfig(tmp_path / "template.cst", tmp_path / "run"),
        parameters=tuple(ParameterConfig(*p) for p in PARAMETER_DEFAULTS),
        physics=PhysicsConfig(z_range_mm=(-235., 235.)),
        search=SearchConfig(max_solves=6, initial_points=4, candidate_pool=16),
    )


@pytest.fixture
def store(config):
    instance = CampaignStore(config.paths.output_dir, "test-contract", config.search.max_solves)
    yield instance
    instance.close()


def test_baseline_pass_stops_after_one_solve_and_resume_does_not_solve(config, store, baseline):
    calls = []

    def evaluator(parameters, attempt, reserve):
        calls.append(parameters)
        reserve(str(attempt))
        return dict(status="valid", worst=100000.)

    report = Campaign(config, store, evaluator).run(baseline)
    assert report["status"] == "target_reached"
    assert report["solve_count"] == 1
    assert report["evaluations"] == 1
    assert report["best"]["objective"] == pytest.approx(math.log(2))
    Campaign(config, store, evaluator).run(baseline)
    assert calls == [baseline]


def test_stops_on_initial_design_pass_without_finishing_initial_batch(config, store, baseline):
    outputs = iter([200000., 90000.])
    calls = []

    def evaluator(parameters, attempt, reserve):
        calls.append(parameters)
        reserve(str(attempt))
        return dict(status="valid", worst=next(outputs))

    report = Campaign(config, store, evaluator).run(baseline)
    assert report["status"] == "target_reached"
    assert len(calls) == report["solve_count"] == 2
    assert report["evaluations"] < config.search.initial_points
    assert calls[0] != calls[1]


def test_failed_and_incomplete_observations_never_enter_gp(config, store, baseline):
    store.state["records"] = [
        dict(status="valid", parameters=baseline, objective=.5),
        dict(status="solver_failed", parameters=baseline, objective=-100.),
        dict(status="geometry_failed", parameters=baseline, objective=None),
        dict(status="postprocess_failed", parameters=baseline, objective=None),
        dict(status="valid", parameters=baseline, objective=float("nan")),
    ]
    x, y = CandidatePlanner(config, store.state).valid_training_data()
    assert x.shape == (1, 6)
    np.testing.assert_array_equal(y, [.5])
    assert np.isfinite(x).all()
    assert (0 <= x).all() and (x <= 1).all()


def test_empty_gp_training_has_consistent_coordinate_dimension(config, store):
    x, y = CandidatePlanner(config, store.state).valid_training_data()
    assert x.shape == (0, 6)
    assert y.shape == (0,)


@pytest.mark.parametrize("status", ["solver_failed", "geometry_failed", "quality_failed"])
def test_failed_baseline_stops_without_sampling(config, store, baseline, status):
    calls = []

    def evaluator(parameters, attempt, reserve):
        calls.append(parameters)
        if status != "geometry_failed":
            reserve(str(attempt))
        return dict(status=status, error="baseline invalid")

    report = Campaign(config, store, evaluator).run(baseline)
    assert report["status"] == "baseline_failed"
    assert len(calls) == 1
    assert report["best"] is None
    assert store.state["records"][0]["objective"] is None


def test_every_coverage_or_retry_call_consumes_budget_and_cannot_overrun(config, tmp_path, baseline):
    config = replace(config, search=replace(config.search, max_solves=3))
    store = CampaignStore(tmp_path / "budget", "test-contract", 3)
    starts = []

    def evaluator(parameters, attempt, reserve):
        for label in ("primary", "retry", "coverage_expand", "cannot_start"):
            reserve(f"{attempt}:{label}")
            starts.append(label)
        raise AssertionError("fourth solve should never start")

    try:
        report = Campaign(config, store, evaluator).run(baseline)
        assert report["status"] == "budget_exhausted"
        assert report["solve_count"] == 3
        assert starts == ["primary", "retry", "coverage_expand"]
        assert store.state["pending"]["source"] == "baseline"
        assert not store.state["records"]
    finally:
        store.close()


def test_reserved_call_survives_crash_and_resume_budget_does_not_reset(config, tmp_path, baseline):
    config = replace(config, search=replace(config.search, max_solves=1))
    root = tmp_path / "interrupted"
    store = CampaignStore(root, "test-contract", 1)

    def crash(parameters, attempt, reserve):
        reserve(str(attempt))
        raise KeyboardInterrupt()

    try:
        with pytest.raises(KeyboardInterrupt):
            Campaign(config, store, crash).run(baseline)
        persisted = json.loads((root / "state.json").read_text())
        assert persisted["solve_count"] == 1
        assert persisted["status"] == "interrupted"
        assert persisted["pending"]
    finally:
        store.close()
    resumed = CampaignStore(root, "test-contract", 1, resume=True)
    try:
        def retry(parameters, attempt, reserve):
            reserve("retry-after-crash")
            raise AssertionError("no remaining solve budget")
        report = Campaign(config, resumed, retry).run(baseline)
        assert report["status"] == "budget_exhausted"
        assert len(resumed.state["reservations"]) == 1
    finally:
        resumed.close()


def test_postprocess_pending_can_finish_after_entire_solve_budget_used(config, tmp_path, baseline):
    config = replace(config, search=replace(config.search, max_solves=1))
    root = tmp_path / "postprocess"
    store = CampaignStore(root, "test-contract", 1)

    def partial(parameters, attempt, reserve):
        reserve(str(attempt))
        return dict(status="postprocess_failed", error="temporary field export error")

    try:
        report = Campaign(config, store, partial).run(baseline)
        assert report["status"] == "postprocess_pending"
        pending_id = store.state["pending"]["id"]
        assert store.state["records"] == []
    finally:
        store.close()
    resumed = CampaignStore(root, "test-contract", 1, resume=True)
    try:
        def finish_postprocessing(parameters, attempt, reserve):
            assert attempt.name == pending_id
            return dict(status="valid", worst=50000.)
        report = Campaign(config, resumed, finish_postprocessing).run(baseline)
        assert report["status"] == "target_reached"
        assert report["solve_count"] == 1
        assert not report["error"]
        assert len(resumed.state["reservations"]) == 1
        assert len(resumed.state["records"]) == 1
        assert resumed.state["pending"] is None
    finally:
        resumed.close()


def test_dimensionless_objective_is_threshold_normalized():
    assert objective(100000., 100000.) == objective(1., 1.)
    assert objective(0., 100000.) == 0
    assert objective(200000., 100000.) > objective(100000., 100000.)


@pytest.mark.parametrize("worst,threshold", [(-1, 100000), (float("nan"), 100000), (1, 0)])
def test_invalid_objective_input_is_rejected(worst, threshold):
    with pytest.raises(ValueError):
        objective(worst, threshold)


def test_real_gp_uses_normalized_successes_and_resume_reproduces_next_candidate(
    config, tmp_path, baseline, monkeypatch, caplog,
):
    """Exercise sklearn fitting and shared EI, rather than mocking their output."""
    config = replace(config, search=replace(config.search, initial_points=3, candidate_pool=16))
    root = tmp_path / "gp-resume"
    store = CampaignStore(root, "gp-contract", config.search.max_solves)
    fit_inputs = []
    ei_inputs = []
    original_fit = search.GaussianProcessRegressor.fit
    original_ei = search.ExpectedImprovement.evaluate

    def observed_fit(model, x, y, *args, **kwargs):
        fit_inputs.append((x.copy(), y.copy()))
        return original_fit(model, x, y, *args, **kwargs)

    def observed_ei(acquisition, x, model, best):
        result = original_ei(acquisition, x, model, best)
        ei_inputs.append((x.copy(), result))
        return result

    monkeypatch.setattr(search.GaussianProcessRegressor, "fit", observed_fit)
    monkeypatch.setattr(search.ExpectedImprovement, "evaluate", observed_ei)
    measured = [
        (dict(baseline), 250000.),
        ({**baseline, "selfangle2": 80., "Lin2": 18., "inner_r2": 10.}, 170000.),
        ({**baseline, "selfangle2": 120., "inner_angle3": 95., "inner_r2": 9.}, 130000.),
    ]
    store.state["records"] = [
        dict(id=f"evaluation_{i:04d}", parameters=parameters, status="valid",
             worst=worst, objective=objective(worst, 100000.))
        for i, (parameters, worst) in enumerate(measured)
    ] + [dict(id="evaluation_0003", parameters={**baseline, "selfangle2": 160.},
              status="solver_failed", objective=-1e100)]
    try:
        planner = CandidatePlanner(config, store.state)
        candidate, source = planner.ask(baseline)
        assert source in {"local", "global"}
        assert planner.geometry.feasible(candidate)
        assert all(math.isfinite(value) for value in candidate.values())
        seen = {planner.key(row["parameters"]) for row in store.state["records"]}
        assert planner.key(candidate) not in seen
        expected_x = np.array([
            [(parameters[p.name] - p.lower) / (p.upper - p.lower) for p in config.parameters]
            for parameters, _ in measured
        ])
        expected_y = np.array([objective(worst, 100000.) for _, worst in measured])
        expected_y = (expected_y - expected_y.mean()) / expected_y.std()
        assert len(fit_inputs) == 1
        np.testing.assert_allclose(fit_inputs[0][0], expected_x)
        np.testing.assert_allclose(fit_inputs[0][1], expected_y)
        assert fit_inputs[0][0].shape == (3, 6)
        assert len(ei_inputs) == config.search.candidate_pool
        assert all(np.isfinite(value) for _, value in ei_inputs)
        assert all(((0 <= x) & (x <= 1)).all() for x, _ in ei_inputs)

        # Persist after observing the point, then compare uninterrupted and resumed asks.
        store.state["records"].append(dict(id="evaluation_0004", parameters=candidate,
            status="valid", worst=140000., objective=objective(140000., 100000.)))
        store.save()
        uninterrupted_state = copy.deepcopy(store.state)
        uninterrupted = CandidatePlanner(config, uninterrupted_state)
        expected_candidate, expected_source = uninterrupted.ask(baseline)
    finally:
        store.close()
    resumed = CampaignStore(root, "gp-contract", config.search.max_solves, resume=True)
    try:
        actual = CandidatePlanner(config, resumed.state)
        actual_candidate, actual_source = actual.ask(baseline)
        assert actual_candidate == expected_candidate
        assert actual_source == expected_source
        assert actual.geometry.feasible(actual_candidate)
        assert actual.key(actual_candidate) not in {
            actual.key(row["parameters"]) for row in resumed.state["records"]
        }
        assert resumed.state["rng_state"] == uninterrupted_state["rng_state"]
        assert len(fit_inputs) == 3
        assert fit_inputs[-1][0].shape == (4, 6)
        assert len(ei_inputs) == 3 * config.search.candidate_pool
        assert "GP unavailable" not in caplog.text
    finally:
        resumed.close()
