"""Entry point for the Elon tweet count trading bot.

Usage:
    python main_tweets.py

Requires TWITTER_API_KEY in .env file.
"""

import gc
import time
import asyncio
import threading
import traceback

from dotenv import load_dotenv

load_dotenv()

from tweet_tracker.logger import logger
from tweet_tracker.config import TWEET_CONFIG
from tweet_tracker.twitter_client import TwitterAPIClient
from tweet_tracker.tweet_counter import TweetCounter
from tweet_tracker.xtracker_client import XTrackerClient
from tweet_tracker.pace_calculator import calculate_pace, update_state_with_pace
from tweet_tracker.market_discovery import (
    discover_tweet_markets,
    get_active_period,
    load_markets_to_global_state,
)
import tweet_tracker.tweet_state as tweet_state

from poly_data.polymarket_client import PolymarketClient
from poly_data.data_utils import update_positions, update_orders
from poly_data.websocket_handlers import connect_market_websocket, connect_user_websocket
import poly_data.global_state as global_state

from tweet_trading import perform_tweet_trade


def setup_data_sources():
    """Initialize Twitter API client, tweet counter, and xTracker."""
    twitter_client = TwitterAPIClient(api_key=TWEET_CONFIG["twitter_api_key"])
    xtracker_client = XTrackerClient()

    logger.info(f"Twitter API client initialized for @{TWEET_CONFIG['target_username']}")
    return twitter_client, xtracker_client


def discover_and_setup_markets():
    """Discover tweet markets and set up the tracking period."""
    df = discover_tweet_markets(global_state.client.client)

    if df.empty:
        logger.error("No tweet markets found. Exiting.")
        return None, None

    period = get_active_period(df)
    if period is None:
        logger.error("Cannot determine market period. Exiting.")
        return None, None

    load_markets_to_global_state(df)
    logger.info(f"Market period: {period[0]} to {period[1]}")
    return df, period


def tweet_polling_loop(counter: TweetCounter, xtracker: XTrackerClient):
    """Background thread: polls tweets and validates against xTracker."""
    poll_interval = TWEET_CONFIG["poll_interval"]
    xt_interval = TWEET_CONFIG["xtracker_poll_interval"]
    username = TWEET_CONFIG["target_username"]

    last_xt_check = 0

    logger.info(
        f"Tweet polling started: interval={poll_interval}s, "
        f"xTracker check every {xt_interval}s"
    )

    while True:
        try:
            # Poll for new tweets
            count = counter.poll_and_update(username=username)

            # Calculate pace
            if tweet_state.period_start and tweet_state.period_end:
                pace_result = calculate_pace(
                    current_count=count,
                    period_start=tweet_state.period_start,
                    period_end=tweet_state.period_end,
                )
                update_state_with_pace(pace_result)

                if pace_result:
                    logger.info(
                        f"Count={count}, pace={pace_result.pace_per_hour:.1f}/h, "
                        f"projected={pace_result.projected_total}, "
                        f"bucket=[{pace_result.center_bucket_low}-{pace_result.center_bucket_high}]"
                    )

            # xTracker validation at longer intervals
            now = time.time()
            if now - last_xt_check >= xt_interval:
                xtracker.validate_count(count, username=username)
                last_xt_check = now

        except Exception:
            logger.error("Error in tweet polling loop", exc_info=True)

        time.sleep(poll_interval)


def position_update_loop():
    """Background thread: periodically updates positions and orders."""
    while True:
        try:
            update_positions(avgOnly=True)
            update_orders()
        except Exception:
            logger.error("Error updating positions/orders", exc_info=True)
        time.sleep(5)


def market_discovery_loop():
    """Background thread: periodically re-discovers markets."""
    interval = TWEET_CONFIG["market_discovery_interval"]
    while True:
        time.sleep(interval)
        try:
            df = discover_tweet_markets(global_state.client.client)
            if not df.empty:
                load_markets_to_global_state(df)
        except Exception:
            logger.error("Error in market discovery loop", exc_info=True)


async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Elon Tweet Trading Bot starting...")
    logger.info(f"DRY_RUN={TWEET_CONFIG['dry_run']}")
    logger.info("=" * 60)

    # 1. Initialize Polymarket client
    global_state.client = PolymarketClient()
    logger.info("Polymarket client initialized")

    # 2. Initialize data sources
    twitter_client, xtracker_client = setup_data_sources()

    # 3. Discover tweet markets
    df, period = discover_and_setup_markets()
    if df is None:
        return

    # 4. Set up tweet counter
    tweet_state.period_start = period[0]
    tweet_state.period_end = period[1]
    counter = TweetCounter(twitter_client, period[0], period[1])

    # 5. Initial full sync
    logger.info("Running initial tweet sync...")
    counter.full_sync(username=TWEET_CONFIG["target_username"])
    logger.info(f"Initial count: {counter.get_count()}")

    # 6. Set trade function
    global_state.trade_function = perform_tweet_trade

    # 7. Start background threads
    threading.Thread(
        target=tweet_polling_loop,
        args=(counter, xtracker_client),
        daemon=True,
        name="tweet-poller",
    ).start()

    threading.Thread(
        target=position_update_loop,
        daemon=True,
        name="position-updater",
    ).start()

    threading.Thread(
        target=market_discovery_loop,
        daemon=True,
        name="market-discovery",
    ).start()

    # 8. WebSocket main loop
    update_positions()
    update_orders()

    while True:
        try:
            logger.info(
                f"Connecting WebSocket for {len(global_state.all_tokens)} tokens..."
            )
            await asyncio.gather(
                connect_market_websocket(global_state.all_tokens),
                connect_user_websocket(),
            )
            logger.info("WebSocket disconnected, reconnecting...")
        except Exception:
            logger.error("WebSocket error", exc_info=True)

        await asyncio.sleep(1)
        gc.collect()


if __name__ == "__main__":
    asyncio.run(main())
