"""Hardening batch 2: Tier 0-3 fixes — inflight expiry, crossed-book guard,
metadata halt, load shed, exit floor, divergence correction, per-market lock,
CSV export, WAL/pnl."""

from __future__ import annotations

import asyncio
import time

from polymaker.domain import Fill, Position, Regime, Side
from polymaker.state.store import StateStore
from polymaker.strategy.quoting import QuoteInputs, construct_quotes
from tests.conftest import view
from tests.test_engine import _engine_with_market, _feed_book


# ── T0-1: inflight expiry ────────────────────────────────────────────────
def test_inflight_expires_after_max_age(tmp_path):
    s = StateStore(tmp_path / "s.db")
    s.mark_inflight("tok")
    assert s.inflight("tok") == 1
    # not yet stale
    assert s.expire_inflight(max_age_s=100) == []
    assert s.inflight("tok") == 1
    # force age by rewriting the stored ts
    s._inflight_ts["tok"] = time.time() - 999
    cleared = s.expire_inflight(max_age_s=100)
    assert cleared == ["tok"]
    assert s.inflight("tok") == 0
    s.close()


# ── T0-7: exit sizing floors (never over-sell) ───────────────────────────
def test_exit_size_is_floored(meta, profile):
    # hold a fractional position; the SELL must be floored so size <= held
    tq = construct_quotes(QuoteInputs(
        meta=meta, regime=Regime.REDUCE_ONLY, fv=0.5, vol_short=0.0, toxicity=0.0,
        yes_view=view(0.49, 0.51), no_view=view(0.49, 0.51),
        pos_yes=Position("yes-token", 17.999, 0.4), pos_no=Position("no-token"),
        profile=profile, now=1000.0,
    ))
    sells = [q for q in tq.quotes if q.side == Side.SELL]
    assert sells
    assert sells[0].size <= 17.999  # floored, never rounded up past the holding
    assert sells[0].size == 17.99


# ── T0-5: crossed-book guard ─────────────────────────────────────────────
async def test_crossed_book_skips_quoting(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    now = time.time()
    # crossed: best bid (0.55) above best ask (0.45)
    eng.md.book(meta.yes.token_id).apply_snapshot(bids=[(0.55, 100)], asks=[(0.45, 100)], ts=now)
    eng.md.book(meta.no.token_id).apply_snapshot(bids=[(0.45, 100)], asks=[(0.55, 100)], ts=now)
    await eng._recompute(meta.condition_id)
    assert eng.state.orders == {}  # no quotes on a nonsensical book
    eng.state.close()
    eng.catalog.close()


# ── T0-2: metadata halt pulls quotes ─────────────────────────────────────
async def test_halted_market_pulls_quotes(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    _feed_book(eng, meta)
    await eng._recompute(meta.condition_id)
    assert len(eng.state.orders) > 0  # quoting normally
    # market flagged closed/not-accepting by the metadata refresh
    eng._halted.add(meta.condition_id)
    await eng._recompute(meta.condition_id)
    assert eng.state.orders == {}  # all pulled
    eng.state.close()
    eng.catalog.close()


# ── T1: load shedding under order pressure ───────────────────────────────
async def test_load_shed_skips_new_quotes_under_pressure(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    eng.paper = False  # shed only applies live
    _feed_book(eng, meta)
    placed_calls: list[int] = []

    async def spy_place(quotes, m):
        placed_calls.append(len(quotes))
        return []

    async def no_cancel(ids):
        return True

    # force high pressure
    for _ in range(1000):
        eng.gateway._order_bucket._tokens = 0.0
    eng.gateway.place = spy_place  # type: ignore[method-assign]
    eng.gateway.cancel = no_cancel  # type: ignore[method-assign]
    await eng._recompute(meta.condition_id)
    assert eng.gateway.order_pressure > 0.85
    assert placed_calls == []  # new quotes shed, not placed
    eng.state.close()
    eng.catalog.close()


# ── per-market lock serializes recompute vs reconcile ────────────────────
async def test_recompute_holds_market_lock(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    _feed_book(eng, meta)
    lock = eng._locks[meta.condition_id]
    await lock.acquire()  # simulate reconcile holding it

    async def try_recompute():
        await eng._recompute(meta.condition_id)

    task = asyncio.create_task(try_recompute())
    await asyncio.sleep(0.05)
    assert not task.done()  # blocked on the lock
    lock.release()
    await task  # now proceeds
    eng.state.close()
    eng.catalog.close()


# ── T1: on-chain divergence correction ───────────────────────────────────
async def test_divergence_corrects_to_onchain(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    tok = meta.yes.token_id
    eng.state.apply_fill(Fill(tok, Side.BUY, 0.5, 100, "phantom"))  # internal says 100
    assert eng.state.position(tok).size == 100

    async def fake_balances(tokens):
        return {t: (5.0 if t == tok else 0.0) for t in tokens}  # chain says 5

    eng.gateway.token_balances = fake_balances  # type: ignore[method-assign]
    await eng._check_position_divergence()
    assert eng.state.position(tok).size == 5.0  # corrected to on-chain truth
    eng.state.close()
    eng.catalog.close()


# ── churn bug: resting orders must NOT shrink the size taper ─────────────
def test_open_orders_do_not_taper_quote_size(tmp_path, meta):
    """Regression: counting our own resting BUY orders toward market notional
    collapsed the next quote size to ~0 -> empty targets -> cancel/replace churn.
    Full resting quotes with zero filled inventory must keep size_scale = 1.0."""
    from polymaker.config import RiskConfig
    from polymaker.domain import OpenOrder, OrderState
    from polymaker.risk.manager import RiskManager

    store = StateStore(tmp_path / "s.db")
    rm = RiskManager(RiskConfig(max_market_notional_usdc=15.0), store)
    rm.update_mark(meta.yes.token_id, 0.2)
    rm.update_mark(meta.no.token_id, 0.8)
    # rest ~$14 of BUY orders (near cap) but hold NO inventory
    store.upsert_order(OpenOrder("y", meta.yes.token_id, Side.BUY, 0.2, 50, OrderState.LIVE))
    store.upsert_order(OpenOrder("n", meta.no.token_id, Side.BUY, 0.79, 6, OrderState.LIVE))
    d = rm.evaluate(meta, ws_stale=False, event_group_cost=0.0)
    assert not d.reduce_only
    assert d.size_scale == 1.0  # resting orders do not taper -> no churn
    # but FILLED inventory near cap DOES taper
    store.apply_fill(Fill(meta.yes.token_id, Side.BUY, 0.2, 70, "f"))  # $14 position
    d2 = rm.evaluate(meta, ws_stale=False, event_group_cost=0.0)
    assert d2.size_scale < 1.0
    store.close()


# ── T2: PnL snapshot + CSV export smoke ──────────────────────────────────
def test_pnl_snapshot_and_wal(tmp_path):
    s = StateStore(tmp_path / "s.db")
    s.record_pnl(100.0, 50.0, 50.0, 1.5)
    s.checkpoint_wal()  # must not raise
    row = s._conn.execute("SELECT equity, daily_pnl FROM pnl_snapshots").fetchone()
    assert row["equity"] == 100.0 and row["daily_pnl"] == 1.5
    s.close()


def test_catalog_csv_export(tmp_path):
    from polymaker.catalog.gamma import parse_market
    from polymaker.catalog.store import CatalogStore
    from tests.test_catalog import RAW

    store = CatalogStore(tmp_path / "c.db")
    store.upsert_market(parse_market(RAW, {"0xabc": 42.0}))
    out = tmp_path / "markets.csv"
    n = store.export_csv(out)
    assert n == 1
    text = out.read_text()
    assert "slug" in text and "will-x-win" in text and "condition_id" in text
    store.close()
