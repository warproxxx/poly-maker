import os

TWEET_CONFIG = {
    # twitterapi.io
    "twitter_api_key": os.getenv("TWITTER_API_KEY", ""),
    "twitter_api_base": "https://api.twitterapi.io",
    "target_username": os.getenv("TARGET_USERNAME", "elonmusk"),
    "poll_interval": int(os.getenv("POLL_INTERVAL", "60")),
    # xTracker
    "xtracker_poll_interval": int(os.getenv("XTRACKER_INTERVAL", "120")),
    "xtracker_count_diff_alert": int(os.getenv("XTRACKER_DIFF_ALERT", "5")),
    # Market discovery
    "market_discovery_interval": int(os.getenv("MARKET_INTERVAL", "300")),
    # Logging
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    # Strategies (Phase B)
    "strategies": {
        "adjacent_bucket": {"enabled": False},
        "pace_market_making": {"enabled": False},
        "early_entry": {"enabled": False},
    },
    # Risk
    "risk": {
        "max_position_per_bucket": int(os.getenv("MAX_POS_PER_BUCKET", "50")),
        "max_event_exposure": int(os.getenv("MAX_EVENT_EXPOSURE", "200")),
        "rebalance_threshold_buckets": 2,
        "stale_data_timeout": int(os.getenv("STALE_TIMEOUT", "300")),
    },
    # Trading
    "dry_run": os.getenv("DRY_RUN", "true").lower() == "true",
    "trade_size": int(os.getenv("TRADE_SIZE", "10")),
    "min_size": int(os.getenv("MIN_SIZE", "5")),
    "tick_size": 0.01,
}
