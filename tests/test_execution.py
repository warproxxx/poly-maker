"""Tests for the rate budgeter and the paper-mode gateway."""

from __future__ import annotations

import asyncio
import time

import pytest

from polymaker.config import Config
from polymaker.domain import Quote, Side
from polymaker.execution.gateway import ExecutionGateway, _tick_str
from polymaker.execution.ratelimit import TokenBucket


def test_tick_str_formats():
    assert _tick_str(0.01) == "0.01"
    assert _tick_str(0.001) == "0.001"
    assert _tick_str(0.0025) == "0.0025"
    assert _tick_str(0.1) == "0.1"


async def test_token_bucket_limits_rate():
    bucket = TokenBucket(rate_per_s=100.0, burst=5.0)
    start = time.monotonic()
    # burst of 5 is instant; the next 5 must wait ~ (5/100)s = 50ms
    for _ in range(10):
        await bucket.acquire(1)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04  # had to wait for refill


async def test_token_bucket_pressure_rises_when_drained():
    bucket = TokenBucket(rate_per_s=10.0, burst=10.0)
    assert bucket.pressure == pytest.approx(0.0, abs=0.01)
    for _ in range(10):
        await bucket.acquire(1)
    assert bucket.pressure > 0.8


async def test_paper_gateway_places_and_cancels_without_wallet(meta):
    cfg = Config()  # defaults, no secrets
    gw = ExecutionGateway(cfg, paper=True)
    quotes = [
        Quote(meta.yes.token_id, Side.BUY, 0.49, 100),
        Quote(meta.no.token_id, Side.BUY, 0.48, 100),
    ]
    placed = await gw.place(quotes, meta)
    assert len(placed) == 2
    assert all(o.order_id.startswith("paper-") for o in placed)
    # cancel is a no-op in paper mode but must not raise
    await gw.cancel([o.order_id for o in placed])
    assert await gw.open_orders() == []


async def test_paper_gateway_heartbeat_and_cancel_all_noop():
    gw = ExecutionGateway(Config(), paper=True)
    await gw.heartbeat("hb1")
    await gw.cancel_all()  # no client, must not raise


def test_gateway_requires_wallet_for_live_connect():
    from polymaker.config import Secrets

    # explicitly-empty secrets (don't read a real .env that may exist on disk)
    cfg = Config(secrets=Secrets(_env_file=None))
    gw = ExecutionGateway(cfg, paper=False)
    with pytest.raises(RuntimeError, match="no wallet"):
        asyncio.run(gw.connect())
