"""Tests for tweet_tracker.tweet_state module."""

from datetime import datetime, timezone


def test_initial_state():
    """All state variables should have default values."""
    import tweet_tracker.tweet_state as ts
    ts.reset()

    assert ts.current_count == 0
    assert ts.period_start is None
    assert ts.period_end is None
    assert ts.count_history == []
    assert ts.projected_total == 0
    assert ts.pace_tweets_per_hour == 0.0
    assert ts.tweets_cache == []


def test_reset():
    """reset() should restore all state to defaults."""
    import tweet_tracker.tweet_state as ts

    ts.current_count = 500
    ts.projected_total = 700
    ts.pace_tweets_per_hour = 4.5
    ts.count_history = [(datetime.now(timezone.utc), 500)]

    ts.reset()

    assert ts.current_count == 0
    assert ts.projected_total == 0
    assert ts.pace_tweets_per_hour == 0.0
    assert ts.count_history == []


def test_state_mutation_thread_safe():
    """State mutations under lock should work correctly."""
    import tweet_tracker.tweet_state as ts
    ts.reset()

    with ts.lock:
        ts.current_count = 42
        ts.pace_tweets_per_hour = 3.14

    assert ts.current_count == 42
    assert ts.pace_tweets_per_hour == 3.14
    ts.reset()
