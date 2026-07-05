"""StateStore: the single owner of positions and open orders.

Replaces v1's module-level global dicts + the `performing`/`last_trade_update`
races. Three inputs, one arbitration rule (docs/scoping/02-architecture.md):

  * WS fill events apply immediately (optimistic),
  * REST reconciliation corrects drift ONLY for tokens with no in-flight trades,
  * on-chain balances are consulted only by the merger.

In-memory + typed, mirrored to SQLite on change so a crash-restart resumes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from polymaker.domain import Fill, OpenOrder, OrderState, Position, Side
from polymaker.logging import get_logger

log = get_logger("state.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    token_id  TEXT PRIMARY KEY,
    size      REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    trade_id  TEXT PRIMARY KEY,
    token_id  TEXT, side TEXT, price REAL, size REAL, is_maker INT, ts REAL
);
CREATE TABLE IF NOT EXISTS order_log (
    order_id  TEXT PRIMARY KEY,
    token_id  TEXT, side TEXT, price REAL, size REAL, state TEXT, ts REAL
);
"""


class StateStore:
    """Owns positions + open orders + a per-token in-flight guard."""

    def __init__(self, db_path: str | Path = "state.db") -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        self.positions: dict[str, Position] = {}
        # order_id -> OpenOrder
        self.orders: dict[str, OpenOrder] = {}
        # token_id -> count of in-flight (MATCHED-not-CONFIRMED) trades; guards reconcile
        self._inflight: dict[str, int] = {}
        self._last_fill_ts: dict[str, float] = {}
        self._load()

    def close(self) -> None:
        self._conn.close()

    # ── positions ───────────────────────────────────────────────────────
    def position(self, token_id: str) -> Position:
        return self.positions.get(token_id, Position(token_id))

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill optimistically to inventory + avg price."""
        pos = self.positions.setdefault(fill.token_id, Position(fill.token_id))
        signed = fill.size if fill.side is Side.BUY else -fill.size
        new_size = pos.size + signed
        if fill.side is Side.BUY:
            if pos.size <= 0:
                pos.avg_price = fill.price
            else:
                pos.avg_price = (pos.avg_price * pos.size + fill.price * fill.size) / (
                    pos.size + fill.size
                )
        # selling leaves avg_price unchanged
        pos.size = max(0.0, new_size)
        if pos.size <= 0:
            pos.avg_price = 0.0
        self._last_fill_ts[fill.token_id] = fill.ts
        self._persist_position(pos)
        self._record_fill(fill)
        log.info("fill", token=fill.token_id[:12], side=fill.side.value,
                 price=fill.price, size=fill.size, pos=round(pos.size, 2))

    def set_position(self, token_id: str, size: float, avg_price: float) -> None:
        pos = Position(token_id, max(0.0, size), avg_price if size > 0 else 0.0)
        self.positions[token_id] = pos
        self._persist_position(pos)

    def reconcile_positions(self, api_positions: dict[str, tuple[float, float]]) -> None:
        """Overwrite sizes from REST, skipping tokens with in-flight trades or
        a very recent fill (the optimistic value is more current there)."""
        now = time.time()
        for token_id, (size, avg) in api_positions.items():
            if self._inflight.get(token_id, 0) > 0:
                continue
            if now - self._last_fill_ts.get(token_id, 0.0) < 5.0:
                continue
            self.set_position(token_id, size, avg)

    # ── in-flight guard ─────────────────────────────────────────────────
    def mark_inflight(self, token_id: str) -> None:
        self._inflight[token_id] = self._inflight.get(token_id, 0) + 1

    def clear_inflight(self, token_id: str) -> None:
        if self._inflight.get(token_id, 0) > 0:
            self._inflight[token_id] -= 1

    def inflight(self, token_id: str) -> int:
        return self._inflight.get(token_id, 0)

    # ── orders ──────────────────────────────────────────────────────────
    def orders_for(self, token_id: str) -> list[OpenOrder]:
        return [o for o in self.orders.values() if o.token_id == token_id]

    def upsert_order(self, order: OpenOrder) -> None:
        if order.state in (OrderState.CANCELED, OrderState.DONE, OrderState.REJECTED):
            self.orders.pop(order.order_id, None)
        else:
            self.orders[order.order_id] = order
        self._persist_order(order)

    def remove_order(self, order_id: str) -> None:
        self.orders.pop(order_id, None)

    def replace_open_orders(self, token_id: str, live: list[OpenOrder]) -> None:
        """Replace our view of a token's open orders from a REST snapshot."""
        for oid in [o.order_id for o in self.orders.values() if o.token_id == token_id]:
            self.orders.pop(oid, None)
        for o in live:
            self.orders[o.order_id] = o

    # ── persistence ─────────────────────────────────────────────────────
    def _persist_position(self, pos: Position) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO positions(token_id,size,avg_price,updated_ts) VALUES(?,?,?,?)",
            (pos.token_id, pos.size, pos.avg_price, time.time()),
        )
        self._conn.commit()

    def _record_fill(self, f: Fill) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO fills(trade_id,token_id,side,price,size,is_maker,ts) VALUES(?,?,?,?,?,?,?)",
            (f.trade_id, f.token_id, f.side.value, f.price, f.size, int(f.is_maker), f.ts),
        )
        self._conn.commit()

    def _persist_order(self, o: OpenOrder) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO order_log(order_id,token_id,side,price,size,state,ts) VALUES(?,?,?,?,?,?,?)",
            (o.order_id, o.token_id, o.side.value, o.price, o.size, o.state.value, time.time()),
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute("SELECT token_id,size,avg_price FROM positions"):
            if row["size"] > 0:
                self.positions[row["token_id"]] = Position(
                    row["token_id"], row["size"], row["avg_price"]
                )

    # ── reporting ───────────────────────────────────────────────────────
    def snapshot(self) -> dict[str, object]:
        return {
            "positions": {k: json.loads(_pos_json(v)) for k, v in self.positions.items() if v.size > 0},
            "open_orders": len(self.orders),
        }


def _pos_json(p: Position) -> str:
    return json.dumps({"size": round(p.size, 4), "avg_price": round(p.avg_price, 4)})
