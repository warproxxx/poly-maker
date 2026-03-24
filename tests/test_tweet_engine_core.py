from datetime import datetime, timedelta, timezone
from typing import Optional

from tweet_engine.models import (
    MarketMetadata,
    QuoteEvent,
    ReplayState,
    Signal,
    TweetCountEvent,
)
from tweet_engine.normalization import sort_events
from tweet_engine.replay import ReplayRunner
from tweet_engine.simulator import ConservativeFillSimulator
from tweet_engine.strategies.adjacent_bucket_arb import AdjacentBucketArbitrageStrategy
from tweet_engine.strategies.pace_mispricing import PaceMispricingStrategy


def utc(hour: int, minute: int = 0) -> datetime:
    base = datetime(2026, 3, 24, tzinfo=timezone.utc)
    return base + timedelta(hours=hour, minutes=minute)


def make_metadata(
    condition_id: str = "cond-1",
    bucket_low: int = 120,
    bucket_high: int = 139,
    series_id: str = "series-a",
) -> MarketMetadata:
    return MarketMetadata(
        timestamp=utc(0),
        condition_id=condition_id,
        market_slug=f"elon-{bucket_low}-{bucket_high}",
        series_id=series_id,
        bucket_low=bucket_low,
        bucket_high=bucket_high,
        yes_token_id=f"yes-{condition_id}",
        no_token_id=f"no-{condition_id}",
        period_start=utc(0),
        period_end=utc(24),
        tick_size=0.01,
    )


def make_quote(
    condition_id: str = "cond-1",
    bucket_low: int = 120,
    bucket_high: int = 139,
    bid: float = 0.21,
    ask: float = 0.24,
    bid_size: float = 25,
    ask_size: float = 25,
    ts: Optional[datetime] = None,
) -> QuoteEvent:
    return QuoteEvent(
        timestamp=ts or utc(10),
        condition_id=condition_id,
        market_slug=f"elon-{bucket_low}-{bucket_high}",
        series_id="series-a",
        bucket_low=bucket_low,
        bucket_high=bucket_high,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
    )


def test_sort_events_orders_by_time_then_priority():
    quote = make_quote(ts=utc(10, 1))
    tweet = TweetCountEvent(timestamp=utc(10, 1), current_count=101)
    metadata = make_metadata()

    ordered = sort_events([quote, tweet, metadata])

    assert ordered == [metadata, tweet, quote]


def test_conservative_simulator_buys_at_ask_and_caps_to_visible_size():
    metadata = make_metadata()
    quote = make_quote(ask=0.31, ask_size=4)
    state = ReplayState()
    state.apply_event(metadata)
    state.apply_event(quote)

    signal = Signal(
        timestamp=quote.timestamp,
        strategy_name="pace",
        condition_id=quote.condition_id,
        market_slug=quote.market_slug,
        series_id=quote.series_id,
        side="BUY",
        size=10,
        limit_price=0.35,
        reason="edge",
    )

    simulator = ConservativeFillSimulator()
    fill = simulator.execute_signal(signal, state)

    assert fill.status == "filled"
    assert fill.size == 4
    assert fill.price == 0.31
    assert state.positions[quote.condition_id].size == 4


def test_pace_strategy_emits_buy_signal_when_model_edge_is_large_enough():
    metadata = make_metadata()
    quote = make_quote(ask=0.22, bid=0.19)
    state = ReplayState()
    state.apply_event(metadata)
    state.apply_event(TweetCountEvent(timestamp=utc(10), current_count=100))
    state.apply_event(quote)

    strategy = PaceMispricingStrategy(
        trade_size=7,
        min_edge=0.05,
        model_probability_fn=lambda *_args, **_kwargs: 0.31,
    )

    signals = strategy.on_event(quote, state)

    assert len(signals) == 1
    assert signals[0].side == "BUY"
    assert signals[0].size == 7
    assert signals[0].condition_id == quote.condition_id


def test_adjacent_bucket_strategy_emits_buy_signals_for_underpriced_strip():
    buckets = [
        (make_metadata("cond-a", 100, 119), make_quote("cond-a", 100, 119, ask=0.09, bid=0.07)),
        (make_metadata("cond-b", 120, 139), make_quote("cond-b", 120, 139, ask=0.11, bid=0.09)),
        (make_metadata("cond-c", 140, 159), make_quote("cond-c", 140, 159, ask=0.10, bid=0.08)),
    ]

    state = ReplayState()
    for metadata, quote in buckets:
        state.apply_event(metadata)
        state.apply_event(quote)

    strategy = AdjacentBucketArbitrageStrategy(
        trade_size=3,
        max_legs=3,
        min_edge=0.05,
        strip_probability_fn=lambda strip, *_args, **_kwargs: 0.20 if len(strip) == 2 else 0.45,
    )

    signals = strategy.on_event(buckets[1][1], state)

    assert len(signals) == 3
    assert {signal.condition_id for signal in signals} == {"cond-a", "cond-b", "cond-c"}
    assert all(signal.side == "BUY" for signal in signals)


def test_replay_runner_generates_fill_and_metrics_from_sorted_events():
    metadata = make_metadata()
    quote = make_quote(ask=0.18, bid=0.16, ask_size=5)
    tweet = TweetCountEvent(timestamp=utc(12), current_count=130)

    runner = ReplayRunner(
        strategies=[
            PaceMispricingStrategy(
                trade_size=6,
                min_edge=0.05,
                model_probability_fn=lambda *_args, **_kwargs: 0.27,
            )
        ],
        simulator=ConservativeFillSimulator(),
    )

    result = runner.run([quote, tweet, metadata])

    assert result.total_signals == 1
    assert result.total_fills == 1
    assert result.fill_rate == 1.0
    assert result.positions["cond-1"].size == 5
