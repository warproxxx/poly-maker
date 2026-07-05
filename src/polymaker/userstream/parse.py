"""Pure parsers for user-WS frames -> normalized trade/order events.

Fills come from `trade` events; open-order tracking from `order` events. The
maker/taker/mint side logic mirrors v1's proven handler (post-only means we are
always the maker):

  * maker & taker on the SAME outcome  -> we SELL the taker's asset (reverse side)
  * maker & taker on DIFFERENT outcomes -> a mint: we BUY the opposite token

NOTE: exact field names must be reconfirmed in the Phase-2 wallet spike
(docs/scoping/03-api-layer.md §9); this is coded to the v1-observed shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from polymaker.domain import Side, TradeState
from polymaker.state.tracker import OrderEvent, TradeEvent

_STATUS = {
    "MATCHED": TradeState.MATCHED,
    "MINED": TradeState.MINED,
    "CONFIRMED": TradeState.CONFIRMED,
    "RETRYING": TradeState.RETRYING,
    "FAILED": TradeState.FAILED,
}


def _ts(msg: dict[str, Any]) -> float:
    raw = msg.get("timestamp")
    try:
        v = float(raw)  # type: ignore[arg-type]
        return v / 1000.0 if v > 1e12 else v
    except (ValueError, TypeError):
        return 0.0


def normalize_trade(
    msg: dict[str, Any],
    our_address: str,
    other_token: Callable[[str], str | None],
) -> list[TradeEvent]:
    """Extract our maker fills from a `trade` event. Returns one TradeEvent per
    matching maker order (usually one)."""
    status = _STATUS.get(str(msg.get("status", "")).upper())
    if status is None:
        return []
    taker_asset = str(msg.get("asset_id", ""))
    taker_side = _side(msg.get("side"))
    taker_outcome = msg.get("outcome")
    ts = _ts(msg)
    trade_id = str(msg.get("id", ""))
    addr = our_address.lower()

    out: list[TradeEvent] = []
    for i, mo in enumerate(msg.get("maker_orders", []) or []):
        if str(mo.get("maker_address", "")).lower() != addr:
            continue
        try:
            size = float(mo.get("matched_amount", 0))
            price = float(mo.get("price", 0))
        except (ValueError, TypeError):
            continue
        if size <= 0:
            continue
        if mo.get("outcome") == taker_outcome:
            token = taker_asset
            our_side = taker_side.opposite
        else:
            token = other_token(taker_asset) or taker_asset
            our_side = taker_side
        out.append(
            TradeEvent(
                token_id=token,
                our_side=our_side,
                price=price,
                size=size,
                trade_id=f"{trade_id}:{i}" if len(msg.get('maker_orders', [])) > 1 else trade_id,
                status=status,
                ts=ts,
            )
        )
    return out


def normalize_order(msg: dict[str, Any]) -> OrderEvent | None:
    """Map an `order` event to remaining-size tracking for the reconciler."""
    try:
        asset = str(msg["asset_id"])
        side = _side(msg.get("side"))
        original = float(msg.get("original_size", msg.get("size", 0)))
        matched = float(msg.get("size_matched", 0))
        remaining = original - matched
        status = str(msg.get("status", "")).upper()
        is_cancel = status in ("CANCELED", "CANCELLED") or msg.get("type") == "CANCELLATION"
        return OrderEvent(
            order_id=str(msg.get("id", "")),
            token_id=asset,
            side=side,
            price=float(msg.get("price", 0)),
            remaining_size=remaining,
            is_cancel=is_cancel,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _side(value: object) -> Side:
    return Side.SELL if str(value).upper() == "SELL" else Side.BUY
