"""Unit tests for the regime state machine."""

from __future__ import annotations

from polymaker.config import StrategyProfile
from polymaker.domain import Regime
from polymaker.strategy.regime import RegimeInputs, RegimeMachine


def _inp(**over):
    base = dict(
        now=1000.0,
        tick=0.01,
        fv=0.50,
        prev_fv=0.50,
        vol_ratio=1.0,
        flow_z=0.0,
        inventory_util=0.0,
        hours_to_end=1000.0,
    )
    base.update(over)
    return RegimeInputs(**base)


def test_default_is_quiet():
    p = StrategyProfile()
    assert RegimeMachine().decide(_inp(), p) == Regime.QUIET


def test_halts_take_priority():
    p = StrategyProfile()
    m = RegimeMachine()
    assert m.decide(_inp(risk_halt=True), p) == Regime.HALTED
    assert m.decide(_inp(ws_stale=True), p) == Regime.HALTED
    assert m.decide(_inp(market_resolved=True), p) == Regime.HALTED
    assert m.decide(_inp(hours_to_end=1.0), p) == Regime.HALTED  # inside halt window


def test_fv_jump_triggers_event_and_cooloff():
    p = StrategyProfile()  # event_jump_ticks=8, cooloff=60
    m = RegimeMachine()
    # jump of 0.10 = 10 ticks > 8 -> EVENT
    assert m.decide(_inp(fv=0.60, prev_fv=0.50), p) == Regime.EVENT
    # still in cooloff a moment later even without a jump
    assert m.decide(_inp(now=1030.0, fv=0.60, prev_fv=0.60), p) == Regime.EVENT
    # after cooloff expires, back to quiet
    assert m.decide(_inp(now=1100.0, fv=0.60, prev_fv=0.60), p) == Regime.QUIET


def test_sweep_flag_triggers_event():
    p = StrategyProfile()
    assert RegimeMachine().decide(_inp(sweep_flagged=True), p) == Regime.EVENT


def test_reduce_only_from_inventory_and_enddate():
    p = StrategyProfile()  # reduce_only_hours=24
    m = RegimeMachine()
    assert m.decide(_inp(inventory_util=1.0), p) == Regime.REDUCE_ONLY
    assert m.decide(_inp(risk_reduce_only=True), p) == Regime.REDUCE_ONLY
    assert m.decide(_inp(hours_to_end=12.0), p) == Regime.REDUCE_ONLY


def test_trending_from_flow_and_vol():
    p = StrategyProfile()  # trend_flow_z=1.5
    m = RegimeMachine()
    assert m.decide(_inp(flow_z=2.0), p) == Regime.TRENDING
    assert m.decide(_inp(vol_ratio=3.0), p) == Regime.TRENDING


def test_event_beats_reduce_only_and_trending():
    p = StrategyProfile()
    m = RegimeMachine()
    r = m.decide(_inp(sweep_flagged=True, inventory_util=1.0, flow_z=5.0), p)
    assert r == Regime.EVENT
