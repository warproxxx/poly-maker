"""Order book maintenance and analytics for a single market.

We keep the YES-token book canonical (bids/asks as SortedDicts keyed by price).
The NO-token view is derived by the identity  no_price = 1 - yes_price, with
bids/asks swapped — so we only ever maintain one book per market.

All methods are synchronous and side-effect-free reads except the explicit
apply_* mutators. Nothing here does I/O; the WS layer drives it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sortedcontainers import SortedDict

from polymaker.domain import Side


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True, slots=True)
class BookView:
    """A resolved best/second/depth snapshot for one outcome token."""

    best_bid: float | None
    best_bid_size: float
    best_ask: float | None
    best_ask_size: float
    second_bid: float | None
    second_ask: float | None
    bid_depth: float  # summed size within band, bid side
    ask_depth: float  # summed size within band, ask side

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def imbalance(self) -> float:
        """(bid_depth - ask_depth) / total in [-1, 1]; 0 if empty."""
        total = self.bid_depth + self.ask_depth
        return (self.bid_depth - self.ask_depth) / total if total > 0 else 0.0


class OrderBook:
    """YES-canonical L2 book for one market."""

    __slots__ = ("bids", "asks", "tick_size", "last_update_ts", "book_hash")

    def __init__(self, tick_size: float = 0.001) -> None:
        # price -> size. bids and asks both ascending in price.
        self.bids: SortedDict[float, float] = SortedDict()
        self.asks: SortedDict[float, float] = SortedDict()
        self.tick_size = tick_size
        self.last_update_ts: float = 0.0
        self.book_hash: str | None = None

    # ── mutation ────────────────────────────────────────────────────────
    def apply_snapshot(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        ts: float,
        book_hash: str | None = None,
    ) -> None:
        self.bids = SortedDict({p: s for p, s in bids if s > 0})
        self.asks = SortedDict({p: s for p, s in asks if s > 0})
        self.last_update_ts = ts
        self.book_hash = book_hash

    def apply_delta(self, side: Side, price: float, size: float, ts: float) -> None:
        book = self.bids if side is Side.BUY else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size
        self.last_update_ts = ts

    def set_tick_size(self, tick_size: float) -> None:
        self.tick_size = tick_size

    @property
    def is_empty(self) -> bool:
        return len(self.bids) == 0 or len(self.asks) == 0

    # ── raw best (YES side) ─────────────────────────────────────────────
    def best_bid(self) -> BookLevel | None:
        if not self.bids:
            return None
        p = self.bids.peekitem(-1)  # highest bid
        return BookLevel(p[0], p[1])

    def best_ask(self) -> BookLevel | None:
        if not self.asks:
            return None
        p = self.asks.peekitem(0)  # lowest ask
        return BookLevel(p[0], p[1])

    # ── analytics ───────────────────────────────────────────────────────
    def microprice(self, levels: int = 3) -> float | None:
        """Depth-weighted mid over the top `levels`, pulled toward the thin side.

        Uses size at the opposite side as the weight for each price (standard
        microprice intuition: price is dragged toward the side with less size).
        Returns None if either side is empty.
        """
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        bid_sz = self._top_size(self.bids, levels, from_high=True)
        ask_sz = self._top_size(self.asks, levels, from_high=False)
        total = bid_sz + ask_sz
        if total <= 0:
            return (bb.price + ba.price) / 2.0
        # weight best_ask by bid size and best_bid by ask size
        return (ba.price * bid_sz + bb.price * ask_sz) / total

    def best_with_min_size(
        self, side: Side, min_size: float
    ) -> tuple[float | None, float, float | None]:
        """First level (from the touch) with size > min_size.

        Returns (price, size, top_price) where top_price is the actual touch
        (used to detect dust at the front). Mirrors v1's find_best_price_with_size
        but without the second-best bookkeeping the new strategy doesn't need.
        """
        if side is Side.BUY:
            items = reversed(self.bids.items())  # high -> low
        else:
            items = iter(self.asks.items())  # low -> high
        top_price: float | None = None
        for price, size in items:
            if top_price is None:
                top_price = price
            if size > min_size:
                return price, size, top_price
        return None, 0.0, top_price

    def depth_within(self, side: Side, lo: float, hi: float) -> float:
        """Sum of sizes with price in [lo, hi] on the given side."""
        book = self.bids if side is Side.BUY else self.asks
        # SortedDict.irange gives keys in [lo, hi]
        return float(sum(book[p] for p in book.irange(lo, hi)))

    def view(self, band_frac: float = 0.05, min_size: float = 0.0) -> BookView:
        """Resolved YES-side view with best/second and in-band depth."""
        bb = self._nth_bid(0, min_size)
        ba = self._nth_ask(0, min_size)
        sb = self._nth_bid(1, min_size)
        sa = self._nth_ask(1, min_size)
        mid = None
        bid_depth = ask_depth = 0.0
        if bb is not None and ba is not None:
            mid = (bb.price + ba.price) / 2.0
            bid_depth = self.depth_within(Side.BUY, bb.price, mid * (1 + band_frac))
            ask_depth = self.depth_within(Side.SELL, mid * (1 - band_frac), ba.price)
        return BookView(
            best_bid=bb.price if bb else None,
            best_bid_size=bb.size if bb else 0.0,
            best_ask=ba.price if ba else None,
            best_ask_size=ba.size if ba else 0.0,
            second_bid=sb.price if sb else None,
            second_ask=sa.price if sa else None,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
        )

    # ── internals ───────────────────────────────────────────────────────
    def _nth_bid(self, n: int, min_size: float) -> BookLevel | None:
        count = 0
        for price in reversed(self.bids):
            if self.bids[price] > min_size:
                if count == n:
                    return BookLevel(price, self.bids[price])
                count += 1
        return None

    def _nth_ask(self, n: int, min_size: float) -> BookLevel | None:
        count = 0
        for price in self.asks:
            if self.asks[price] > min_size:
                if count == n:
                    return BookLevel(price, self.asks[price])
                count += 1
        return None

    @staticmethod
    def _top_size(book: SortedDict[float, float], levels: int, *, from_high: bool) -> float:
        keys = list(reversed(book)) if from_high else list(book)
        return float(sum(book[k] for k in keys[:levels]))


def to_no_price(yes_price: float) -> float:
    """Convert a YES price to the equivalent NO price."""
    return 1.0 - yes_price
