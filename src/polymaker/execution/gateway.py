"""ExecutionGateway: the only component that sends actions to the CLOB.

Wraps the synchronous py-clob-client-v2 (which owns the hard V2 EIP-712 signing,
pUSD balance adjustment, and tick/fee caching) and offloads its blocking network
calls to a thread pool so the asyncio hot path never stalls. Every quote goes out
**post-only** (the maker-only mandate, enforced at the exchange).

A `paper=True` gateway shares the same path but fabricates order ids instead of
posting — so paper mode exercises the full pipeline.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import asdict
from typing import Any

import httpx

from polymaker.config import Config
from polymaker.domain import MarketMeta, OpenOrder, OrderState, Quote, Side
from polymaker.execution.ratelimit import TokenBucket
from polymaker.journal import Journal
from polymaker.logging import get_logger

log = get_logger("execution.gateway")


def _tick_str(tick: float) -> str:
    return f"{tick:g}"


class ExecutionGateway:
    def __init__(
        self,
        cfg: Config,
        journal: Journal | None = None,
        *,
        paper: bool = False,
    ) -> None:
        self._cfg = cfg
        self._paper = paper
        self._journal = journal
        self._client: Any = None  # py_clob_client_v2.ClobClient
        self._creds: Any = None
        self._address: str = ""  # signer EOA
        self._funder: str = ""  # funds/positions live here (proxy/deposit wallet)
        self._data_host = cfg.wallet.data_api_host
        # rate budgets: fraction of documented POST/DELETE ceilings (per second)
        f = cfg.execution.rate_budget_fraction
        self._order_bucket = TokenBucket(rate_per_s=200.0 * f, burst=500.0 * f)
        self._cancel_bucket = TokenBucket(rate_per_s=200.0 * f, burst=500.0 * f)
        self._paper_ids = itertools.count(1)

    @property
    def paper(self) -> bool:
        return self._paper

    @property
    def creds(self) -> Any:
        return self._creds

    @property
    def address(self) -> str:
        """The signing EOA address."""
        return self._address

    @property
    def funder(self) -> str:
        """The address holding funds/positions (proxy/deposit wallet, or the EOA)."""
        return self._funder or self._address

    # ── lifecycle ───────────────────────────────────────────────────────
    async def connect(self) -> None:
        """Build the client and derive L2 API creds (network). No-op fields in paper."""
        sec = self._cfg.secrets
        if self._paper and not sec.has_wallet:
            # paper mode runs the full pipeline without a wallet (no orders posted)
            self._address = sec.browser_address or "0xPAPER"
            self._funder = sec.browser_address or self._address
            log.info("gateway_connected", address=self._address[:10], paper=True)
            return
        if not sec.has_wallet:
            raise RuntimeError("no wallet configured (set PK and BROWSER_ADDRESS in .env)")

        def _build() -> tuple[Any, Any, str]:
            from py_clob_client_v2.client import ClobClient

            client = ClobClient(
                host=self._cfg.wallet.clob_host,
                chain_id=self._cfg.wallet.chain_id,
                key=sec.pk,
                signature_type=self._cfg.wallet.signature_type,
                funder=sec.browser_address,
            )
            creds = client.create_or_derive_api_key()
            client.set_api_creds(creds)
            return client, creds, client.get_address()

        self._client, self._creds, self._address = await asyncio.to_thread(_build)
        # funds/positions live on the funder (proxy/deposit wallet); fall back to EOA
        self._funder = sec.browser_address or self._address
        log.info("gateway_connected", signer=self._address[:10], funder=self._funder[:10],
                 paper=self._paper)

    # ── placement ───────────────────────────────────────────────────────
    async def place(self, quotes: list[Quote], meta: MarketMeta) -> list[OpenOrder]:
        if not quotes:
            return []
        await self._order_bucket.acquire(len(quotes))
        ts = time.time()
        self._journal_write("orders_out", [asdict(q) for q in quotes], ts)

        if self._paper:
            return [self._paper_order(q) for q in quotes]

        def _place() -> list[OpenOrder]:
            from py_clob_client_v2.clob_types import (
                OrderArgsV2,
                OrderType,
                PartialCreateOrderOptions,
                PostOrdersV2Args,
            )

            opts = PartialCreateOrderOptions(tick_size=_tick_str(meta.tick_size), neg_risk=meta.neg_risk)
            args = []
            for q in quotes:
                signed = self._client.create_order(
                    OrderArgsV2(token_id=q.token_id, price=q.price, size=q.size, side=q.side.value),
                    options=opts,
                )
                args.append(PostOrdersV2Args(order=signed, orderType=OrderType.GTC))
            resp = self._client.post_orders(args, post_only=self._cfg.execution.post_only)
            return self._parse_place_response(resp, quotes)

        try:
            return await asyncio.to_thread(_place)
        except Exception as exc:  # noqa: BLE001 - surface + continue; engine handles error rate
            log.error("place_failed", err=str(exc), n=len(quotes))
            return []

    def _paper_order(self, q: Quote) -> OpenOrder:
        oid = f"paper-{next(self._paper_ids)}"
        return OpenOrder(oid, q.token_id, q.side, q.price, q.size, OrderState.LIVE)

    def _parse_place_response(self, resp: Any, quotes: list[Quote]) -> list[OpenOrder]:
        """Map a batch post response to OpenOrders. Tolerant of shape variants;
        the user-WS order events + REST snapshot reconcile anything we miss."""
        items = resp if isinstance(resp, list) else resp.get("orders", resp.get("data", []))
        out: list[OpenOrder] = []
        for q, item in zip(quotes, items if isinstance(items, list) else [], strict=False):
            oid = _first(item, "orderID", "orderId", "order_id", "id", "hash")
            if not oid:
                log.warning("place_response_missing_id", item=str(item)[:120])
                continue
            out.append(OpenOrder(str(oid), q.token_id, q.side, q.price, q.size, OrderState.LIVE))
        return out

    # ── cancellation ────────────────────────────────────────────────────
    async def cancel(self, order_ids: list[str]) -> None:
        if not order_ids or self._paper:
            return
        await self._cancel_bucket.acquire(1)

        def _cancel() -> None:
            self._client.cancel_orders(order_ids)

        try:
            await asyncio.to_thread(_cancel)
        except Exception as exc:  # noqa: BLE001
            log.error("cancel_failed", err=str(exc), n=len(order_ids))

    async def cancel_asset(self, asset_id: str) -> None:
        if self._paper:
            return

        def _cancel() -> None:
            from py_clob_client_v2.clob_types import OrderMarketCancelParams

            self._client.cancel_market_orders(OrderMarketCancelParams(asset_id=asset_id))

        await asyncio.to_thread(_cancel)

    async def cancel_all(self) -> None:
        if self._paper or self._client is None:
            return
        await asyncio.to_thread(self._client.cancel_all)
        log.info("cancel_all_sent")

    # ── heartbeat (dead-man switch) ─────────────────────────────────────
    async def heartbeat(self, hb_id: str = "") -> None:
        if self._paper or self._client is None:
            return
        try:
            await asyncio.to_thread(self._client.post_heartbeat, hb_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("heartbeat_failed", err=str(exc))

    # ── reads ───────────────────────────────────────────────────────────
    async def open_orders(self) -> list[OpenOrder]:
        if self._paper or self._client is None:
            return []

        def _get() -> list[OpenOrder]:
            raw = self._client.get_open_orders()
            rows = raw if isinstance(raw, list) else raw.get("data", raw.get("orders", []))
            out = []
            for r in rows:
                try:
                    side = Side(str(r["side"]).upper())
                    remaining = float(r.get("original_size", r.get("size", 0))) - float(
                        r.get("size_matched", 0)
                    )
                    out.append(
                        OpenOrder(
                            str(_first(r, "id", "orderID", "order_id")),
                            str(r["asset_id"]),
                            side,
                            float(r["price"]),
                            remaining,
                            OrderState.LIVE,
                        )
                    )
                except (KeyError, ValueError, TypeError):
                    continue
            return out

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            log.warning("open_orders_failed", err=str(exc))
            return []

    async def positions(self) -> dict[str, tuple[float, float]]:
        """{token_id: (size, avg_price)} from the data API (reconcile use).

        Queries the FUNDER (where positions live), not the signer EOA.
        """
        user = self.funder
        if not user or not user.startswith("0x") or user == "0xPAPER":
            return {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(f"{self._data_host}/positions", params={"user": user})
                r.raise_for_status()
                return {
                    str(p["asset"]): (float(p["size"]), float(p.get("avgPrice", 0)))
                    for p in r.json()
                    if float(p.get("size", 0)) > 0
                }
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("positions_failed", err=str(exc))
            return {}

    async def balance_allowance(self) -> dict[str, Any]:
        """Collateral balance/allowance snapshot (for `doctor`)."""
        if self._client is None:
            return {}

        def _get() -> dict[str, Any]:
            from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

            result: dict[str, Any] = self._client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            return result

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            log.warning("balance_allowance_failed", err=str(exc))
            return {}

    def _journal_write(self, kind: str, payload: Any, ts: float) -> None:
        if self._journal is not None:
            self._journal.write(kind, payload, ts)


def _first(d: Any, *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k]:
            return d[k]
    return None
