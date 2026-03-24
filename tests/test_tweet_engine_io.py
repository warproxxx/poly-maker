import json
from datetime import datetime, timezone

import pandas as pd

from tweet_engine.cli import build_parser, dispatch, run_record_tweet_markets
from tweet_engine.models import MarketMetadata, QuoteEvent
from tweet_engine.normalization import from_records, to_records
from tweet_engine.recorder import RawEventRecorder
from tweet_engine.reporting import build_leaderboard


def make_metadata():
    return MarketMetadata(
        timestamp=datetime(2026, 3, 24, tzinfo=timezone.utc),
        condition_id="cond-1",
        market_slug="elon-100-119",
        series_id="series-a",
        bucket_low=100,
        bucket_high=119,
        yes_token_id="yes-1",
        no_token_id="no-1",
        period_start=datetime(2026, 3, 24, tzinfo=timezone.utc),
        period_end=datetime(2026, 3, 25, tzinfo=timezone.utc),
    )


def make_quote():
    return QuoteEvent(
        timestamp=datetime(2026, 3, 24, 12, tzinfo=timezone.utc),
        condition_id="cond-1",
        market_slug="elon-100-119",
        series_id="series-a",
        bucket_low=100,
        bucket_high=119,
        bid=0.2,
        ask=0.25,
        bid_size=30,
        ask_size=40,
    )


def test_to_records_serializes_event_type_and_core_fields():
    records = to_records([make_quote()])

    assert records[0]["event_type"] == "quote"
    assert records[0]["condition_id"] == "cond-1"
    assert records[0]["ask"] == 0.25


def test_records_round_trip_back_to_event_objects():
    quote = make_quote()

    restored = from_records(to_records([quote]))

    assert restored == [quote]


def test_raw_event_recorder_writes_ndjson(tmp_path):
    recorder = RawEventRecorder(tmp_path / "events.ndjson")
    recorder.record_many([make_quote()])

    payload = (tmp_path / "events.ndjson").read_text().strip().splitlines()

    assert len(payload) == 1
    written = json.loads(payload[0])
    assert written["event_type"] == "quote"
    assert written["market_slug"] == "elon-100-119"


def test_leaderboard_sorts_results_by_realized_pnl_descending():
    leaderboard = build_leaderboard(
        [
            {"strategy_name": "pace", "realized_pnl": 1.2, "fill_rate": 0.5},
            {"strategy_name": "arb", "realized_pnl": 2.5, "fill_rate": 0.8},
        ]
    )

    assert [entry["strategy_name"] for entry in leaderboard] == ["arb", "pace"]


def test_cli_parser_supports_record_backfill_and_replay_commands():
    parser = build_parser()

    record_args = parser.parse_args(["record_tweet_markets", "--output", "data/raw.ndjson"])
    backfill_args = parser.parse_args(
        ["backfill_tweet_window", "--market", "elon-100-119", "--output", "data/backfill.json"]
    )
    replay_args = parser.parse_args(
        ["replay_tweet_strategies", "--input", "data/events.ndjson", "--output", "data/results"]
    )

    assert record_args.command == "record_tweet_markets"
    assert backfill_args.command == "backfill_tweet_window"
    assert replay_args.command == "replay_tweet_strategies"


def test_cli_dispatch_routes_to_selected_handler(monkeypatch):
    parser = build_parser()
    args = parser.parse_args(["record_tweet_markets", "--output", "data/raw.ndjson"])
    calls = []

    def fake_handler(parsed_args):
        calls.append(parsed_args.command)
        return {"command": parsed_args.command}

    monkeypatch.setattr("tweet_engine.cli.run_record_tweet_markets", fake_handler)

    result = dispatch(args)

    assert result == {"command": "record_tweet_markets"}
    assert calls == ["record_tweet_markets"]


def test_record_command_writes_market_metadata_snapshot(tmp_path):
    parser = build_parser()
    args = parser.parse_args(["record_tweet_markets", "--output", str(tmp_path / "raw.ndjson")])

    class FakeAdapter:
        def discover_markets(self):
            return pd.DataFrame(
                [
                    {
                        "condition_id": "cond-1",
                        "market_slug": "elon-100-119",
                        "bucket_low": 100,
                        "bucket_high": 119,
                        "token1": "yes-1",
                        "token2": "no-1",
                        "end_date": "2026-03-25T00:00:00+00:00",
                        "tick_size": 0.01,
                    }
                ]
            )

    result = run_record_tweet_markets(args, market_adapter=FakeAdapter())

    lines = (tmp_path / "raw.ndjson").read_text().splitlines()
    payload = json.loads(lines[0])

    assert result["recorded"] == 1
    assert payload["event_type"] == "metadata"
    assert payload["condition_id"] == "cond-1"
