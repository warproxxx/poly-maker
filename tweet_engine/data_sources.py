from datetime import datetime, timedelta

from tweet_tracker.market_discovery import discover_tweet_markets
from tweet_tracker.tweet_counter import TweetCounter
from tweet_tracker.xtracker_client import XTrackerClient

from tweet_engine.models import MarketMetadata


class PolymarketTweetMarketAdapter:
    def __init__(self, market_client=None):
        if market_client is None:
            from poly_data.polymarket_client import PolymarketClient

            market_client = PolymarketClient()
        self.market_client = market_client

    def discover_markets(self):
        client = getattr(self.market_client, "client", self.market_client)
        return discover_tweet_markets(client)


class TweetSourceAdapter:
    def __init__(self, twitter_client=None, xtracker_client=None):
        self.twitter_client = twitter_client
        self.xtracker_client = xtracker_client or XTrackerClient()

    def build_counter(self, period_start, period_end):
        if self.twitter_client is None:
            from tweet_tracker.config import TWEET_CONFIG
            from tweet_tracker.twitter_client import TwitterAPIClient

            self.twitter_client = TwitterAPIClient(api_key=TWEET_CONFIG["twitter_api_key"])
        client = self.twitter_client
        return TweetCounter(client, period_start, period_end)


def market_frame_to_metadata(markets, observed_at=None):
    if markets is None:
        return []

    if hasattr(markets, "to_dict"):
        rows = markets.to_dict(orient="records")
    else:
        rows = list(markets)

    events = []
    for row in rows:
        period_end = _coerce_timestamp(row.get("end_date"), observed_at)
        period_start = period_end - timedelta(days=7)
        series_id = row.get("series_id") or f"{period_start.isoformat()}::{period_end.isoformat()}"
        events.append(
            MarketMetadata(
                timestamp=observed_at or period_start,
                condition_id=row["condition_id"],
                market_slug=row["market_slug"],
                series_id=series_id,
                bucket_low=int(row["bucket_low"]),
                bucket_high=int(row["bucket_high"]),
                yes_token_id=str(row["token1"]),
                no_token_id=str(row["token2"]),
                period_start=period_start,
                period_end=period_end,
                tick_size=float(row.get("tick_size", 0.01)),
            )
        )
    return events


def _coerce_timestamp(value, default):
    if value is None:
        if default is None:
            raise ValueError("Timestamp value is required when no default is provided")
        return default

    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()

    if hasattr(value, "tzinfo"):
        return value

    return datetime.fromisoformat(str(value))
