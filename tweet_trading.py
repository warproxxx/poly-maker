"""Tweet trading orchestrator — selects strategy and executes trades.

This module is the bridge between tweet data (tweet_tracker) and
the Polymarket trading layer (trading.py / poly_data).

Strategies are defined in tweet_tracker/strategies/ (Phase B).
"""

import asyncio
from tweet_tracker.logger import logger
from tweet_tracker.config import TWEET_CONFIG
import tweet_tracker.tweet_state as tweet_state
import poly_data.global_state as global_state


async def perform_tweet_trade(market: str):
    """Main trade decision function, called on each order book update.

    This replaces the default `perform_trade` for tweet markets.
    Strategy implementations will be added in Phase B.
    """
    if TWEET_CONFIG["dry_run"]:
        logger.debug(f"[DRY_RUN] Trade signal for market {market}")
        return

    # Phase B: Strategy selection and execution
    # 1. Get current pace prediction from tweet_state
    # 2. Select strategy based on market conditions
    # 3. Generate and execute orders
    logger.debug(f"perform_tweet_trade called for {market} (strategies not yet implemented)")
