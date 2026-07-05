"""Tests for market-WS parsing and the book service routing."""

from __future__ import annotations

from polymaker.domain import Side
from polymaker.marketdata.parse import (
    parse_book,
    parse_last_trade,
    parse_price_changes,
    parse_tick_size_change,
)
from polymaker.marketdata.service import MarketDataService

# frames modeled on live captures (2026-07-05)
BOOK = {
    "event_type": "book",
    "market": "0xcond",
    "asset_id": "yes-tok",
    "timestamp": "1783270000000",
    "hash": "abc123",
    "tick_size": "0.01",
    "bids": [{"price": "0.48", "size": "100"}, {"price": "0.49", "size": "200"}],
    "asks": [{"price": "0.52", "size": "150"}, {"price": "0.51", "size": "80"}],
}
PRICE_CHANGE = {
    "event_type": "price_change",
    "market": "0xcond",
    "timestamp": "1783270001000",
    "price_changes": [
        {"asset_id": "yes-tok", "price": "0.49", "size": "0", "side": "BUY", "hash": "h"},
        {"asset_id": "yes-tok", "price": "0.50", "size": "300", "side": "BUY", "hash": "h"},
    ],
}
LAST_TRADE = {
    "event_type": "last_trade_price",
    "market": "0xcond",
    "asset_id": "yes-tok",
    "price": "0.50",
    "size": "42",
    "side": "BUY",
    "timestamp": "1783270002000",
}


def test_parse_book_converts_ms_and_levels():
    upd = parse_book(BOOK)
    assert upd is not None
    assert upd.asset_id == "yes-tok"
    assert upd.condition_id == "0xcond"
    assert (0.49, 200) in upd.bids
    assert upd.ts == 1783270000.0  # ms -> s
    assert upd.tick_size == 0.01


def test_parse_price_changes():
    changes = parse_price_changes(PRICE_CHANGE)
    assert len(changes) == 2
    assert changes[0].side is Side.BUY
    assert changes[1].price == 0.50 and changes[1].size == 300


def test_parse_last_trade_aggressor():
    tp = parse_last_trade(LAST_TRADE)
    assert tp is not None
    assert tp.aggressor is Side.BUY
    assert tp.size == 42


def test_parse_tick_size_change():
    tc = parse_tick_size_change(
        {"event_type": "tick_size_change", "asset_id": "yes-tok", "new_tick_size": "0.001"}
    )
    assert tc is not None and tc.tick_size == 0.001


def test_service_routes_book_and_wakes_quoter():
    woken: list[tuple[str, str]] = []
    svc = MarketDataService(on_dirty=lambda c, t: woken.append((c, t)))
    svc.set_markets([("0xcond", ["yes-tok", "no-tok"])])
    svc._dispatch(BOOK)
    book = svc.book("yes-tok")
    assert book is not None
    assert book.best_bid().price == 0.49
    assert book.best_ask().price == 0.51
    assert woken == [("0xcond", "yes-tok")]


def test_service_applies_price_change_delta():
    svc = MarketDataService()
    svc.set_markets([("0xcond", ["yes-tok"])])
    svc._dispatch(BOOK)
    svc._dispatch(PRICE_CHANGE)  # removes 0.49 bid, adds 0.50 bid
    book = svc.book("yes-tok")
    assert book.best_bid().price == 0.50
    assert 0.49 not in book.bids


def test_service_ignores_unsubscribed_asset():
    svc = MarketDataService()
    svc.set_markets([("0xcond", ["yes-tok"])])
    svc._dispatch({**BOOK, "asset_id": "stranger"})
    assert svc.book("stranger") is None


def test_service_forwards_trades_for_flow():
    trades = []
    svc = MarketDataService(on_trade=trades.append)
    svc.set_markets([("0xcond", ["yes-tok"])])
    svc._dispatch(LAST_TRADE)
    assert len(trades) == 1 and trades[0].aggressor is Side.BUY
