"""Tests for tweet_tracker.pace_calculator module."""

import pytest
import math
from datetime import datetime, timezone, timedelta
from tweet_tracker.pace_calculator import (
    calculate_pace,
    find_bucket_for_count,
    bucket_probability,
    update_state_with_pace,
)
import tweet_tracker.tweet_state as tweet_state


@pytest.fixture(autouse=True)
def reset_state():
    tweet_state.reset()
    yield
    tweet_state.reset()


class TestCalculatePace:
    def test_basic_pace_calculation(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)  # 72h elapsed

        result = calculate_pace(300, start, end, now)

        assert result is not None
        assert result.current_count == 300
        assert result.hours_elapsed == 72.0
        assert result.hours_remaining == 96.0
        # pace = 300/72 ≈ 4.17/h
        assert abs(result.pace_per_hour - 4.17) < 0.1
        # projected = 300 + 4.17 * 96 ≈ 700
        assert abs(result.projected_total - 700) < 5

    def test_sigma_calculation(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now)

        # sigma = sqrt(pace * remaining) = sqrt(4.17 * 96) ≈ 20
        assert result.sigma > 15
        assert result.sigma < 25

    def test_confidence_interval(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now)

        assert result.ci_low < result.projected_total
        assert result.ci_high > result.projected_total
        assert result.ci_high - result.ci_low > 2 * result.sigma

    def test_center_bucket(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now)

        # projected ≈ 700, bucket should be 700-719 (or 680-699)
        assert result.center_bucket_low % 20 == 0
        assert result.center_bucket_high == result.center_bucket_low + 19

    def test_zero_elapsed_returns_none(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        result = calculate_pace(0, start, end, start)
        assert result is None

    def test_at_period_end(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(500, start, end, end)

        assert result.hours_remaining == 0
        assert result.projected_total == 500
        assert result.sigma == 0

    def test_past_period_end(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        past = end + timedelta(hours=2)

        result = calculate_pace(500, start, end, past)

        assert result.hours_remaining == 0
        assert result.projected_total == 500

    def test_custom_bucket_size(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now, bucket_size=50)

        assert result.center_bucket_low % 50 == 0
        assert result.center_bucket_high == result.center_bucket_low + 49


class TestFindBucketForCount:
    def test_exact_bucket_boundary(self):
        assert find_bucket_for_count(700) == (700, 719)

    def test_within_bucket(self):
        assert find_bucket_for_count(715) == (700, 719)

    def test_zero(self):
        assert find_bucket_for_count(0) == (0, 19)

    def test_large_count(self):
        assert find_bucket_for_count(999) == (980, 999)

    def test_custom_bucket_size(self):
        assert find_bucket_for_count(75, bucket_size=50) == (50, 99)


class TestBucketProbability:
    def test_center_bucket_highest_probability(self):
        p_center = bucket_probability(690, 709, 700.0, 20.0)
        p_adjacent = bucket_probability(710, 729, 700.0, 20.0)
        assert p_center > p_adjacent

    def test_probabilities_sum_to_approximately_one(self):
        """Probabilities across all buckets should sum close to 1."""
        projected = 700.0
        sigma = 20.0
        total = 0.0
        for low in range(0, 1400, 20):
            total += bucket_probability(low, low + 19, projected, sigma)
        assert abs(total - 1.0) < 0.01

    def test_zero_sigma(self):
        """With zero sigma, only the bucket containing projected has P=1."""
        assert bucket_probability(700, 719, 710.0, 0.0) == 1.0
        assert bucket_probability(680, 699, 710.0, 0.0) == 0.0

    def test_far_bucket_low_probability(self):
        p = bucket_probability(300, 319, 700.0, 20.0)
        assert p < 0.001

    def test_symmetric_buckets(self):
        """Equidistant buckets from center should have similar probabilities."""
        p_left = bucket_probability(680, 699, 700.0, 20.0)
        p_right = bucket_probability(700, 719, 700.0, 20.0)
        # Not exactly symmetric because projected=700 is at boundary
        # but should be in similar range
        assert abs(p_left - p_right) < 0.15


class TestUpdateStateWithPace:
    def test_updates_global_state(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now)
        update_state_with_pace(result)

        assert tweet_state.projected_total == result.projected_total
        assert tweet_state.pace_tweets_per_hour == result.pace_per_hour
        assert tweet_state.center_bucket_index == result.center_bucket_low
        assert len(tweet_state.count_history) == 1

    def test_none_result_no_crash(self):
        update_state_with_pace(None)
        assert tweet_state.projected_total == 0

    def test_history_capped_at_1000(self):
        start = datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)

        result = calculate_pace(300, start, end, now)

        # Add 1005 entries
        for _ in range(1005):
            update_state_with_pace(result)

        assert len(tweet_state.count_history) <= 1000
