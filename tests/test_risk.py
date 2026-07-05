"""Tests for the RiskManager gates and circuit breakers."""

from __future__ import annotations

from polymaker.config import RiskConfig
from polymaker.domain import Fill, Side
from polymaker.risk.manager import RiskManager
from polymaker.state.store import StateStore


def _rm(tmp_path, **over):
    cfg = RiskConfig(**{
        "max_total_exposure_usdc": 5000, "max_market_notional_usdc": 800,
        "max_event_group_loss_usdc": 1000, "daily_loss_kill_usdc": 250,
        **over,
    })
    store = StateStore(tmp_path / "s.db")
    return RiskManager(cfg, store), store


def test_daily_loss_kill_switch(tmp_path, meta):
    rm, store = _rm(tmp_path)
    # buy 1000 shares @ 0.50 -> -500 cash, +1000 inventory
    store.apply_fill(Fill(meta.yes.token_id, Side.BUY, 0.50, 1000, "t1"))
    rm.note_fill(Fill(meta.yes.token_id, Side.BUY, 0.50, 1000, "t1"))
    rm.update_mark(meta.yes.token_id, 0.50)
    rm.reset_day()
    assert rm.global_halt()[0] is False
    # fair value collapses to 0.20 -> unrealized loss 300 > 250 kill
    rm.update_mark(meta.yes.token_id, 0.20)
    halted, why = rm.global_halt()
    assert halted and "daily_loss" in why
    store.close()


def test_market_cap_triggers_reduce_only(tmp_path, meta):
    rm, store = _rm(tmp_path, max_market_notional_usdc=100)
    store.apply_fill(Fill(meta.yes.token_id, Side.BUY, 0.50, 300, "t1"))  # 150 notional > 100
    rm.update_mark(meta.yes.token_id, 0.50)
    rm.update_mark(meta.no.token_id, 0.50)
    d = rm.evaluate(meta, ws_stale=False, event_group_cost=0.0)
    assert d.reduce_only and d.reason == "market_cap"
    store.close()


def test_ws_stale_halts_market(tmp_path, meta):
    rm, store = _rm(tmp_path)
    d = rm.evaluate(meta, ws_stale=True, event_group_cost=0.0)
    assert d.halt and d.reason == "ws_stale"
    store.close()


def test_size_scale_tapers_near_cap(tmp_path, meta):
    rm, store = _rm(tmp_path, max_market_notional_usdc=100)
    # 85 notional -> 85% of cap -> should scale below 1.0 but not reduce-only
    store.apply_fill(Fill(meta.yes.token_id, Side.BUY, 0.50, 170, "t1"))  # 85 notional
    rm.update_mark(meta.yes.token_id, 0.50)
    rm.update_mark(meta.no.token_id, 0.50)
    d = rm.evaluate(meta, ws_stale=False, event_group_cost=0.0)
    assert not d.reduce_only
    assert 0.0 < d.size_scale < 1.0
    store.close()


def test_event_group_cap(tmp_path, meta):
    rm, store = _rm(tmp_path, max_event_group_loss_usdc=50)
    d = rm.evaluate(meta, ws_stale=False, event_group_cost=60.0)
    assert d.reduce_only and d.reason == "event_group_cap"
    store.close()


def test_error_rate_breaker(tmp_path, meta):
    rm, store = _rm(tmp_path, max_order_error_rate=0.25)
    for _ in range(15):
        rm.note_order_result(False)
    for _ in range(10):
        rm.note_order_result(True)  # 15/25 = 0.6 > 0.25
    assert rm.global_halt()[0] is True
    store.close()


def test_manual_kill(tmp_path, meta):
    rm, store = _rm(tmp_path)
    rm.kill()
    assert rm.global_halt() == (True, "manual_kill")
    store.close()
