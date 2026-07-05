"""Order/trade lifecycle processing over the StateStore.

Consumes *normalized* user-stream events (the wire-format extraction lives in
userstream/, so this is unit-testable with synthetic events) and drives the
state machine from the README:

    Trade:  MATCHED -> MINED -> CONFIRMED
                 └──────────-> FAILED (roll back the optimistic fill, reconcile)

Because we quote post-only, we are always the maker; `our_side` is our side of
each match. We apply the fill optimistically at MATCHED and reverse it on FAILED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from polymaker.domain import Fill, OpenOrder, OrderState, Side, TradeState
from polymaker.logging import get_logger
from polymaker.state.store import StateStore

log = get_logger("state.tracker")


@dataclass(frozen=True, slots=True)
class TradeEvent:
    token_id: str
    our_side: Side
    price: float
    size: float
    trade_id: str
    status: TradeState
    ts: float


@dataclass(frozen=True, slots=True)
class OrderEvent:
    order_id: str
    token_id: str
    side: Side
    price: float
    remaining_size: float  # original - matched
    is_cancel: bool = False


class UserEventProcessor:
    """Applies normalized trade/order events to the store."""

    def __init__(
        self,
        store: StateStore,
        on_change: Callable[[str], None] | None = None,
        on_fill: Callable[[Fill], None] | None = None,
    ) -> None:
        self._store = store
        self._on_change = on_change or (lambda _cid: None)
        self._on_fill = on_fill or (lambda _fill: None)
        # trade_id -> applied Fill, so FAILED can reverse exactly what we applied
        self._applied: dict[str, Fill] = {}

    def on_trade(self, ev: TradeEvent, condition_id: str) -> None:
        if ev.status is TradeState.MATCHED:
            if ev.trade_id in self._applied:
                return  # idempotent: already counted this match
            fill = Fill(ev.token_id, ev.our_side, ev.price, ev.size, ev.trade_id, ev.ts, is_maker=True)
            self._store.apply_fill(fill)
            self._store.mark_inflight(ev.token_id)
            self._applied[ev.trade_id] = fill
            self._on_fill(fill)
            self._on_change(condition_id)

        elif ev.status in (TradeState.CONFIRMED, TradeState.MINED):
            if ev.trade_id in self._applied and ev.status is TradeState.CONFIRMED:
                self._store.clear_inflight(ev.token_id)
                # keep the fill; it's now settled
                self._applied.pop(ev.trade_id, None)
                self._on_change(condition_id)

        elif ev.status in (TradeState.FAILED, TradeState.RETRYING):
            prior = self._applied.pop(ev.trade_id, None)
            if prior is not None:
                # reverse the optimistic fill
                self._store.apply_fill(
                    Fill(prior.token_id, prior.side.opposite, prior.price, prior.size,
                         f"{prior.trade_id}:reverse", prior.ts, is_maker=True)
                )
                self._store.clear_inflight(ev.token_id)
                log.warning("trade_failed_reversed", trade_id=ev.trade_id, token=ev.token_id[:12])
                self._on_change(condition_id)

    def on_order(self, ev: OrderEvent, condition_id: str) -> None:
        if ev.is_cancel or ev.remaining_size <= 0:
            self._store.remove_order(ev.order_id)
        else:
            state = OrderState.LIVE
            self._store.upsert_order(
                OpenOrder(ev.order_id, ev.token_id, ev.side, ev.price, ev.remaining_size, state)
            )
        self._on_change(condition_id)
