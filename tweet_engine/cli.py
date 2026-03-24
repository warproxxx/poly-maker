import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tweet_engine.data_sources import PolymarketTweetMarketAdapter, market_frame_to_metadata
from tweet_engine.normalization import from_records
from tweet_engine.recorder import RawEventRecorder
from tweet_engine.services import HistoricalBackfillService, ReplayService
from tweet_engine.strategies.adjacent_bucket_arb import AdjacentBucketArbitrageStrategy
from tweet_engine.strategies.pace_mispricing import PaceMispricingStrategy


def build_parser():
    parser = argparse.ArgumentParser(prog="tweet_engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record_tweet_markets")
    record_parser.add_argument("--output", required=True)

    backfill_parser = subparsers.add_parser("backfill_tweet_window")
    backfill_parser.add_argument("--market", required=True)
    backfill_parser.add_argument("--output", required=True)

    replay_parser = subparsers.add_parser("replay_tweet_strategies")
    replay_parser.add_argument("--input", required=True)
    replay_parser.add_argument("--output", required=True)

    return parser


def run_record_tweet_markets(args, market_adapter=None, recorder=None):
    market_adapter = market_adapter or PolymarketTweetMarketAdapter()
    recorder = recorder or RawEventRecorder(Path(args.output))

    markets = market_adapter.discover_markets()
    metadata_events = market_frame_to_metadata(
        markets,
        observed_at=datetime.now(timezone.utc),
    )
    recorder.record_many(metadata_events)
    return {
        "command": args.command,
        "output": args.output,
        "recorded": len(metadata_events),
    }


def run_backfill_tweet_window(args, market_adapter=None, backfill_service=None):
    market_adapter = market_adapter or PolymarketTweetMarketAdapter()
    backfill_service = backfill_service or HistoricalBackfillService()
    markets = market_adapter.discover_markets()
    metadata_events = [
        event
        for event in market_frame_to_metadata(markets, observed_at=datetime.now(timezone.utc))
        if event.market_slug == args.market
    ]

    records = backfill_service.build_dataset(metadata_events=metadata_events)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return {
        "command": args.command,
        "market": args.market,
        "output": args.output,
        "records": len(records),
    }


def run_replay_tweet_strategies(args):
    input_path = Path(args.input)
    records = []
    if input_path.exists():
        lines = [line for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        records = [json.loads(line) for line in lines]

    events = from_records(records) if records else []
    service = ReplayService()
    summary = service.run(
        events=events,
        strategies=[PaceMispricingStrategy(), AdjacentBucketArbitrageStrategy()],
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "leaderboard.json").write_text(
        json.dumps(summary["leaderboard"], indent=2),
        encoding="utf-8",
    )
    return {"command": args.command, "output": args.output, "leaderboard": summary["leaderboard"]}


def dispatch(args):
    handlers = {
        "record_tweet_markets": run_record_tweet_markets,
        "backfill_tweet_window": run_backfill_tweet_window,
        "replay_tweet_strategies": run_replay_tweet_strategies,
    }
    return handlers[args.command](args)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)
