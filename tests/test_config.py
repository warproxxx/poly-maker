"""Tests for tweet_tracker.config module."""

import os
import importlib


def test_default_config_values():
    """Config should have sensible defaults when no env vars set."""
    # Clear relevant env vars
    env_vars = [
        "TWITTER_API_KEY", "TARGET_USERNAME", "POLL_INTERVAL",
        "XTRACKER_INTERVAL", "MARKET_INTERVAL", "LOG_LEVEL",
        "DRY_RUN", "TRADE_SIZE", "MIN_SIZE",
    ]
    saved = {k: os.environ.pop(k, None) for k in env_vars}

    try:
        import tweet_tracker.config
        importlib.reload(tweet_tracker.config)
        cfg = tweet_tracker.config.TWEET_CONFIG

        assert cfg["target_username"] == "elonmusk"
        assert cfg["poll_interval"] == 60
        assert cfg["xtracker_poll_interval"] == 120
        assert cfg["market_discovery_interval"] == 300
        assert cfg["dry_run"] is True
        assert cfg["trade_size"] == 10
        assert cfg["tick_size"] == 0.01
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_config_reads_env_vars():
    """Config should respect environment variable overrides."""
    os.environ["POLL_INTERVAL"] = "30"
    os.environ["DRY_RUN"] = "false"
    os.environ["TRADE_SIZE"] = "25"

    try:
        import tweet_tracker.config
        importlib.reload(tweet_tracker.config)
        cfg = tweet_tracker.config.TWEET_CONFIG

        assert cfg["poll_interval"] == 30
        assert cfg["dry_run"] is False
        assert cfg["trade_size"] == 25
    finally:
        del os.environ["POLL_INTERVAL"]
        del os.environ["DRY_RUN"]
        del os.environ["TRADE_SIZE"]


def test_config_strategies_disabled_by_default():
    """All strategies should be disabled by default in Phase A."""
    from tweet_tracker.config import TWEET_CONFIG

    for name, strategy_cfg in TWEET_CONFIG["strategies"].items():
        assert strategy_cfg["enabled"] is False, f"Strategy {name} should be disabled"
