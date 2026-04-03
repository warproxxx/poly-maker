"""
AppState: the single shared state object for the entire bot.

Design rules:
  - All writes happen only from the asyncio event loop (never from threads).
  - Background threads may READ state but must never write it.
  - Components receive a reference to AppState and read from it directly;
    they mutate it via the explicit helper methods below to keep writes visible.
  - Per-market asyncio.Lock instances in market_locks serialize strategy
    evaluations so concurrent WS events for the same market don't race.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.types import MarketInfo, Position, OpenOrder

if TYPE_CHECKING:
    from core.orderbook import OrderBook


@dataclass
class AppState:
    # ── Market registry ──────────────────────────────────────────────────────
    # condition_id → MarketInfo  (written by MarketRegistry only)
    markets: dict[str, MarketInfo] = field(default_factory=dict)

    # ── Order books ──────────────────────────────────────────────────────────
    # condition_id → OrderBook  (written by MarketFeed only)
    order_books: dict[str, "OrderBook"] = field(default_factory=dict)

    # ── Position state ───────────────────────────────────────────────────────
    # token_id → Position  (written by PositionTracker only)
    positions: dict[str, Position] = field(default_factory=dict)

    # ── Open orders ──────────────────────────────────────────────────────────
    # order_id → OpenOrder  (written by Executor + Reconciler)
    open_orders: dict[str, OpenOrder] = field(default_factory=dict)

    # ── Concurrency ──────────────────────────────────────────────────────────
    # Per-market lock; created on demand by get_market_lock()
    _market_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    # ── Inflight order tracking ───────────────────────────────────────────────
    # (token_id, side, price) keys currently being posted (dedup guard)
    inflight: set[tuple[str, str, float]] = field(default_factory=set)

    # ── Wallet ───────────────────────────────────────────────────────────────
    browser_address: str = ""

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def get_market_lock(self, condition_id: str) -> asyncio.Lock:
        """Return (creating if absent) the per-market asyncio Lock."""
        if condition_id not in self._market_locks:
            self._market_locks[condition_id] = asyncio.Lock()
        return self._market_locks[condition_id]

    def get_position(self, token_id: str) -> Position:
        """Return position for token_id, defaulting to a flat zero position."""
        return self.positions.get(
            token_id,
            Position(token_id=token_id, size=0.0, avg_price=0.0),
        )

    def get_open_orders_for_token(self, token_id: str) -> list[OpenOrder]:
        """Return all resting orders for a given token."""
        return [o for o in self.open_orders.values() if o.token_id == token_id]

    def get_open_orders_for_market(self, condition_id: str) -> list[OpenOrder]:
        """Return all resting orders across YES and NO tokens of a market."""
        return [o for o in self.open_orders.values() if o.condition_id == condition_id]

    def remove_orders_for_token(self, token_id: str) -> None:
        """Remove all cached open orders for a token (called after cancel)."""
        ids_to_remove = [oid for oid, o in self.open_orders.items() if o.token_id == token_id]
        for oid in ids_to_remove:
            del self.open_orders[oid]

    def remove_orders_for_market(self, condition_id: str) -> None:
        """Remove all cached open orders for a market."""
        ids_to_remove = [
            oid for oid, o in self.open_orders.items() if o.condition_id == condition_id
        ]
        for oid in ids_to_remove:
            del self.open_orders[oid]

    def remove_market(self, condition_id: str) -> None:
        """Tear down all state for an expired/resolved market."""
        self.markets.pop(condition_id, None)
        self.order_books.pop(condition_id, None)
        self._market_locks.pop(condition_id, None)
        self.remove_orders_for_market(condition_id)
        # Positions intentionally kept until reconciler or merger clears them.
