"""Tests for tweet_tracker.market_discovery module."""

import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import MagicMock
from tweet_tracker.market_discovery import (
    is_tweet_market,
    parse_bucket_range,
    discover_tweet_markets,
    get_active_period,
    load_markets_to_global_state,
)
import poly_data.global_state as global_state


@pytest.fixture(autouse=True)
def reset_global_state():
    global_state.all_tokens = []
    global_state.REVERSE_TOKENS = {}
    global_state.df = None
    yield


class TestIsTweetMarket:
    def test_matches_tweet_market(self):
        assert is_tweet_market("How many tweets will Elon Musk post?") is True

    def test_matches_post_market(self):
        assert is_tweet_market("Elon Musk posts: how many this week?") is True

    def test_no_match_generic(self):
        assert is_tweet_market("Will Bitcoin reach $100K?") is False

    def test_no_match_elon_without_tweet(self):
        assert is_tweet_market("Will Elon Musk buy a company?") is False

    def test_case_insensitive(self):
        assert is_tweet_market("ELON MUSK TWEET count") is True


class TestParseBucketRange:
    def test_standard_range(self):
        assert parse_bucket_range("200-219") == (200, 219)

    def test_range_in_question(self):
        assert parse_bucket_range("Elon Musk tweets: 400-419?") == (400, 419)

    def test_plus_range(self):
        assert parse_bucket_range("740+") == (740, 99999)

    def test_plus_in_question(self):
        assert parse_bucket_range("Will there be 800+ tweets?") == (800, 99999)

    def test_no_range(self):
        assert parse_bucket_range("How many tweets?") is None

    def test_range_with_spaces(self):
        assert parse_bucket_range("200 - 219") == (200, 219)


class TestDiscoverTweetMarkets:
    def test_discovers_markets(self):
        mock_client = MagicMock()
        mock_client.get_sampling_markets.return_value = {
            "data": [
                {
                    "question": "Elon Musk tweets: 200-219?",
                    "tokens": [
                        {"token_id": "token_yes_1", "outcome": "Yes"},
                        {"token_id": "token_no_1", "outcome": "No"},
                    ],
                    "condition_id": "cond_1",
                    "neg_risk": True,
                    "minimum_tick_size": 0.01,
                    "end_date_iso": "2026-03-24T00:00:00Z",
                    "market_slug": "elon-tweets-200-219",
                    "rewards": {"min_size": 5},
                },
                {
                    "question": "Will Bitcoin hit $100K?",
                    "tokens": [
                        {"token_id": "btc_yes", "outcome": "Yes"},
                        {"token_id": "btc_no", "outcome": "No"},
                    ],
                    "condition_id": "cond_btc",
                    "neg_risk": False,
                    "minimum_tick_size": 0.01,
                    "end_date_iso": "2026-04-01T00:00:00Z",
                    "market_slug": "bitcoin-100k",
                    "rewards": {"min_size": 10},
                },
            ],
            "next_cursor": None,
        }

        mock_book = MagicMock()
        mock_book.bids = [{"price": "0.10", "size": "100"}]
        mock_book.asks = [{"price": "0.15", "size": "50"}]
        mock_client.get_order_book.return_value = mock_book

        df = discover_tweet_markets(mock_client)

        assert len(df) == 1  # only tweet market
        assert df.iloc[0]["bucket_low"] == 200
        assert df.iloc[0]["bucket_high"] == 219
        assert df.iloc[0]["token1"] == "token_yes_1"

    def test_empty_when_no_markets(self):
        mock_client = MagicMock()
        mock_client.get_sampling_markets.return_value = {
            "data": [],
            "next_cursor": None,
        }

        df = discover_tweet_markets(mock_client)
        assert df.empty

    def test_handles_api_error(self):
        mock_client = MagicMock()
        mock_client.get_sampling_markets.side_effect = Exception("API error")

        df = discover_tweet_markets(mock_client)
        assert df.empty


class TestGetActivePeriod:
    def test_extracts_period(self):
        df = pd.DataFrame({
            "end_date": ["2026-03-24T00:00:00Z", "2026-03-24T00:00:00Z"],
        })
        result = get_active_period(df)
        assert result is not None
        start, end = result
        assert end.day == 24
        assert start.day == 17  # 7 days before

    def test_empty_df(self):
        assert get_active_period(pd.DataFrame()) is None


class TestLoadMarketsToGlobalState:
    def test_loads_tokens(self):
        df = pd.DataFrame({
            "token1": ["t1", "t3"],
            "token2": ["t2", "t4"],
            "question": ["q1", "q2"],
        })
        load_markets_to_global_state(df)

        assert len(global_state.all_tokens) == 4
        assert global_state.REVERSE_TOKENS["t1"] == "t2"
        assert global_state.REVERSE_TOKENS["t2"] == "t1"

    def test_empty_df_noop(self):
        load_markets_to_global_state(pd.DataFrame())
        assert len(global_state.all_tokens) == 0
