"""Tests for market parsing, scoring, and the SQLite catalog store."""

from __future__ import annotations

import json

from polymaker.catalog.gamma import parse_market
from polymaker.catalog.scoring import score_market
from polymaker.catalog.store import CatalogStore

RAW = {
    "conditionId": "0xabc",
    "question": "Will candidate X win?",
    "slug": "will-x-win",
    "clobTokenIds": json.dumps(["tok-yes", "tok-no"]),
    "outcomes": json.dumps(["Yes", "No"]),
    "orderPriceMinTickSize": 0.01,
    "orderMinSize": 5,
    "negRisk": True,
    "acceptingOrders": True,
    "rewardsMinSize": 10,
    "rewardsMaxSpread": 3.0,
    "feesEnabled": True,
    "feeSchedule": {"rate": 0.01, "takerOnly": True, "rebateRate": 0.25},
    "bestBid": 0.48,
    "bestAsk": 0.50,
    "liquidityNum": 20000.0,
    "volumeNum": 500000.0,
    "endDate": "2028-11-07T00:00:00Z",
    "events": [{"id": 999, "slug": "2028-election"}],
}


def test_parse_market_maps_fields():
    m = parse_market(RAW, reward_rates={"0xabc": 42.0})
    assert m is not None
    assert m.condition_id == "0xabc"
    assert m.yes.token_id == "tok-yes"
    assert m.no.token_id == "tok-no"
    assert m.tick_size == 0.01
    assert m.neg_risk is True
    assert m.rewards_daily_rate == 42.0
    assert m.taker_fee_bps == 100  # 0.01 -> 100 bps
    assert m.maker_fee_bps == 0  # V2 makers pay zero
    assert m.rebate_rate == 0.25
    assert m.event_id == "999"


def test_parse_market_rejects_non_binary_and_closed():
    triple = {**RAW, "clobTokenIds": json.dumps(["a", "b", "c"]),
              "outcomes": json.dumps(["A", "B", "C"])}
    assert parse_market(triple) is None
    not_accepting = {**RAW, "acceptingOrders": False}
    assert parse_market(not_accepting) is None


def test_score_prefers_rewards_and_rebates():
    good = parse_market(RAW, {"0xabc": 100.0})
    poor = parse_market({**RAW, "conditionId": "0xdef", "rewardsMinSize": 0,
                         "rewardsMaxSpread": 0, "feesEnabled": False},
                        {"0xdef": 0.0})
    assert score_market(good).score > score_market(poor).score


def test_score_penalizes_extremity():
    balanced = parse_market(RAW, {"0xabc": 50.0})
    extreme = parse_market({**RAW, "conditionId": "0xext", "bestBid": 0.96, "bestAsk": 0.98},
                           {"0xext": 50.0})
    assert score_market(extreme).extremity > score_market(balanced).extremity


def test_store_roundtrip_and_top(tmp_path):
    store = CatalogStore(tmp_path / "s.db")
    m = parse_market(RAW, {"0xabc": 42.0})
    store.upsert_market(m)
    assert store.get("0xabc").condition_id == "0xabc"
    assert store.get_by_slug("will-x-win").slug == "will-x-win"
    top = store.top(10)
    assert len(top) == 1 and top[0][0].condition_id == "0xabc"
    # tokens survive the JSON round-trip as a 2-tuple
    assert len(store.get("0xabc").tokens) == 2
    store.close()


def test_store_upsert_is_idempotent(tmp_path):
    store = CatalogStore(tmp_path / "s.db")
    m = parse_market(RAW, {"0xabc": 42.0})
    store.upsert_market(m)
    store.upsert_market(m)  # second time updates, not duplicates
    assert len(store.top(10)) == 1
    store.close()
