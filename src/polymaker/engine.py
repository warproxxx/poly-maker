"""Engine: wires every component into a single async event loop.

Data flow per market:
  market WS -> OrderBook -> (wake) -> Quoter task -> strategy (pure) -> reconcile
  -> ExecutionGateway ; user WS -> StateStore ; periodic REST reconcile + heartbeat.

One lightweight quoter task per market, woken by book/fill events and debounced.
The strategy layer is pure; the engine owns all the state and I/O around it.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from typing import Any

from polymaker.catalog.gamma import GammaClient, fetch_reward_rates, parse_market
from polymaker.catalog.store import CatalogStore
from polymaker.config import Config, StrategyProfile
from polymaker.domain import Fill, MarketMeta
from polymaker.execution.gateway import ExecutionGateway
from polymaker.execution.reconciler import reconcile
from polymaker.journal import Journal
from polymaker.logging import get_logger
from polymaker.marketdata.parse import TradePrint
from polymaker.marketdata.service import MarketDataService
from polymaker.merge import Merger
from polymaker.risk.manager import RiskManager
from polymaker.state.store import StateStore
from polymaker.state.tracker import UserEventProcessor
from polymaker.strategy.estimators import (
    FlowEstimator,
    MarketEstimators,
    MarkoutTracker,
    VolEstimator,
)
from polymaker.strategy.quoting import QuoteInputs, compute_fair_value, construct_quotes
from polymaker.strategy.regime import RegimeInputs, RegimeMachine
from polymaker.userstream.client import UserStream

log = get_logger("engine")


class Engine:
    def __init__(self, cfg: Config, *, paper: bool = False) -> None:
        self.cfg = cfg
        self.paper = paper
        self._running = False

        self.journal = Journal(cfg.paths.journal_dir, enabled=cfg.engine.journal,
                               day="paper" if paper else "live")
        self.state = StateStore(cfg.paths.db)
        self.catalog = CatalogStore(cfg.paths.db)
        self.gateway = ExecutionGateway(cfg, self.journal, paper=paper)
        self.risk = RiskManager(cfg.risk, self.state)
        self.merger = Merger(cfg)

        self.md = MarketDataService(on_dirty=self._on_dirty, on_trade=self._on_trade,
                                    journal=self.journal, proxy=cfg.proxy)
        self.user_proc = UserEventProcessor(self.state, on_change=self._wake_cid,
                                            on_fill=self._on_fill)
        self.user: UserStream | None = None

        # per-market state
        self.metas: dict[str, MarketMeta] = {}
        self.profiles: dict[str, StrategyProfile] = {}
        self.est: dict[str, MarketEstimators] = {}
        self.regime_m: dict[str, RegimeMachine] = {}
        self._dirty: dict[str, asyncio.Event] = {}
        self._sweep: dict[str, bool] = {}
        self._merging: set[str] = set()
        self._token_cid: dict[str, str] = {}
        self._tasks: list[asyncio.Task[Any]] = []

    # ── lifecycle ───────────────────────────────────────────────────────
    async def start(self) -> None:
        self._running = True
        await self.gateway.connect()
        await self._resolve_markets()
        if not self.metas:
            log.warning("no_markets_selected", hint="add markets to config/markets.toml, run `polymaker scan`")
        await self._startup_reconcile()

        # subscribe feeds
        self.md.set_markets([(cid, [m.yes.token_id, m.no.token_id]) for cid, m in self.metas.items()])
        self.user = UserStream(
            self.gateway.creds, self.gateway.address, self.user_proc,
            other_token=self._other_token, condition_of_token=self._cid_of_token,
            journal=self.journal, proxy=self.cfg.proxy,
        )
        self.user.set_markets(list(self.metas))

        # launch tasks
        self._tasks.append(asyncio.create_task(self.md.run(), name="market_ws"))
        if not self.paper:
            self._tasks.append(asyncio.create_task(self.user.run(), name="user_ws"))
            self._tasks.append(asyncio.create_task(self._heartbeat_loop(), name="heartbeat"))
        self._tasks.append(asyncio.create_task(self._reconcile_loop(), name="reconcile"))
        for cid in self.metas:
            self._tasks.append(asyncio.create_task(self._quoter(cid), name=f"quote:{cid[:8]}"))
        self.risk.reset_day()
        log.info("engine_started", markets=len(self.metas), paper=self.paper)

    async def run_forever(self) -> None:
        await self.start()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*self._tasks)

    async def shutdown(self) -> None:
        self._running = False
        log.info("engine_shutdown")
        self.md.stop()
        if self.user:
            self.user.stop()
        for t in self._tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await self.gateway.cancel_all()
        self.journal.close()
        self.state.close()
        self.catalog.close()

    # ── market resolution ───────────────────────────────────────────────
    async def _resolve_markets(self) -> None:
        reward_rates: dict[str, float] | None = None
        async with GammaClient(self.cfg.wallet.gamma_host) as gamma:
            for entry in self.cfg.enabled_markets:
                meta = self.catalog.get_by_slug(entry.slug) if entry.slug else None
                if meta is None and entry.condition_id:
                    meta = self.catalog.get(entry.condition_id)
                if meta is None:  # fall back to a live Gamma fetch
                    if reward_rates is None:
                        reward_rates = await fetch_reward_rates(self.cfg.wallet.clob_host)
                    meta = await self._fetch_meta(gamma, entry.slug, entry.condition_id, reward_rates)
                if meta is None:
                    log.warning("market_unresolved", ref=entry.ref)
                    continue
                self.metas[meta.condition_id] = meta
                self.profiles[meta.condition_id] = self.cfg.profile_for(entry)
                self.est[meta.condition_id] = self._make_estimators(self.profiles[meta.condition_id])
                self.regime_m[meta.condition_id] = RegimeMachine()
                self._dirty[meta.condition_id] = asyncio.Event()
                for tok in (meta.yes.token_id, meta.no.token_id):
                    self._token_cid[tok] = meta.condition_id

    async def _fetch_meta(
        self, gamma: GammaClient, slug: str | None, condition_id: str | None,
        reward_rates: dict[str, float],
    ) -> MarketMeta | None:
        tag_id = self.catalog.cached_tag("politics")
        async for raw in gamma.iter_markets(tag_id=tag_id, max_pages=25):
            if (slug and raw.get("slug") == slug) or (condition_id and raw.get("conditionId") == condition_id):
                m = parse_market(raw, reward_rates)
                if m:
                    self.catalog.upsert_market(m)
                return m
        return None

    @staticmethod
    def _make_estimators(p: StrategyProfile) -> MarketEstimators:
        return MarketEstimators(
            vol=VolEstimator(p.vol_short_halflife_s, p.vol_long_halflife_s),
            flow=FlowEstimator(p.flow_ewma_halflife_s),
            markout=MarkoutTracker(),
        )

    async def _startup_reconcile(self) -> None:
        with contextlib.suppress(Exception):
            await self.gateway.cancel_all()  # clean slate; heartbeat covers crashes
        positions = await self.gateway.positions()
        if positions:
            self.state.reconcile_positions(positions)
            log.info("startup_positions", n=len(positions))

    # ── callbacks ───────────────────────────────────────────────────────
    def _on_dirty(self, condition_id: str, token_id: str) -> None:
        ev = self._dirty.get(condition_id)
        if ev is not None:
            ev.set()

    def _wake_cid(self, condition_id: str) -> None:
        ev = self._dirty.get(condition_id)
        if ev is not None:
            ev.set()

    def _on_trade(self, tp: TradePrint) -> None:
        cid = self._token_cid.get(tp.asset_id)
        if cid is None:
            return
        self.est[cid].flow.update(tp.aggressor, tp.size, tp.ts)
        # crude sweep flag: a single print larger than 3x base size
        base = self.profiles[cid].base_size_usdc / max(tp.price, 0.01)
        if tp.size >= 3 * base:
            self._sweep[cid] = True

    def _on_fill(self, fill: Fill) -> None:
        self.risk.note_fill(fill)
        cid = self._token_cid.get(fill.token_id)
        if cid is None:
            return
        est = self.est[cid]
        fv = est.last_fv if est.last_fv is not None else fill.price
        token_fv = fv if fill.token_id == self.metas[cid].yes.token_id else (1.0 - fv)
        est.markout.record_fill(fill.side, token_fv, fill.ts)

    # ── quoter ──────────────────────────────────────────────────────────
    async def _quoter(self, cid: str) -> None:
        debounce = self.cfg.engine.debounce_ms / 1000.0
        ev = self._dirty[cid]
        while self._running:
            try:
                await ev.wait()
                await asyncio.sleep(debounce)  # coalesce a burst of book updates
                ev.clear()
                await self._recompute(cid)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                log.error("quoter_error", cid=cid[:8], err=str(exc))
                await asyncio.sleep(0.5)

    async def _recompute(self, cid: str) -> None:
        meta = self.metas[cid]
        p = self.profiles[cid]
        yes_book = self.md.book(meta.yes.token_id)
        no_book = self.md.book(meta.no.token_id)
        if yes_book is None or yes_book.is_empty:
            return

        now = time.time()
        micro = yes_book.microprice(p.micro_levels)
        if micro is None:
            return
        est = self.est[cid]
        est.flow.decay_to(now)
        fv = compute_fair_value(micro, est.flow.z, meta.tick_size)
        prev_fv = est.last_fv
        est.on_fair_value(fv, now)

        self.risk.update_mark(meta.yes.token_id, fv)
        self.risk.update_mark(meta.no.token_id, 1.0 - fv)

        pos_yes = self.state.position(meta.yes.token_id)
        pos_no = self.state.position(meta.no.token_id)
        q_max = p.q_max_usdc
        inv_util = abs(pos_yes.size - pos_no.size) * fv / q_max if q_max > 0 else 0.0
        hours_to_end = _hours_to_end(meta.end_date_iso, now)
        ws_stale = (now - self.md.last_update_ts(meta.yes.token_id)) > self.cfg.risk.ws_stale_halt_s

        rd = self.risk.evaluate(meta, ws_stale=ws_stale,
                                event_group_cost=self._event_group_cost(meta))
        regime = self.regime_m[cid].decide(
            RegimeInputs(
                now=now, tick=meta.tick_size, fv=fv, prev_fv=prev_fv,
                vol_ratio=est.vol.ratio, flow_z=est.flow.z, inventory_util=inv_util,
                hours_to_end=hours_to_end, sweep_flagged=self._sweep.pop(cid, False),
                ws_stale=ws_stale, risk_halt=rd.halt, risk_reduce_only=rd.reduce_only,
            ),
            p,
        )

        tq = construct_quotes(QuoteInputs(
            meta=meta, regime=regime, fv=fv, vol_short=est.vol.short,
            toxicity=est.markout.toxicity, yes_view=yes_book.view(),
            no_view=(no_book.view() if no_book else _empty_view()),
            pos_yes=pos_yes, pos_no=pos_no, profile=p, now=now,
            risk_size_scale=rd.size_scale,
        ))

        live = self.state.orders_for(meta.yes.token_id) + self.state.orders_for(meta.no.token_id)
        plan = reconcile(tq, live, tick=meta.tick_size,
                         reprice_ticks=p.reprice_ticks, resize_frac=p.resize_frac)
        if plan.is_noop:
            self._maybe_merge(cid, meta, p, pos_yes.size, pos_no.size)
            return

        if plan.to_cancel:
            await self.gateway.cancel(plan.to_cancel)
            for oid in plan.to_cancel:
                self.state.remove_order(oid)
        if plan.to_place:
            placed = await self.gateway.place(plan.to_place, meta)
            self.risk.note_order_result(bool(placed) or not plan.to_place)
            for o in placed:
                self.state.upsert_order(o)
        log.info("requote", cid=cid[:8], regime=regime.value, fv=round(fv, 4),
                 place=len(plan.to_place), cancel=len(plan.to_cancel),
                 pos_yes=round(pos_yes.size, 1), pos_no=round(pos_no.size, 1))
        self._maybe_merge(cid, meta, p, pos_yes.size, pos_no.size)

    def _maybe_merge(self, cid: str, meta: MarketMeta, p: StrategyProfile,
                     yes_size: float, no_size: float) -> None:
        amount = min(yes_size, no_size)
        if amount < p.merge_min_size or cid in self._merging or self.paper:
            return
        self._merging.add(cid)
        self._tasks.append(asyncio.create_task(self._merge_task(cid, meta, amount)))

    async def _merge_task(self, cid: str, meta: MarketMeta, amount: float) -> None:
        try:
            raw = int(amount * 1e6)
            await asyncio.to_thread(self.merger.merge, meta.condition_id, raw, meta.neg_risk)
        finally:
            self._merging.discard(cid)

    # ── background loops ────────────────────────────────────────────────
    async def _heartbeat_loop(self) -> None:
        if not self.cfg.engine.heartbeat:
            return
        while self._running:
            await self.gateway.heartbeat()
            await asyncio.sleep(self.cfg.engine.heartbeat_interval_s)

    async def _reconcile_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.cfg.engine.reconcile_interval_s)
            try:
                positions = await self.gateway.positions()
                if positions:
                    self.state.reconcile_positions(positions)
                live = await self.gateway.open_orders()
                if live or not self.paper:
                    by_token: dict[str, list[Any]] = {}
                    for o in live:
                        by_token.setdefault(o.token_id, []).append(o)
                    for tok, orders in by_token.items():
                        if self.state.inflight(tok) == 0:
                            self.state.replace_open_orders(tok, orders)
            except Exception as exc:  # noqa: BLE001
                log.warning("reconcile_error", err=str(exc))

    # ── helpers ─────────────────────────────────────────────────────────
    def _other_token(self, token_id: str) -> str | None:
        cid = self._token_cid.get(token_id)
        return self.metas[cid].other_token(token_id) if cid else None

    def _cid_of_token(self, token_id: str) -> str | None:
        return self._token_cid.get(token_id)

    def _event_group_cost(self, meta: MarketMeta) -> float:
        if not meta.event_id:
            return 0.0
        cost = 0.0
        for m in self.metas.values():
            if m.event_id == meta.event_id:
                for tok in (m.yes.token_id, m.no.token_id):
                    pos = self.state.position(tok)
                    cost += pos.size * pos.avg_price
        return cost


def _hours_to_end(end_date_iso: str | None, now: float) -> float | None:
    if not end_date_iso:
        return None
    try:
        dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        return max(0.0, (dt.timestamp() - now) / 3600.0)
    except (ValueError, TypeError):
        return None


def _empty_view() -> Any:
    from polymaker.marketdata.orderbook import BookView

    return BookView(None, 0.0, None, 0.0, None, None, 0.0, 0.0)
