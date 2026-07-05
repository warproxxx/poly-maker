"""Unit tests for the order book and its analytics."""

from __future__ import annotations

import pytest

from polymaker.domain import Side
from polymaker.marketdata.orderbook import OrderBook, to_no_price


def make_book() -> OrderBook:
    ob = OrderBook(tick_size=0.01)
    ob.apply_snapshot(
        bids=[(0.40, 100), (0.41, 200), (0.42, 50)],  # best bid 0.42
        asks=[(0.45, 80), (0.46, 150), (0.44, 30)],  # best ask 0.44
        ts=1.0,
    )
    return ob


def test_best_bid_ask():
    ob = make_book()
    assert ob.best_bid().price == 0.42
    assert ob.best_bid().size == 50
    assert ob.best_ask().price == 0.44
    assert ob.best_ask().size == 30


def test_apply_delta_add_and_remove():
    ob = make_book()
    ob.apply_delta(Side.BUY, 0.43, 25, ts=2.0)
    assert ob.best_bid().price == 0.43
    ob.apply_delta(Side.BUY, 0.43, 0, ts=3.0)  # size 0 removes the level
    assert ob.best_bid().price == 0.42
    assert ob.last_update_ts == 3.0


def test_empty_book_views_are_none():
    ob = OrderBook()
    assert ob.best_bid() is None
    assert ob.best_ask() is None
    assert ob.microprice() is None
    assert ob.is_empty
    v = ob.view()
    assert v.mid is None
    assert v.spread is None
    assert v.imbalance == 0.0


def test_microprice_pulls_toward_thin_side():
    ob = OrderBook(tick_size=0.01)
    # bid side much heavier than ask side -> microprice near the ask
    ob.apply_snapshot(bids=[(0.40, 1000)], asks=[(0.42, 10)], ts=1.0)
    mp = ob.microprice(levels=1)
    assert mp is not None
    assert 0.41 < mp <= 0.42  # dragged up toward the thin ask
    # symmetric sizes -> mid
    ob.apply_snapshot(bids=[(0.40, 100)], asks=[(0.42, 100)], ts=2.0)
    assert ob.microprice(levels=1) == pytest.approx(0.41)


def test_best_with_min_size_skips_dust():
    ob = OrderBook(tick_size=0.01)
    # a dust order (size 1) sits at the touch; real size is one level back
    ob.apply_snapshot(bids=[(0.42, 1), (0.41, 500)], asks=[(0.44, 1), (0.45, 500)], ts=1.0)
    price, size, top = ob.best_with_min_size(Side.BUY, min_size=5)
    assert price == 0.41 and size == 500
    assert top == 0.42  # the dust touch is still reported as top
    price, size, top = ob.best_with_min_size(Side.SELL, min_size=5)
    assert price == 0.45 and size == 500
    assert top == 0.44


def test_depth_within_band():
    ob = make_book()
    # bids at 0.40,0.41,0.42 all within [0.40, 0.42]
    assert ob.depth_within(Side.BUY, 0.40, 0.42) == 350
    assert ob.depth_within(Side.BUY, 0.415, 0.42) == 50


def test_view_second_levels_and_imbalance():
    ob = make_book()
    v = ob.view(min_size=0.0)
    assert v.best_bid == 0.42
    assert v.second_bid == 0.41
    assert v.best_ask == 0.44
    assert v.second_ask == 0.45
    assert -1.0 <= v.imbalance <= 1.0


def test_no_price_mirror():
    assert to_no_price(0.42) == pytest.approx(0.58)
    assert to_no_price(0.0) == 1.0
    assert to_no_price(1.0) == 0.0
