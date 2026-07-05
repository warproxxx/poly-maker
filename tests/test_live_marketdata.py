"""Live integration test for the market WS (network-gated).

Run explicitly with:  POLYMAKER_LIVE=1 uv run pytest tests/test_live_marketdata.py
Skipped by default so the unit suite stays offline and fast.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest
import websockets

pytestmark = pytest.mark.skipif(
    os.environ.get("POLYMAKER_LIVE") != "1", reason="live test; set POLYMAKER_LIVE=1"
)


async def _top_political_tokens() -> tuple[str, list[str]]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 1, "closed": "false", "tag_id": 2,
                    "order": "volume24hr", "ascending": "false"},
        )
        m = r.json()[0]
        return m["conditionId"], json.loads(m["clobTokenIds"])


async def test_market_service_builds_a_live_book():
    from polymaker.marketdata.service import MarketDataService

    cond, tokens = await _top_political_tokens()
    woken: list[tuple[str, str]] = []
    svc = MarketDataService(on_dirty=lambda c, t: woken.append((c, t)))
    svc.set_markets([(cond, tokens)])

    task = asyncio.create_task(svc.run())
    try:
        # wait until at least one token has a two-sided book
        for _ in range(60):
            await asyncio.sleep(0.5)
            if any(not svc.book(t).is_empty for t in tokens):
                break
    finally:
        svc.stop()
        task.cancel()

    assert woken, "quoter was never woken by a book event"
    live = [t for t in tokens if not svc.book(t).is_empty]
    assert live, "no book was populated from the live feed"
    book = svc.book(live[0])
    assert book.best_bid() is not None and book.best_ask() is not None
    assert book.best_bid().price < book.best_ask().price


async def test_live_market_ws_raw_frames():
    """Sanity check the wire format our parser targets hasn't drifted."""
    _, tokens = await _top_political_tokens()
    uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    async with websockets.connect(uri, ping_interval=5, ping_timeout=None) as ws:
        await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
        got_book = False
        for _ in range(10):
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw)
            for msg in data if isinstance(data, list) else [data]:
                if msg.get("event_type") == "book":
                    assert {"asset_id", "bids", "asks", "hash"} <= set(msg)
                    got_book = True
        assert got_book
