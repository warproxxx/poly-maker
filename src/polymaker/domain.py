"""Core domain types shared across polymaker.

These are plain, immutable-ish dataclasses and enums with no I/O. Everything the
strategy, execution, and state layers speak is defined here so the boundaries
between components are typed rather than dict-shaped (the v1 failure mode).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    """Order side. Values match the CLOB API's string form."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class Regime(str, Enum):
    """Per-market quoting regime (see the README)."""

    QUIET = "QUIET"  # farming posture: in-band, layered, full size
    TRENDING = "TRENDING"  # persistent one-sided flow: lean + widen + half size
    EVENT = "EVENT"  # sweep/jump detected: pull quotes, cool off
    REDUCE_ONLY = "REDUCE_ONLY"  # inventory cap / end-date: exit quotes only
    HALTED = "HALTED"  # stale data / resolved / kill switch: cancel all


class OrderState(str, Enum):
    """Lifecycle of one of our orders."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    LIVE = "LIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    DONE = "DONE"


class TradeState(str, Enum):
    """Lifecycle of an on-chain match, mirroring the user-WS status ladder."""

    MATCHED = "MATCHED"
    MINED = "MINED"
    CONFIRMED = "CONFIRMED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"


# ── Market metadata ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TokenMeta:
    token_id: str
    outcome: str  # e.g. "Yes" / "No" / candidate name


@dataclass(frozen=True, slots=True)
class MarketMeta:
    """Static-ish metadata for a tradable market, sourced from Gamma/CLOB."""

    condition_id: str
    question: str
    slug: str
    tokens: tuple[TokenMeta, TokenMeta]
    tick_size: float
    neg_risk: bool
    min_order_size: float  # exchange minimum order size (shares)
    # liquidity-rewards params
    rewards_min_size: float
    rewards_max_spread: float  # in cents (e.g. 3.0 == 3c band)
    rewards_daily_rate: float
    # fees
    maker_fee_bps: int
    taker_fee_bps: int
    fees_enabled: bool
    # lifecycle / grouping
    end_date_iso: str | None
    event_id: str | None  # neg-risk event group; siblings share this
    # fraction of taker fees rebated to makers (V2 maker rebates)
    rebate_rate: float = 0.0
    # market-data references (may be stale; not authoritative for quoting)
    best_bid: float = 0.0
    best_ask: float = 0.0
    liquidity_num: float = 0.0
    volume_num: float = 0.0  # lifetime
    volume_24hr: float = 0.0  # trailing 24h CLOB volume (drives rebate estimate)

    @property
    def yes(self) -> TokenMeta:
        return self.tokens[0]

    @property
    def no(self) -> TokenMeta:
        return self.tokens[1]

    def other_token(self, token_id: str) -> str:
        a, b = self.tokens
        return b.token_id if token_id == a.token_id else a.token_id

    @property
    def price_decimals(self) -> int:
        """Number of decimal places implied by the tick size."""
        s = f"{self.tick_size:f}".rstrip("0")
        return len(s.split(".")[1]) if "." in s else 0


# ── Live trading state ─────────────────────────────────────────────────────


@dataclass(slots=True)
class Position:
    token_id: str
    size: float = 0.0  # signed shares held (long only in practice; >= 0)
    avg_price: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.size <= 0.0


@dataclass(slots=True)
class OpenOrder:
    """One of our resting orders as we currently believe it exists."""

    order_id: str
    token_id: str
    side: Side
    price: float
    size: float  # remaining (original - matched)
    state: OrderState = OrderState.LIVE
    created_ts: float = field(default_factory=time.time)

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True, slots=True)
class Fill:
    token_id: str
    side: Side
    price: float
    size: float
    trade_id: str
    ts: float = field(default_factory=time.time)
    is_maker: bool = True


# ── Strategy output ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Quote:
    """One intended resting order the strategy wants live."""

    token_id: str
    side: Side
    price: float
    size: float

    def key(self, price_decimals: int) -> tuple[str, Side, float]:
        """Identity used to match against live orders (side + rounded price)."""
        return (self.token_id, self.side, round(self.price, price_decimals))


@dataclass(frozen=True, slots=True)
class TargetQuotes:
    """The full desired resting-order set for a market at a point in time."""

    condition_id: str
    regime: Regime
    quotes: tuple[Quote, ...] = ()

    @property
    def is_empty(self) -> bool:
        return len(self.quotes) == 0
