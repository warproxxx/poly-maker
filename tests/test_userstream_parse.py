"""Tests for user-WS normalization (maker fill extraction + order tracking).

Frames modeled on v1's observed shape; reconfirm field names in the wallet spike.
"""

from __future__ import annotations

from polymaker.domain import Side, TradeState
from polymaker.userstream.parse import normalize_order, normalize_trade

OUR = "0xMyWallet"


def _other(token: str) -> str | None:
    return {"yes-tok": "no-tok", "no-tok": "yes-tok"}.get(token)


def test_maker_same_outcome_is_a_sell():
    # taker BUYs YES; we are the maker on YES -> we SELL YES
    msg = {
        "event_type": "trade",
        "market": "0xcond",
        "asset_id": "yes-tok",
        "side": "BUY",
        "outcome": "Yes",
        "status": "MATCHED",
        "id": "trade1",
        "timestamp": "1700000000000",
        "maker_orders": [
            {"maker_address": OUR, "matched_amount": "50", "price": "0.49", "outcome": "Yes"}
        ],
    }
    evs = normalize_trade(msg, OUR, _other)
    assert len(evs) == 1
    ev = evs[0]
    assert ev.token_id == "yes-tok"
    assert ev.our_side is Side.SELL
    assert ev.size == 50 and ev.price == 0.49
    assert ev.status is TradeState.MATCHED


def test_maker_different_outcome_is_a_mint_buy():
    # taker BUYs YES; we are the maker on NO -> a mint: we BUY NO
    msg = {
        "event_type": "trade",
        "market": "0xcond",
        "asset_id": "yes-tok",
        "side": "BUY",
        "outcome": "Yes",
        "status": "MATCHED",
        "id": "trade2",
        "timestamp": "1700000000000",
        "maker_orders": [
            {"maker_address": OUR, "matched_amount": "30", "price": "0.51", "outcome": "No"}
        ],
    }
    evs = normalize_trade(msg, OUR, _other)
    assert len(evs) == 1
    assert evs[0].token_id == "no-tok"
    assert evs[0].our_side is Side.BUY
    assert evs[0].size == 30


def test_ignores_maker_orders_that_are_not_ours():
    msg = {
        "event_type": "trade", "market": "0xcond", "asset_id": "yes-tok", "side": "BUY",
        "outcome": "Yes", "status": "MATCHED", "id": "t", "timestamp": "1700000000000",
        "maker_orders": [
            {"maker_address": "0xSomeoneElse", "matched_amount": "50", "price": "0.49", "outcome": "Yes"}
        ],
    }
    assert normalize_trade(msg, OUR, _other) == []


def test_normalize_order_remaining_and_cancel():
    ev = normalize_order({
        "event_type": "order", "asset_id": "yes-tok", "side": "BUY", "price": "0.49",
        "original_size": "100", "size_matched": "40", "status": "LIVE", "id": "o1",
    })
    assert ev is not None
    assert ev.remaining_size == 60
    assert ev.is_cancel is False

    cancel = normalize_order({
        "event_type": "order", "asset_id": "yes-tok", "side": "BUY", "price": "0.49",
        "original_size": "100", "size_matched": "0", "status": "CANCELED", "id": "o1",
    })
    assert cancel is not None and cancel.is_cancel is True
