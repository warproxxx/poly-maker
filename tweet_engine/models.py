from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MarketMetadata:
    timestamp: datetime
    condition_id: str
    market_slug: str
    series_id: str
    bucket_low: int
    bucket_high: int
    yes_token_id: str
    no_token_id: str
    period_start: datetime
    period_end: datetime
    tick_size: float = 0.01
    event_type: str = field(init=False, default="metadata")


@dataclass(frozen=True)
class TweetCountEvent:
    timestamp: datetime
    current_count: int
    event_type: str = field(init=False, default="tweet_count")


@dataclass(frozen=True)
class QuoteEvent:
    timestamp: datetime
    condition_id: str
    market_slug: str
    series_id: str
    bucket_low: int
    bucket_high: int
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    event_type: str = field(init=False, default="quote")


@dataclass(frozen=True)
class TradeEvent:
    timestamp: datetime
    condition_id: str
    market_slug: str
    series_id: str
    side: str
    price: float
    size: float
    event_type: str = field(init=False, default="trade")


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    strategy_name: str
    condition_id: str
    market_slug: str
    series_id: str
    side: str
    size: float
    limit_price: float
    reason: str
    signal_id: Optional[str] = None


@dataclass
class Position:
    size: float = 0.0
    avg_price: float = 0.0


@dataclass(frozen=True)
class SimulatedFill:
    timestamp: datetime
    strategy_name: str
    condition_id: str
    side: str
    size: float
    price: float
    status: str
    signal_id: Optional[str] = None
    reason: str = ""


@dataclass
class BacktestResult:
    total_signals: int
    total_fills: int
    fill_rate: float
    positions: Dict[str, Position]
    fills: List[SimulatedFill]
    signals: List[Signal]
    realized_pnl: float = 0.0


@dataclass
class ReplayState:
    metadata: Dict[str, MarketMetadata] = field(default_factory=dict)
    quotes: Dict[str, QuoteEvent] = field(default_factory=dict)
    positions: Dict[str, Position] = field(default_factory=dict)
    current_count: int = 0
    last_timestamp: Optional[datetime] = None
    fills: List[SimulatedFill] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    realized_pnl: float = 0.0

    def apply_event(self, event) -> None:
        self.last_timestamp = getattr(event, "timestamp", self.last_timestamp)

        if isinstance(event, MarketMetadata):
            self.metadata[event.condition_id] = event
        elif isinstance(event, QuoteEvent):
            self.quotes[event.condition_id] = event
        elif isinstance(event, TweetCountEvent):
            self.current_count = event.current_count

    def get_metadata(self, condition_id: str) -> Optional[MarketMetadata]:
        return self.metadata.get(condition_id)

    def get_quote(self, condition_id: str) -> Optional[QuoteEvent]:
        return self.quotes.get(condition_id)

    def get_position(self, condition_id: str) -> Position:
        if condition_id not in self.positions:
            self.positions[condition_id] = Position()
        return self.positions[condition_id]


EVENT_TYPE_TO_CLASS = {
    "metadata": MarketMetadata,
    "tweet_count": TweetCountEvent,
    "quote": QuoteEvent,
    "trade": TradeEvent,
}
