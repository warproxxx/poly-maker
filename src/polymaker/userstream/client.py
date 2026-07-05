"""UserStream: authenticated user WS for our order/trade lifecycle events.

Subscribes with L2 creds and the condition_ids we trade; routes fills and order
updates into the StateStore via the UserEventProcessor. Reconnects with backoff.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import websockets

from polymaker.journal import Journal
from polymaker.logging import get_logger
from polymaker.state.tracker import UserEventProcessor
from polymaker.userstream.parse import normalize_order, normalize_trade

log = get_logger("userstream.client")


class UserStream:
    def __init__(
        self,
        creds: Any,
        our_address: str,
        processor: UserEventProcessor,
        *,
        other_token: Callable[[str], str | None],
        condition_of_token: Callable[[str], str | None],
        url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/user",
        journal: Journal | None = None,
        proxy: str | None = None,
    ) -> None:
        self._creds = creds
        self._address = our_address
        self._proc = processor
        self._other_token = other_token
        self._condition_of_token = condition_of_token
        self._url = url
        self._journal = journal
        self._proxy = proxy
        self._markets: list[str] = []
        self._stop = asyncio.Event()

    def set_markets(self, condition_ids: list[str]) -> None:
        self._markets = condition_ids

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_and_listen()
                backoff = 1.0
            except (websockets.ConnectionClosed, OSError) as exc:
                log.warning("user_ws_dropped", err=str(exc))
            except Exception as exc:  # noqa: BLE001
                log.error("user_ws_error", err=str(exc))
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _connect_and_listen(self) -> None:
        sub = {
            "type": "user",
            "auth": {
                "apiKey": self._creds.api_key,
                "secret": self._creds.api_secret,
                "passphrase": self._creds.api_passphrase,
            },
            "markets": self._markets,
        }
        kwargs: dict[str, Any] = {"ping_interval": 5, "ping_timeout": None}
        if self._proxy:
            kwargs["proxy"] = self._proxy
        async with websockets.connect(self._url, **kwargs) as ws:
            await ws.send(json.dumps(sub))
            log.info("user_ws_subscribed", markets=len(self._markets))
            async for raw in ws:
                self._handle(raw)

    def stop(self) -> None:
        self._stop.set()

    def _handle(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        for msg in data if isinstance(data, list) else [data]:
            if not isinstance(msg, dict):
                continue
            et = msg.get("event_type")
            if et == "trade":
                self._on_trade(msg)
            elif et == "order":
                self._on_order(msg)

    def _on_trade(self, msg: dict[str, Any]) -> None:
        self._journal_write("user_trade", msg)
        for ev in normalize_trade(msg, self._address, self._other_token):
            cond = self._condition_of_token(ev.token_id) or str(msg.get("market", ""))
            self._proc.on_trade(ev, cond)

    def _on_order(self, msg: dict[str, Any]) -> None:
        self._journal_write("user_order", msg)
        ev = normalize_order(msg)
        if ev is not None:
            cond = self._condition_of_token(ev.token_id) or str(msg.get("market", ""))
            self._proc.on_order(ev, cond)

    def _journal_write(self, kind: str, payload: dict[str, Any]) -> None:
        if self._journal is not None:
            self._journal.write(kind, payload, _ts(payload))


def _ts(msg: dict[str, Any]) -> float:
    raw = msg.get("timestamp")
    try:
        v = float(raw)  # type: ignore[arg-type]
        return v / 1000.0 if v > 1e12 else v
    except (ValueError, TypeError):
        return 0.0
