from tweet_engine.normalization import to_records
from tweet_engine.replay import ReplayRunner
from tweet_engine.reporting import build_leaderboard


class HistoricalBackfillService:
    def build_dataset(
        self,
        metadata_events=None,
        tweet_events=None,
        quote_events=None,
        trade_events=None,
    ):
        events = []
        for group in (metadata_events, tweet_events, quote_events, trade_events):
            if group:
                events.extend(group)
        return to_records(events)


class ReplayService:
    def __init__(self, simulator=None):
        self.simulator = simulator

    def run(self, events, strategies):
        runs = []

        for strategy in strategies:
            runner = ReplayRunner(strategies=[strategy], simulator=self.simulator)
            result = runner.run(events)
            strategy_name = getattr(strategy, "strategy_name", strategy.__class__.__name__)
            runs.append(
                {
                    "strategy_name": strategy_name,
                    "result": result,
                    "metrics": {
                        "strategy_name": strategy_name,
                        "realized_pnl": result.realized_pnl,
                        "fill_rate": result.fill_rate,
                        "total_signals": result.total_signals,
                        "total_fills": result.total_fills,
                    },
                }
            )

        leaderboard = build_leaderboard([run["metrics"] for run in runs])
        summary = {"runs": runs, "leaderboard": leaderboard}
        if len(runs) == 1:
            summary["result"] = runs[0]["result"]
        return summary
