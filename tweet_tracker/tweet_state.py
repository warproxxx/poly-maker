"""Global mutable state for tweet tracking.

All modules read/write these variables to share tweet data and predictions.
"""
import threading

# Current tweet count for the active period
current_count = 0

# Period boundaries (datetime objects, UTC)
period_start = None
period_end = None

# Historical count snapshots: [(timestamp, count), ...]
count_history = []

# Pace prediction results
projected_total = 0
center_bucket_index = None
pace_tweets_per_hour = 0.0

# Last successful data update time (datetime)
last_update_time = None

# Cached tweet objects for the current period (for precise counting)
tweets_cache = []

# Thread lock for state mutations
lock = threading.Lock()


def reset():
    """Reset all state to defaults. Useful for tests and period transitions."""
    global current_count, period_start, period_end, count_history
    global projected_total, center_bucket_index, pace_tweets_per_hour
    global last_update_time, tweets_cache

    with lock:
        current_count = 0
        period_start = None
        period_end = None
        count_history = []
        projected_total = 0
        center_bucket_index = None
        pace_tweets_per_hour = 0.0
        last_update_time = None
        tweets_cache = []
