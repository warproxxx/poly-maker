"""Async Gamma API client for market discovery.

Gamma (https://gamma-api.polymarket.com, no auth) returns everything the v1
scanner burned two extra REST calls per market to compute: best bid/ask,
liquidity, volume, reward params, fee schedule, tick size, tokens. We filter
server-side by the politics tag and liquidity/volume, so a full political-market
sweep is a handful of paginated requests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from polymaker.domain import MarketMeta, TokenMeta
from polymaker.logging import get_logger

log = get_logger("catalog.gamma")

POLITICS_TAG_SLUG = "politics"


class GammaClient:
    """Thin async wrapper over the Gamma REST endpoints we use."""

    def __init__(self, host: str = "https://gamma-api.polymarket.com", timeout: float = 20.0) -> None:
        self._host = host.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._host, timeout=timeout)

    async def __aenter__(self) -> GammaClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def markets_by_condition(self, condition_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch current raw market dicts for specific condition ids (metadata
        refresh: detect closed/not-accepting/resolved and updated end dates)."""
        out: dict[str, dict[str, Any]] = {}
        if not condition_ids:
            return out
        try:
            r = await self._client.get(
                "/markets",
                params={"condition_ids": ",".join(condition_ids), "limit": len(condition_ids) + 5},
            )
            r.raise_for_status()
            for m in r.json():
                cid = m.get("conditionId")
                if cid:
                    out[cid] = m
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("markets_by_condition_failed", err=str(exc))
        return out

    async def resolve_tag_id(self, slug: str) -> str | None:
        try:
            r = await self._client.get(f"/tags/slug/{slug}")
            r.raise_for_status()
            return str(r.json()["id"])
        except (httpx.HTTPError, KeyError, json.JSONDecodeError):
            log.warning("tag_resolve_failed", slug=slug)
            return None

    async def iter_markets(
        self,
        *,
        tag_id: str | None = None,
        related_tags: bool = True,
        min_liquidity: float = 0.0,
        min_volume_24hr: float = 0.0,
        limit: int = 100,  # Gamma caps a page at 100 regardless of a higher ask
        max_pages: int = 25,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw active/open market dicts, offset-paginated.

        Uses the offset `/markets` endpoint because it reliably supports
        `tag_id` filtering today. (Keyset is the go-forward per docs; switch when
        it supports tag filtering. See the README.)
        """
        offset = 0
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
            }
            if tag_id:
                params["tag_id"] = tag_id
                params["related_tags"] = "true" if related_tags else "false"
            if min_liquidity > 0:
                params["liquidity_num_min"] = min_liquidity
            if min_volume_24hr > 0:
                params["volume_num_min"] = min_volume_24hr

            r = await self._client.get("/markets", params=params)
            # Gamma returns 422 (not an empty page) once the offset runs past the
            # last result — treat that as the natural end of pagination.
            if r.status_code in (400, 422):
                log.info("pagination_end", offset=offset, status=r.status_code)
                return
            r.raise_for_status()
            batch = r.json()
            if not batch:
                return
            for m in batch:
                yield m
            if len(batch) < limit:
                return
            offset += limit


def parse_market(raw: dict[str, Any], reward_rates: dict[str, float] | None = None) -> MarketMeta | None:
    """Convert a Gamma market dict into our MarketMeta, or None if unusable."""
    try:
        if not raw.get("acceptingOrders", False):
            return None
        token_ids = _json_list(raw.get("clobTokenIds"))
        outcomes = _json_list(raw.get("outcomes"))
        if len(token_ids) != 2 or len(outcomes) != 2:
            return None  # only binary markets

        condition_id = raw["conditionId"]
        rate_map = reward_rates or {}
        fee = raw.get("feeSchedule") or {}
        taker_rate = float(fee.get("rate", 0.0) or 0.0)

        event_id = None
        events = raw.get("events") or []
        if events:
            event_id = str(events[0].get("id")) if events[0].get("id") is not None else None

        return MarketMeta(
            condition_id=condition_id,
            question=raw.get("question", ""),
            slug=raw.get("slug", ""),
            tokens=(
                TokenMeta(str(token_ids[0]), str(outcomes[0])),
                TokenMeta(str(token_ids[1]), str(outcomes[1])),
            ),
            tick_size=float(raw.get("orderPriceMinTickSize", 0.001) or 0.001),
            neg_risk=bool(raw.get("negRisk", False)),
            min_order_size=float(raw.get("orderMinSize", 5) or 5),
            rewards_min_size=float(raw.get("rewardsMinSize", 0) or 0),
            rewards_max_spread=float(raw.get("rewardsMaxSpread", 0) or 0),
            rewards_daily_rate=float(rate_map.get(condition_id, 0.0)),
            maker_fee_bps=0,  # V2: makers pay zero
            taker_fee_bps=int(round(taker_rate * 10000)),
            fees_enabled=bool(raw.get("feesEnabled", False)),
            rebate_rate=float(fee.get("rebateRate", 0.0) or 0.0),
            end_date_iso=raw.get("endDate"),
            event_id=event_id,
            best_bid=float(raw.get("bestBid", 0) or 0),
            best_ask=float(raw.get("bestAsk", 0) or 0),
            liquidity_num=float(raw.get("liquidityNum", 0) or 0),
            volume_num=float(raw.get("volumeNum", 0) or 0),
            # prefer CLOB 24h volume (the taker flow that generates fees);
            # fall back to total 24h volume
            volume_24hr=float(raw.get("volume24hrClob") or raw.get("volume24hr") or 0),
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("parse_market_failed", err=str(exc), slug=raw.get("slug"))
        return None


def _json_list(value: Any) -> list[Any]:
    """clobTokenIds / outcomes arrive as JSON-encoded strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def fetch_reward_rates(
    clob_host: str = "https://clob.polymarket.com", timeout: float = 20.0
) -> dict[str, float]:
    """Build {condition_id: daily USDC reward rate} from CLOB sampling-markets.

    These are the rewards-enabled markets; the daily rate isn't on Gamma.
    """
    usdc = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
    rates: dict[str, float] = {}
    async with httpx.AsyncClient(base_url=clob_host.rstrip("/"), timeout=timeout) as client:
        cursor = ""
        for _ in range(50):
            r = await client.get("/sampling-markets", params={"next_cursor": cursor})
            r.raise_for_status()
            data = r.json()
            for m in data.get("data", []):
                cid = m.get("condition_id")
                rate = 0.0
                for ri in (m.get("rewards") or {}).get("rates") or []:
                    if str(ri.get("asset_address", "")).lower() == usdc:
                        rate = float(ri.get("rewards_daily_rate", 0) or 0)
                        break
                if cid:
                    rates[cid] = rate
            cursor = data.get("next_cursor") or ""
            if not cursor or cursor == "LTE=":  # "LTE=" is the documented end sentinel
                break
    return rates
