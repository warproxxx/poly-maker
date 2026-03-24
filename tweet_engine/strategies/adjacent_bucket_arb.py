from tweet_engine.models import QuoteEvent, Signal
from tweet_tracker.pace_calculator import bucket_probability, calculate_pace


class AdjacentBucketArbitrageStrategy:
    strategy_name = "adjacent_bucket_arb"

    def __init__(
        self,
        trade_size=5,
        max_legs=7,
        min_edge=0.05,
        overdispersion_factor=1.8,
        strip_probability_fn=None,
    ):
        self.trade_size = trade_size
        self.max_legs = max_legs
        self.min_edge = min_edge
        self.overdispersion_factor = overdispersion_factor
        self.strip_probability_fn = strip_probability_fn

    def on_event(self, event, state):
        if not isinstance(event, QuoteEvent):
            return []

        candidates = self._series_quotes(event.series_id, state)
        if len(candidates) < 2:
            return []

        best_strip = None
        best_edge = None

        for start_idx in range(len(candidates)):
            for end_idx in range(start_idx + 1, min(len(candidates), start_idx + self.max_legs)):
                strip = candidates[start_idx : end_idx + 1]
                if event.condition_id not in [quote.condition_id for _, quote in strip]:
                    continue

                cost = sum(quote.ask for _, quote in strip)
                probability = self._get_strip_probability(strip, state)
                edge = probability - cost

                if edge >= self.min_edge and (best_edge is None or edge > best_edge):
                    best_strip = strip
                    best_edge = edge

        if best_strip is None:
            return []

        signals = []
        for _metadata, quote in best_strip:
            signals.append(
                Signal(
                    timestamp=event.timestamp,
                    strategy_name=self.strategy_name,
                    condition_id=quote.condition_id,
                    market_slug=quote.market_slug,
                    series_id=quote.series_id,
                    side="BUY",
                    size=self.trade_size,
                    limit_price=quote.ask,
                    reason="strip_edge",
                )
            )
        return signals

    def _series_quotes(self, series_id, state):
        selected = []
        for condition_id, metadata in state.metadata.items():
            if metadata.series_id != series_id:
                continue
            quote = state.get_quote(condition_id)
            if quote is None:
                continue
            selected.append((metadata, quote))
        selected.sort(key=lambda pair: pair[0].bucket_low)
        return selected

    def _get_strip_probability(self, strip, state):
        if self.strip_probability_fn is not None:
            return self.strip_probability_fn(strip, state)

        metadata = strip[0][0]
        event = strip[0][1]
        pace_result = calculate_pace(
            current_count=state.current_count,
            period_start=metadata.period_start,
            period_end=metadata.period_end,
            now=event.timestamp,
            bucket_size=metadata.bucket_high - metadata.bucket_low + 1,
        )
        if pace_result is None:
            return 0.0

        sigma = max(pace_result.sigma * self.overdispersion_factor, metadata.tick_size)
        probability = 0.0
        for bucket_metadata, _quote in strip:
            probability += bucket_probability(
                bucket_metadata.bucket_low,
                bucket_metadata.bucket_high,
                pace_result.projected_total,
                sigma,
            )
        return probability
