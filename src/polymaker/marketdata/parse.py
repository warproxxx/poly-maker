"""Pure parsers for market-WS wire messages -> structured updates.

Kept separate from the socket so they're unit-testable against captured frames.
Verified against live frames on 2026-07-05 (the README):

  book:        {market, asset_id, bids:[{price,size}], asks:[...], timestamp, hash, tick_size}
  price_change:{market, timestamp, price_changes:[{asset_id, price, size, side, hash}]}
  last_trade_price:{market, asset_id, price, size, side, timestamp, fee_rate_bps}
  tick_size_change:{market, asset_id, old_tick_size, new_tick_size}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from polymaker.domain import Side


@dataclass(frozen=True, slots=True)
class BookUpdate:
    asset_id: str
    condition_id: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    ts: float
    book_hash: str | None
    tick_size: float | None


@dataclass(frozen=True, slots=True)
class PriceChange:
    asset_id: str
    condition_id: str
    side: Side  # BUY -> bid side, SELL -> ask side
    price: float
    size: float
    ts: float


@dataclass(frozen=True, slots=True)
class TradePrint:
    asset_id: str
    condition_id: str
    aggressor: Side
    price: float
    size: float
    ts: float


@dataclass(frozen=True, slots=True)
class TickSizeChange:
    asset_id: str
    tick_size: float


def _ts(msg: dict[str, Any]) -> float:
    raw = msg.get("timestamp")
    if raw is None:
        return 0.0
    try:
        v = float(raw)
        return v / 1000.0 if v > 1e12 else v  # ms -> s
    except (ValueError, TypeError):
        return 0.0


def _levels(items: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for it in items or []:
        try:
            out.append((float(it["price"]), float(it["size"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_book(msg: dict[str, Any]) -> BookUpdate | None:
    try:
        tick = msg.get("tick_size")
        return BookUpdate(
            asset_id=str(msg["asset_id"]),
            condition_id=str(msg.get("market", "")),
            bids=_levels(msg.get("bids")),
            asks=_levels(msg.get("asks")),
            ts=_ts(msg),
            book_hash=msg.get("hash"),
            tick_size=float(tick) if tick is not None else None,
        )
    except (KeyError, ValueError, TypeError):
        return None


def parse_price_changes(msg: dict[str, Any]) -> list[PriceChange]:
    out: list[PriceChange] = []
    ts = _ts(msg)
    cond = str(msg.get("market", ""))
    for ch in msg.get("price_changes", []) or []:
        try:
            out.append(
                PriceChange(
                    asset_id=str(ch["asset_id"]),
                    condition_id=cond,
                    side=Side(str(ch["side"]).upper()),
                    price=float(ch["price"]),
                    size=float(ch["size"]),
                    ts=ts,
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_last_trade(msg: dict[str, Any]) -> TradePrint | None:
    try:
        return TradePrint(
            asset_id=str(msg["asset_id"]),
            condition_id=str(msg.get("market", "")),
            aggressor=Side(str(msg.get("side", "BUY")).upper()),
            price=float(msg["price"]),
            size=float(msg["size"]),
            ts=_ts(msg),
        )
    except (KeyError, ValueError, TypeError):
        return None


def parse_tick_size_change(msg: dict[str, Any]) -> TickSizeChange | None:
    try:
        tick = msg.get("new_tick_size", msg.get("tick_size"))
        if tick is None:
            return None
        return TickSizeChange(asset_id=str(msg["asset_id"]), tick_size=float(tick))
    except (KeyError, ValueError, TypeError):
        return None
