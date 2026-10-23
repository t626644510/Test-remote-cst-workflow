"""Signed penetration constraints and newly reachable GP domain (lengths in mm)."""
from dataclasses import replace

import numpy as np
import pytest

from workflows.rfgun_wake_thermal.config import Config, Paths, NAMES
from workflows.rfgun_wake_thermal.geometry import Geometry
from workflows.rfgun_wake_thermal.search import Controller

pytestmark = pytest.mark.no_cst


def configuration():
    return Config(paths=Paths(templates={}, output_dir='unused', artifact_dir='unused'))


def point():
    return dict(zip(NAMES, [90., 10., 0., 40., 12., 15.] * 2))


@pytest.mark.parametrize('branch', [1, 2])
@pytest.mark.parametrize('down,valid', [(0., True), (10., True), (30., True),
                                     (-9.98, True), (-9.995, False), (-10., False),
                                     (39.995, False), (51., False)])
def test_signed_flange_and_inner_clearance(branch, down, valid):
    p = point()
    p[f'DownHeight{branch}'] = down
    geometry = Geometry(configuration())
    assert (not geometry.violations(p)) is valid
    if valid:
        assert geometry.collapse(geometry.expand(p)) == pytest.approx(p)
    else:
        with pytest.raises(ValueError):
            geometry.expand(p)


def test_old_domain_is_subset_and_new_gp_pool_reaches_both_extensions():
    cfg = configuration()
    cfg = replace(cfg, search=replace(cfg.search, pool=1024))
    controller = Controller(cfg, {'candidates': [], 'radius': .2})
    pool = [controller.decode(x) for x in controller.pool()]
    assert all(not controller.geometry.violations(p) for p in pool)
    for i in (1, 2):
        assert any(p[f'DownHeight{i}'] > p[f'UpperHeight{i}'] for p in pool)
    # Independent old predicate: every previously valid random point survives.
    rng = np.random.default_rng(987)
    checked = 0
    for x in rng.random((5000, 12)):
        p = controller.decode(x)
        if all(abs(p[f'DownHeight{i}']) <= p[f'UpperHeight{i}'] - .01
               and p[f'Lin{i}'] - p[f'DownHeight{i}'] >= .01 for i in (1, 2)):
            checked += 1
            assert not controller.geometry.violations(p)
    assert checked > 100


def test_gp_accepts_observation_from_new_domain_without_changing_noise():
    cfg = configuration()
    p = point()
    p['DownHeight1'] = 30.
    candidate = dict(parameters=p, metrics={'longitudinal': 1900.})
    rows = Controller(cfg, {'candidates': [candidate]}).training_rows('longitudinal')
    assert len(rows) == 1
    assert rows[0][1:] == (1900., cfg.search.native_relative_noise, False)
