"""SQLite persistence for the market catalog and scan results.

Replaces the v1 "All Markets" / "Volatility Markets" Google Sheets. One local
file (state.db), queryable by the CLI. WAL mode so the running bot and a
`polymaker markets` query don't block each other.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from polymaker.catalog.scoring import MarketScore, score_market
from polymaker.domain import MarketMeta, TokenMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    condition_id      TEXT PRIMARY KEY,
    question          TEXT,
    slug              TEXT,
    meta_json         TEXT NOT NULL,
    score             REAL DEFAULT 0,
    score_json        TEXT,
    scanned_ts        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_markets_score ON markets(score DESC);
CREATE INDEX IF NOT EXISTS idx_markets_slug ON markets(slug);

CREATE TABLE IF NOT EXISTS tags (
    slug   TEXT PRIMARY KEY,
    tag_id TEXT NOT NULL,
    ts     REAL NOT NULL
);
"""


class CatalogStore:
    """Owns the markets/tags tables in state.db."""

    def __init__(self, db_path: str | Path = "state.db") -> None:
        self.path = str(db_path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_market(self, meta: MarketMeta, score: MarketScore | None = None) -> None:
        sc = score or score_market(meta)
        self._conn.execute(
            """INSERT INTO markets(condition_id, question, slug, meta_json, score, score_json, scanned_ts)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(condition_id) DO UPDATE SET
                 question=excluded.question, slug=excluded.slug, meta_json=excluded.meta_json,
                 score=excluded.score, score_json=excluded.score_json, scanned_ts=excluded.scanned_ts""",
            (
                meta.condition_id,
                meta.question,
                meta.slug,
                _dump_meta(meta),
                sc.score,
                json.dumps(asdict(sc)),
                time.time(),
            ),
        )
        self._conn.commit()

    def upsert_many(self, metas: list[MarketMeta]) -> int:
        for m in metas:
            self.upsert_market(m)
        return len(metas)

    def get(self, condition_id: str) -> MarketMeta | None:
        row = self._conn.execute(
            "SELECT meta_json FROM markets WHERE condition_id=?", (condition_id,)
        ).fetchone()
        return _load_meta(row["meta_json"]) if row else None

    def get_by_slug(self, slug: str) -> MarketMeta | None:
        row = self._conn.execute(
            "SELECT meta_json FROM markets WHERE slug=?", (slug,)
        ).fetchone()
        return _load_meta(row["meta_json"]) if row else None

    def top(self, limit: int = 50, fresh_s: float = 3600.0) -> list[tuple[MarketMeta, MarketScore]]:
        """Top markets by score, restricted to the most recent scan.

        The markets table accumulates rows across scans; without a freshness gate
        a stale row (scored by an older formula, or a market that has since
        resolved / dropped out of the tag) can surface at the top. We keep only
        rows scanned within `fresh_s` of the newest row.
        """
        newest = self._conn.execute("SELECT MAX(scanned_ts) AS t FROM markets").fetchone()
        cutoff = (newest["t"] or 0.0) - fresh_s
        rows = self._conn.execute(
            "SELECT meta_json, score_json FROM markets WHERE scanned_ts >= ? "
            "ORDER BY score DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        out = []
        for row in rows:
            meta = _load_meta(row["meta_json"])
            sc = MarketScore(**json.loads(row["score_json"])) if row["score_json"] else score_market(meta)
            out.append((meta, sc))
        return out

    def export_csv(self, path: str | Path, limit: int = 500) -> int:
        """Write the scored catalog to a CSV for easy market picking.

        Columns are chosen so you can eyeball reward/rebate income, cost (spread,
        fee category), liquidity, and the exact slug/condition_id to paste into
        markets.toml. Returns the number of rows written.
        """
        rows = self.top(limit)
        fields = [
            "score", "reward_pool_per_day", "rebate_pool_per_day", "spread",
            "best_bid", "best_ask", "tick", "min_size", "neg_risk", "taker_fee_pct",
            "rebate_pct", "rewards_max_spread", "liquidity", "volume_24h",
            "end_date", "question", "slug", "condition_id",
        ]
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(fields)
            for m, sc in rows:
                w.writerow([
                    f"{sc.score:.3f}", f"{m.rewards_daily_rate:.2f}", f"{sc.rebate_potential:.2f}",
                    f"{sc.spread:.4f}", m.best_bid, m.best_ask, f"{m.tick_size:g}",
                    f"{m.min_order_size:g}", int(m.neg_risk), f"{m.taker_fee_bps / 100:.1f}",
                    f"{m.rebate_rate * 100:.0f}", m.rewards_max_spread, f"{m.liquidity_num:.0f}",
                    f"{m.volume_24hr:.0f}", m.end_date_iso or "", m.question, m.slug, m.condition_id,
                ])
        return len(rows)

    def cache_tag(self, slug: str, tag_id: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tags(slug, tag_id, ts) VALUES(?,?,?)",
            (slug, tag_id, time.time()),
        )
        self._conn.commit()

    def cached_tag(self, slug: str) -> str | None:
        row = self._conn.execute("SELECT tag_id FROM tags WHERE slug=?", (slug,)).fetchone()
        return row["tag_id"] if row else None


def _dump_meta(meta: MarketMeta) -> str:
    d = asdict(meta)
    d["tokens"] = [asdict(t) for t in meta.tokens]
    return json.dumps(d)


def _load_meta(blob: str) -> MarketMeta:
    d = json.loads(blob)
    d["tokens"] = tuple(TokenMeta(**t) for t in d["tokens"])
    return MarketMeta(**d)
