from tweet_engine.models import BacktestResult, ReplayState
from tweet_engine.normalization import sort_events
from tweet_engine.simulator import ConservativeFillSimulator


class ReplayRunner:
    def __init__(self, strategies, simulator=None):
        self.strategies = strategies
        self.simulator = simulator or ConservativeFillSimulator()

    def run(self, events):
        state = ReplayState()
        ordered_events = sort_events(events)

        for event in ordered_events:
            state.apply_event(event)

            for strategy in self.strategies:
                signals = strategy.on_event(event, state)
                if not signals:
                    continue

                state.signals.extend(signals)
                for signal in signals:
                    self.simulator.execute_signal(signal, state)

        total_signals = len(state.signals)
        total_fills = len([fill for fill in state.fills if fill.status == "filled"])
        fill_rate = total_fills / total_signals if total_signals else 0.0

        return BacktestResult(
            total_signals=total_signals,
            total_fills=total_fills,
            fill_rate=fill_rate,
            positions=state.positions,
            fills=state.fills,
            signals=state.signals,
            realized_pnl=state.realized_pnl,
        )

