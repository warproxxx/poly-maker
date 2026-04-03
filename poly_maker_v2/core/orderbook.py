"""
OrderBook: live, mutable order book backed by SortedDict.

Design:
  - One OrderBook instance per market (keyed by condition_id).
  - Written only by the MarketFeed from the asyncio event loop.
  - Strategy receives an immutable OrderBookSnapshot, not this object.
  - Uses SortedDict for O(log n) updates and O(1) best bid/ask via peekitem().

Token asymmetry note (inherited from reference):
  - The market WebSocket sends price_change events keyed by the YES token's
    asset_id regardless of which token the update is for.
  - The `primary_asset_id` stored at snapshot time lets us filter out
    duplicate events that would corrupt the NO token's book.
"""
from __future__ import annotations

import time
from typing import Any

from sortedcontainers import SortedDict

from core.types import OrderBookLevel, OrderBookSnapshot


class OrderBook:
    """
    Live order book for one market (both YES and NO share the same book
    because the market WS sends a combined view).

    Bids are stored ascending (SortedDict natural order), accessed via
    peekitem(-1) for best bid.
    Asks are stored ascending, accessed via peekitem(0) for best ask.
    """

    def __init__(self, condition_id: str, token_id: str) -> None:
        """
        Args:
            condition_id: Market / condition ID this book belongs to.
            token_id:     The primary YES token ID (used to filter WS dedup).
        """
        self.condition_id = condition_id
        self.token_id = token_id       # primary asset_id for dedup filtering
        self._bids: SortedDict = SortedDict()   # price → size, ascending
        self._asks: SortedDict = SortedDict()   # price → size, ascending
        self._last_updated: float = 0.0

    # ── Mutators (called from MarketFeed only) ─────────────────────────────

    def apply_snapshot(self, bids: list[dict[str, Any]], asks: list[dict[str, Any]]) -> None:
        """
        Replace the entire order book from a 'book' WS event.

        Args:
            bids: list of {"price": "0.45", "size": "120.5"} dicts
            asks: list of {"price": "0.55", "size": "80.0"} dicts
        """
        self._bids.clear()
        self._asks.clear()
        for entry in bids:
            p, s = float(entry["price"]), float(entry["size"])
            if s > 0:
                self._bids[p] = s
        for entry in asks:
            p, s = float(entry["price"]), float(entry["size"])
            if s > 0:
                self._asks[p] = s
        self._last_updated = time.monotonic()

    def apply_price_change(self, side: str, price: float, size: float) -> None:
        """
        Update a single price level from a 'price_change' WS event.
        size == 0 means the level was removed.

        Args:
            side:  "BUY" (bids) or "SELL" (asks)
            price: price level
            size:  new size at that level (0 = remove)
        """
        book = self._bids if side == "BUY" else self._asks
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size
        self._last_updated = time.monotonic()

    # ── Read-only accessors ────────────────────────────────────────────────

    @property
    def best_bid(self) -> tuple[float, float] | None:
        """(price, size) of the best bid, or None if book is empty."""
        if not self._bids:
            return None
        price, size = self._bids.peekitem(-1)   # highest price
        return price, size

    @property
    def best_ask(self) -> tuple[float, float] | None:
        """(price, size) of the best ask, or None if book is empty."""
        if not self._asks:
            return None
        price, size = self._asks.peekitem(0)    # lowest price
        return price, size

    @property
    def mid_price(self) -> float | None:
        """(best_bid + best_ask) / 2, or None if either side is empty."""
        bb = self.best_bid
        ba = self.best_ask
        if bb and ba:
            return (bb[0] + ba[0]) / 2
        return None

    @property
    def spread(self) -> float | None:
        """best_ask - best_bid, or None if either side is empty."""
        bb = self.best_bid
        ba = self.best_ask
        if bb and ba:
            return ba[0] - bb[0]
        return None

    @property
    def last_updated(self) -> float:
        return self._last_updated

    def bid_depth(self, levels: int = 5) -> list[tuple[float, float]]:
        """Top N bid levels as [(price, size)], best first (descending price)."""
        items = list(self._bids.items())
        return [(p, s) for p, s in reversed(items[-levels:])]

    def ask_depth(self, levels: int = 5) -> list[tuple[float, float]]:
        """Top N ask levels as [(price, size)], best first (ascending price)."""
        items = list(self._asks.items())
        return [(p, s) for p, s in items[:levels]]

    def bid_volume(self, levels: int = 5) -> float:
        """Total size across top N bid levels."""
        return sum(s for _, s in self.bid_depth(levels))

    def ask_volume(self, levels: int = 5) -> float:
        """Total size across top N ask levels."""
        return sum(s for _, s in self.ask_depth(levels))

    def imbalance(self, levels: int = 5) -> float | None:
        """
        Order book imbalance over top N levels.
        Returns value in [-1, 1]:  +1 = all bids, -1 = all asks.
        Returns None if total volume is zero.
        """
        bv = self.bid_volume(levels)
        av = self.ask_volume(levels)
        total = bv + av
        if total == 0:
            return None
        return (bv - av) / total

    # ── Snapshot (passed to strategy) ─────────────────────────────────────

    def snapshot(self, levels: int = 10) -> OrderBookSnapshot:
        """
        Return a frozen OrderBookSnapshot for strategy consumption.
        Bids: descending price (index 0 = best bid).
        Asks: ascending price  (index 0 = best ask).
        """
        bids = [
            OrderBookLevel(price=p, size=s)
            for p, s in reversed(list(self._bids.items())[-levels:])
        ]
        asks = [
            OrderBookLevel(price=p, size=s)
            for p, s in list(self._asks.items())[:levels]
        ]
        return OrderBookSnapshot(
            condition_id=self.condition_id,
            token_id=self.token_id,
            bids=bids,
            asks=asks,
            timestamp=self._last_updated,
        )

    def is_empty(self) -> bool:
        return not self._bids and not self._asks

    def __repr__(self) -> str:
        bb = self.best_bid
        ba = self.best_ask
        return (
            f"OrderBook({self.condition_id[:8]}… "
            f"bid={bb[0] if bb else 'N/A'} "
            f"ask={ba[0] if ba else 'N/A'})"
        )
