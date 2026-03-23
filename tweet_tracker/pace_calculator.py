"""Pace calculator for predicting final tweet count.

Uses current tweet pace to project the total count at period end,
with confidence intervals based on Poisson/Normal approximation.
"""

import math
from typing import Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

from tweet_tracker.logger import logger
import tweet_tracker.tweet_state as tweet_state


@dataclass
class PaceResult:
    current_count: int
    hours_elapsed: float
    hours_remaining: float
    pace_per_hour: float
    projected_total: int
    sigma: float
    ci_low: int  # 95% CI lower bound
    ci_high: int  # 95% CI upper bound
    center_bucket_low: int  # predicted bucket lower bound
    center_bucket_high: int  # predicted bucket upper bound


def calculate_pace(
    current_count: int,
    period_start: datetime,
    period_end: datetime,
    now: datetime = None,
    bucket_size: int = 20,
) -> Optional[PaceResult]:
    """Calculate tweet pace and project final count.

    Args:
        current_count: Tweets counted so far
        period_start: Start of the counting period (UTC)
        period_end: End of the counting period (UTC)
        now: Current time (defaults to utcnow)
        bucket_size: Width of each market bucket (default 20)

    Returns:
        PaceResult with projections, or None if insufficient data
    """
    if now is None:
        now = datetime.now(timezone.utc)

    total_hours = (period_end - period_start).total_seconds() / 3600
    elapsed_hours = (now - period_start).total_seconds() / 3600
    remaining_hours = (period_end - now).total_seconds() / 3600

    if elapsed_hours <= 0 or total_hours <= 0:
        return None

    # Clamp: if past period_end, remaining = 0
    remaining_hours = max(0, remaining_hours)

    pace = current_count / elapsed_hours
    projected = current_count + pace * remaining_hours

    # Standard deviation using Poisson approximation for remaining tweets
    # Var(remaining) ≈ pace * remaining_hours
    sigma = math.sqrt(pace * remaining_hours) if pace > 0 and remaining_hours > 0 else 0

    # 95% confidence interval (±1.96σ)
    ci_low = max(0, int(projected - 1.96 * sigma))
    ci_high = int(projected + 1.96 * sigma)

    # Center bucket
    bucket_low = int(projected // bucket_size) * bucket_size
    bucket_high = bucket_low + bucket_size - 1

    result = PaceResult(
        current_count=current_count,
        hours_elapsed=round(elapsed_hours, 2),
        hours_remaining=round(remaining_hours, 2),
        pace_per_hour=round(pace, 2),
        projected_total=int(projected),
        sigma=round(sigma, 2),
        ci_low=ci_low,
        ci_high=ci_high,
        center_bucket_low=bucket_low,
        center_bucket_high=bucket_high,
    )

    logger.debug(
        f"Pace: {pace:.2f}/h, projected: {int(projected)}, "
        f"σ={sigma:.1f}, CI=[{ci_low}, {ci_high}], "
        f"bucket: [{bucket_low}-{bucket_high}]"
    )

    return result


def update_state_with_pace(pace_result: PaceResult):
    """Write pace calculation results to global tweet_state."""
    if pace_result is None:
        return

    with tweet_state.lock:
        tweet_state.projected_total = pace_result.projected_total
        tweet_state.pace_tweets_per_hour = pace_result.pace_per_hour
        tweet_state.center_bucket_index = pace_result.center_bucket_low

        tweet_state.count_history.append(
            (datetime.now(timezone.utc), pace_result.current_count)
        )

        # Keep only last 1000 data points
        if len(tweet_state.count_history) > 1000:
            tweet_state.count_history = tweet_state.count_history[-1000:]


def find_bucket_for_count(count: int, bucket_size: int = 20) -> Tuple[int, int]:
    """Return (low, high) for the bucket containing count."""
    low = int(count // bucket_size) * bucket_size
    return low, low + bucket_size - 1


def bucket_probability(
    bucket_low: int,
    bucket_high: int,
    projected_total: float,
    sigma: float,
) -> float:
    """Calculate probability that final count falls in [bucket_low, bucket_high].

    Uses normal CDF approximation (valid when projected_total > ~30).
    """
    if sigma <= 0:
        # No uncertainty: probability is 1 if projected is in bucket, else 0
        return 1.0 if bucket_low <= projected_total <= bucket_high else 0.0

    def _norm_cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    z_low = (bucket_low - 0.5 - projected_total) / sigma
    z_high = (bucket_high + 0.5 - projected_total) / sigma

    return _norm_cdf(z_high) - _norm_cdf(z_low)
