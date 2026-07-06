"""Integration test: one full engine recompute cycle in paper mode (no network)."""

from __future__ import annotations

import asyncio
import time

from polymaker.config import Config, PathsConfig, StrategyProfile
from polymaker.domain import Side
from polymaker.engine import Engine
from polymaker.strategy.regime import RegimeMachine


def _engine_with_market(tmp_path, meta) -> Engine:
    cfg = Config(paths=PathsConfig(db=str(tmp_path / "state.db"),
                                   journal_dir=str(tmp_path / "j"),
                                   log_dir=str(tmp_path / "l")))
    cfg.engine.journal = False
    eng = Engine(cfg, paper=True)
    cid = meta.condition_id
    # inject one market directly, bypassing network resolution
    eng.metas[cid] = meta
    eng.profiles[cid] = StrategyProfile()
    eng.est[cid] = Engine._make_estimators(eng.profiles[cid])
    eng.regime_m[cid] = RegimeMachine()
    eng._dirty[cid] = asyncio.Event()
    eng._locks[cid] = asyncio.Lock()
    for tok in (meta.yes.token_id, meta.no.token_id):
        eng._token_cid[tok] = cid
    eng.md.set_markets([(cid, [meta.yes.token_id, meta.no.token_id])])
    eng._running = True
    return eng


def _feed_book(eng, meta):
    now = time.time()  # fresh ts so the ws_stale guard doesn't HALT the market
    yb = eng.md.book(meta.yes.token_id)
    yb.apply_snapshot(bids=[(0.48, 500), (0.49, 500)], asks=[(0.51, 500), (0.52, 500)], ts=now)
    nb = eng.md.book(meta.no.token_id)
    nb.apply_snapshot(bids=[(0.48, 500), (0.49, 500)], asks=[(0.51, 500), (0.52, 500)], ts=now)


async def test_recompute_places_two_sided_paper_quotes(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    _feed_book(eng, meta)
    await eng._recompute(meta.condition_id)

    yes_orders = eng.state.orders_for(meta.yes.token_id)
    no_orders = eng.state.orders_for(meta.no.token_id)
    assert yes_orders, "no YES quotes placed"
    assert no_orders, "no NO quotes placed"
    # entry quotes are BUYs on both tokens (the canonical two-sided quote)
    assert all(o.side is Side.BUY for o in yes_orders)
    assert all(o.side is Side.BUY for o in no_orders)
    eng.state.close()
    eng.catalog.close()


async def test_recompute_is_idempotent_within_tolerance(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    _feed_book(eng, meta)
    await eng._recompute(meta.condition_id)
    n_after_first = len(eng.state.orders)
    # same book -> reconcile should be a no-op, order count unchanged
    await eng._recompute(meta.condition_id)
    assert len(eng.state.orders) == n_after_first
    eng.state.close()
    eng.catalog.close()


async def test_recompute_skips_when_book_empty(tmp_path, meta):
    eng = _engine_with_market(tmp_path, meta)
    # no book fed
    await eng._recompute(meta.condition_id)
    assert len(eng.state.orders) == 0
    eng.state.close()
    eng.catalog.close()
