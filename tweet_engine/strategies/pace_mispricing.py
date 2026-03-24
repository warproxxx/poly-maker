from datetime import timedelta

from tweet_engine.models import QuoteEvent, Signal
from tweet_tracker.pace_calculator import bucket_probability, calculate_pace


class PaceMispricingStrategy:
    strategy_name = "pace_mispricing"

    def __init__(
        self,
        trade_size=10,
        min_edge=0.05,
        exit_edge=0.02,
        overdispersion_factor=1.8,
        model_probability_fn=None,
    ):
        self.trade_size = trade_size
        self.min_edge = min_edge
        self.exit_edge = exit_edge
        self.overdispersion_factor = overdispersion_factor
        self.model_probability_fn = model_probability_fn

    def on_event(self, event, state):
        if not isinstance(event, QuoteEvent):
            return []

        metadata = state.get_metadata(event.condition_id)
        if metadata is None:
            return []

        current_position = state.get_position(event.condition_id).size
        model_probability = self._get_model_probability(event, metadata, state)
        if model_probability is None:
            return []

        time_to_expiry = metadata.period_end - event.timestamp
        edge = model_probability - event.ask

        if current_position > 0:
            if edge <= self.exit_edge or time_to_expiry <= timedelta(hours=2):
                return [
                    Signal(
                        timestamp=event.timestamp,
                        strategy_name=self.strategy_name,
                        condition_id=event.condition_id,
                        market_slug=event.market_slug,
                        series_id=event.series_id,
                        side="SELL",
                        size=current_position,
                        limit_price=event.bid,
                        reason="pace_exit",
                    )
                ]
            return []

        if time_to_expiry <= timedelta(hours=2):
            return []

        if edge >= self.min_edge:
            return [
                Signal(
                    timestamp=event.timestamp,
                    strategy_name=self.strategy_name,
                    condition_id=event.condition_id,
                    market_slug=event.market_slug,
                    series_id=event.series_id,
                    side="BUY",
                    size=self.trade_size,
                    limit_price=event.ask,
                    reason="pace_edge",
                )
            ]

        return []

    def _get_model_probability(self, event, metadata, state):
        if self.model_probability_fn is not None:
            return self.model_probability_fn(event, metadata, state)

        pace_result = calculate_pace(
            current_count=state.current_count,
            period_start=metadata.period_start,
            period_end=metadata.period_end,
            now=event.timestamp,
            bucket_size=metadata.bucket_high - metadata.bucket_low + 1,
        )
        if pace_result is None:
            return None

        sigma = max(pace_result.sigma * self.overdispersion_factor, metadata.tick_size)
        return bucket_probability(
            metadata.bucket_low,
            metadata.bucket_high,
            pace_result.projected_total,
            sigma,
        )
