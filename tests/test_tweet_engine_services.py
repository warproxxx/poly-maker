from datetime import datetime, timezone

from tweet_engine.data_sources import PolymarketTweetMarketAdapter
from tweet_engine.models import MarketMetadata, QuoteEvent, TweetCountEvent
from tweet_engine.services import HistoricalBackfillService, ReplayService
from tweet_engine.strategies.pace_mispricing import PaceMispricingStrategy


def ts(hour: int) -> datetime:
    return datetime(2026, 3, 24, hour, tzinfo=timezone.utc)


def make_metadata():
    return MarketMetadata(
        timestamp=ts(0),
        condition_id="cond-1",
        market_slug="elon-100-119",
        series_id="series-a",
        bucket_low=100,
        bucket_high=119,
        yes_token_id="yes-1",
        no_token_id="no-1",
        period_start=ts(0),
        period_end=datetime(2026, 3, 25, tzinfo=timezone.utc),
        tick_size=0.01,
    )


def make_quote():
    return QuoteEvent(
        timestamp=ts(12),
        condition_id="cond-1",
        market_slug="elon-100-119",
        series_id="series-a",
        bucket_low=100,
        bucket_high=119,
        bid=0.18,
        ask=0.22,
        bid_size=20,
        ask_size=20,
    )


def test_polymarket_adapter_reuses_existing_discovery_function(monkeypatch):
    calls = {}

    def fake_discover(client):
        calls["client"] = client
        return ["ok"]

    class FakeWrapper:
        client = "raw-client"

    monkeypatch.setattr("tweet_engine.data_sources.discover_tweet_markets", fake_discover)

    adapter = PolymarketTweetMarketAdapter(FakeWrapper())
    result = adapter.discover_markets()

    assert result == ["ok"]
    assert calls["client"] == "raw-client"


def test_backfill_service_builds_sorted_records():
    service = HistoricalBackfillService()

    records = service.build_dataset(
        metadata_events=[make_metadata()],
        tweet_events=[TweetCountEvent(timestamp=ts(11), current_count=105)],
        quote_events=[make_quote()],
    )

    assert [record["event_type"] for record in records] == ["metadata", "tweet_count", "quote"]


def test_replay_service_returns_summary_with_leaderboard():
    strategy = PaceMispricingStrategy(
        trade_size=4,
        min_edge=0.05,
        model_probability_fn=lambda *_args, **_kwargs: 0.30,
    )
    service = ReplayService()

    summary = service.run(
        events=[make_quote(), TweetCountEvent(timestamp=ts(11), current_count=105), make_metadata()],
        strategies=[strategy],
    )

    assert summary["result"].total_fills == 1
    assert summary["leaderboard"][0]["strategy_name"] == "pace_mispricing"


def test_replay_service_scores_strategies_independently():
    aggressive = PaceMispricingStrategy(
        trade_size=4,
        min_edge=0.05,
        model_probability_fn=lambda *_args, **_kwargs: 0.30,
    )
    conservative = PaceMispricingStrategy(
        trade_size=4,
        min_edge=0.05,
        model_probability_fn=lambda *_args, **_kwargs: 0.10,
    )
    service = ReplayService()

    summary = service.run(
        events=[make_quote(), TweetCountEvent(timestamp=ts(11), current_count=105), make_metadata()],
        strategies=[aggressive, conservative],
    )

    assert len(summary["runs"]) == 2
    assert summary["runs"][0]["result"].total_signals == 1
    assert summary["runs"][1]["result"].total_signals == 0
    assert len(summary["leaderboard"]) == 2
