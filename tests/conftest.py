"""Shared test fixtures."""

from __future__ import annotations

import pytest

from polymaker.config import StrategyProfile
from polymaker.domain import MarketMeta, TokenMeta
from polymaker.marketdata.orderbook import BookView


@pytest.fixture
def meta() -> MarketMeta:
    return MarketMeta(
        condition_id="0xcond",
        question="Will X happen?",
        slug="will-x-happen",
        tokens=(TokenMeta("yes-token", "Yes"), TokenMeta("no-token", "No")),
        tick_size=0.01,
        neg_risk=False,
        min_order_size=5.0,
        rewards_min_size=10.0,
        rewards_max_spread=3.0,  # 3 cents
        rewards_daily_rate=50.0,
        maker_fee_bps=0,
        taker_fee_bps=100,
        fees_enabled=True,
        end_date_iso="2028-11-07T00:00:00Z",
        event_id="evt-1",
    )


@pytest.fixture
def profile() -> StrategyProfile:
    return StrategyProfile()  # defaults


def view(bb: float | None, ba: float | None, bb_sz: float = 500, ba_sz: float = 500) -> BookView:
    """Construct a BookView for a token with a symmetric deep book."""
    return BookView(
        best_bid=bb,
        best_bid_size=bb_sz,
        best_ask=ba,
        best_ask_size=ba_sz,
        second_bid=(bb - 0.01) if bb else None,
        second_ask=(ba + 0.01) if ba else None,
        bid_depth=bb_sz,
        ask_depth=ba_sz,
    )
