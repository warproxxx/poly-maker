"""Unit tests for the online estimators (vol, flow, markout/toxicity)."""

from __future__ import annotations

import pytest

from polymaker.domain import Side
from polymaker.strategy.estimators import (
    Ewma,
    FlowEstimator,
    MarkoutTracker,
    VolEstimator,
)


def test_ewma_seeds_then_decays():
    e = Ewma(halflife_s=10.0)
    assert not e.ready
    e.update(1.0, ts=0.0)
    assert e.value == 1.0
    # after exactly one half-life, a 0 observation pulls the mean halfway
    e.update(0.0, ts=10.0)
    assert e.value == pytest.approx(0.5, abs=1e-9)


def test_ewma_decay_to_ages_value():
    e = Ewma(halflife_s=10.0)
    e.update(1.0, ts=0.0)
    e.decay_to(ts=10.0)  # one half-life of silence
    assert e.value == pytest.approx(0.5, abs=1e-9)


def test_vol_estimator_rises_with_movement():
    v = VolEstimator(short_halflife_s=5.0, long_halflife_s=100.0)
    # quiet: tiny moves
    fv, t = 0.5, 0.0
    for _ in range(20):
        t += 1.0
        v.update(fv, t)  # no change -> zero vol
    assert v.short == pytest.approx(0.0, abs=1e-6)
    # sudden jumps -> short vol jumps, ratio > 1
    for step in (0.05, -0.04, 0.06):
        t += 1.0
        fv += step
        v.update(fv, t)
    assert v.short > 0.01
    assert v.ratio > 1.0


def test_flow_estimator_sign_and_z():
    f = FlowEstimator(halflife_s=10.0)
    t = 0.0
    for _ in range(5):
        t += 1.0
        f.update(Side.BUY, 100, t)  # persistent buying
    assert f.signed > 0
    assert f.z > 0.5  # strongly one-sided
    # now heavy selling flips the sign over time
    for _ in range(10):
        t += 1.0
        f.update(Side.SELL, 200, t)
    assert f.signed < 0
    assert f.z < 0


def test_markout_toxicity_from_adverse_fills():
    mt = MarkoutTracker(horizon_s=30.0, ewma_halflife_s=100.0)
    # we BUY at fv=0.50; price then falls to 0.45 after the horizon -> adverse
    mt.record_fill(Side.BUY, fv_at_fill=0.50, ts=0.0)
    mt.evaluate(fv_now=0.50, ts=10.0)  # before horizon: nothing resolves
    assert mt.markout == 0.0
    mt.evaluate(fv_now=0.45, ts=31.0)  # after horizon: -0.05 markout
    assert mt.markout < 0
    assert mt.toxicity > 0


def test_markout_benign_fills_are_not_toxic():
    mt = MarkoutTracker(horizon_s=30.0, ewma_halflife_s=100.0)
    # we BUY at 0.50; price rises to 0.55 -> favorable, not toxic
    mt.record_fill(Side.BUY, fv_at_fill=0.50, ts=0.0)
    mt.evaluate(fv_now=0.55, ts=31.0)
    assert mt.markout > 0
    assert mt.toxicity == 0.0
