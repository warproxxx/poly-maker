"""Discover and parse Elon tweet count markets on Polymarket.

Uses the CLOB API to find active tweet count markets and parse their
bucket structure (e.g., 0-19, 20-39, ..., 740+).
"""

import re
from typing import Optional, Tuple

import pandas as pd
from datetime import datetime, timezone

from tweet_tracker.logger import logger
import poly_data.global_state as global_state


# Pattern to match bucket ranges like "200-219" or "740+"
BUCKET_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
BUCKET_PLUS_RE = re.compile(r"(\d+)\+")

# Keywords to identify tweet count markets
TWEET_MARKET_KEYWORDS = ["elon", "musk", "tweet", "post"]


def is_tweet_market(question: str) -> bool:
    """Check if a market question is about Elon tweet counts."""
    q_lower = question.lower()
    return any(kw in q_lower for kw in TWEET_MARKET_KEYWORDS) and any(
        kw in q_lower for kw in ["tweet", "post", "how many"]
    )


def parse_bucket_range(question: str) -> Optional[Tuple[int, int]]:
    """Extract bucket range from market question text.

    Examples:
        "200-219" → (200, 219)
        "740+"    → (740, 99999)

    Returns None if no bucket range found.
    """
    match = BUCKET_RANGE_RE.search(question)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = BUCKET_PLUS_RE.search(question)
    if match:
        return int(match.group(1)), 99999

    return None


def discover_tweet_markets(client) -> pd.DataFrame:
    """Find all active Elon tweet count markets on Polymarket.

    Args:
        client: py_clob_client ClobClient instance

    Returns:
        DataFrame with columns:
            question, token1, token2, condition_id, neg_risk,
            tick_size, bucket_low, bucket_high, end_date,
            best_bid, best_ask, market_slug
    """
    logger.info("Discovering tweet count markets...")
    cursor = ""
    found_markets = []

    while True:
        try:
            markets = client.get_sampling_markets(next_cursor=cursor)
            if not markets or "data" not in markets:
                break

            for market in markets["data"]:
                question = market.get("question", "")
                if not is_tweet_market(question):
                    continue

                bucket = parse_bucket_range(question)
                if bucket is None:
                    continue

                tokens = market.get("tokens", [])
                if len(tokens) < 2:
                    continue

                token1 = tokens[0]["token_id"]
                token2 = tokens[1]["token_id"]

                entry = {
                    "question": question,
                    "token1": token1,
                    "token2": token2,
                    "condition_id": market.get("condition_id", ""),
                    "neg_risk": market.get("neg_risk", True),
                    "tick_size": market.get("minimum_tick_size", 0.01),
                    "bucket_low": bucket[0],
                    "bucket_high": bucket[1],
                    "end_date": market.get("end_date_iso", ""),
                    "market_slug": market.get("market_slug", ""),
                    "min_size": market.get("rewards", {}).get("min_size", 5),
                }

                # Fetch order book for pricing
                try:
                    book = client.get_order_book(token1)
                    bids = book.bids if book.bids else []
                    asks = book.asks if book.asks else []
                    entry["best_bid"] = float(bids[-1]["price"]) if bids else 0.0
                    entry["best_ask"] = float(asks[-1]["price"]) if asks else 0.0
                except Exception:
                    entry["best_bid"] = 0.0
                    entry["best_ask"] = 0.0

                found_markets.append(entry)
                logger.debug(f"Found bucket [{bucket[0]}-{bucket[1]}]: {question}")

            cursor = markets.get("next_cursor")
            if cursor is None:
                break

        except Exception as e:
            logger.error(f"Market discovery error: {e}", exc_info=True)
            break

    if not found_markets:
        logger.warning("No tweet count markets found")
        return pd.DataFrame()

    df = pd.DataFrame(found_markets)
    df = df.sort_values("bucket_low").reset_index(drop=True)
    logger.info(
        f"Discovered {len(df)} tweet buckets: "
        f"[{df['bucket_low'].min()}-{df['bucket_high'].max()}]"
    )
    return df


def get_active_period(df: pd.DataFrame) -> Optional[Tuple[datetime, datetime]]:
    """Extract the active market period from discovered markets.

    Returns (period_start, period_end) or None if no valid dates.
    """
    if df.empty or "end_date" not in df.columns:
        return None

    try:
        end_dates = pd.to_datetime(df["end_date"])
        period_end = end_dates.max()
        if pd.isna(period_end):
            return None
        # Tweet markets typically run for a week
        period_start = period_end - pd.Timedelta(days=7)
        return (
            period_start.to_pydatetime().replace(tzinfo=timezone.utc),
            period_end.to_pydatetime().replace(tzinfo=timezone.utc),
        )
    except Exception as e:
        logger.error(f"Cannot parse market period: {e}")
        return None


def load_markets_to_global_state(df: pd.DataFrame):
    """Load discovered tweet markets into global_state for trading."""
    if df.empty:
        return

    global_state.df = df

    all_tokens = []
    for _, row in df.iterrows():
        t1, t2 = row["token1"], row["token2"]
        all_tokens.extend([t1, t2])
        global_state.REVERSE_TOKENS[t1] = t2
        global_state.REVERSE_TOKENS[t2] = t1

    global_state.all_tokens = all_tokens
    logger.info(f"Loaded {len(df)} markets ({len(all_tokens)} tokens) into global state")
