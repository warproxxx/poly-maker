"""
Shared data types used across all layers of the market making bot.
No logic lives here — pure data containers only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MarketInfo:
    """Describes a single active prediction market (YES/NO binary)."""
    condition_id: str       # Market / condition ID used for on-chain ops
    token_yes: str          # YES outcome token ID
    token_no: str           # NO outcome token ID
    neg_risk: bool          # True for negative-risk markets (use NegRiskAdapter)
    tick_size: float        # Minimum price increment (e.g. 0.01)
    min_size: float         # Minimum order size in USDC
    expiry_time: datetime   # UTC datetime when the market resolves
    interval_minutes: int   # 5 or 15
    question: str           # Human-readable market question


@dataclass
class OrderBookLevel:
    """A single price level in the order book."""
    price: float
    size: float


@dataclass
class OrderBookSnapshot:
    """
    Immutable snapshot of an order book passed to strategy callbacks.
    Bids and asks are lists sorted best-first:
      bids: descending price  (index 0 = best bid)
      asks: ascending price   (index 0 = best ask)
    """
    condition_id: str
    token_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: float  # time.monotonic() at snapshot creation

    @property
    def best_bid(self) -> OrderBookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> OrderBookLevel | None:
        return self.asks[0] if self.asks else None

    @property
    def mid_price(self) -> float | None:
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return None

    @property
    def spread(self) -> float | None:
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None


@dataclass
class Position:
    """Tracks our current position in a single token."""
    token_id: str
    size: float         # Positive = long. Zero means no position.
    avg_price: float    # Average cost basis
    last_updated: float = 0.0  # time.monotonic()

    @property
    def is_long(self) -> bool:
        return self.size > 0

    @property
    def is_flat(self) -> bool:
        return self.size == 0


@dataclass
class OpenOrder:
    """Represents one of our resting limit orders."""
    order_id: str
    token_id: str
    condition_id: str
    side: str           # "BUY" or "SELL"
    price: float
    size_original: float
    size_remaining: float
    placed_at: float    # time.monotonic()


@dataclass
class QuoteRequest:
    """
    What the strategy tells the executor to do.
    None on a side means: do nothing on that side (keep existing order as-is).
    Pass cancel_all_first=True to wipe existing orders before placing new ones
    (used for stop-loss and expiry exit flows).
    """
    condition_id: str
    token_id: str
    bid_price: float | None = None
    bid_size: float | None = None
    ask_price: float | None = None
    ask_size: float | None = None
    cancel_all_first: bool = False
    # If True, post an aggressive exit order regardless of epsilon checks
    force_post: bool = False


@dataclass
class FillEvent:
    """A confirmed trade fill from the user WebSocket."""
    order_id: str
    trade_id: str
    token_id: str
    condition_id: str
    side: str       # "BUY" or "SELL"
    size: float
    price: float
    status: str     # "MATCHED" | "CONFIRMED" | "MINED" | "FAILED"
    timestamp: float


@dataclass
class LatencyRecord:
    """Structured latency log entry written after each order cycle."""
    condition_id: str
    t_ws_received: float        # time.monotonic() when WS message arrived
    t_book_updated: float       # after OrderBook.apply_*()
    t_strategy_returned: float  # after strategy.on_book_update() returned
    t_executor_submitted: float # after run_in_executor() was submitted (not completed)
    t_order_acked: float        # when API response came back
    action: str                 # "post_bid" | "post_ask" | "cancel" | "skip"
