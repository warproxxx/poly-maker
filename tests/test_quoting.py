"""Unit tests for pure quote construction — the strategy's decision core."""

from __future__ import annotations

import pytest

from polymaker.domain import Position, Regime, Side
from polymaker.strategy.quoting import (
    QuoteInputs,
    compute_fair_value,
    construct_quotes,
    round_to_tick,
)
from tests.conftest import view


def _inputs(meta, profile, **over):
    base = dict(
        meta=meta,
        regime=Regime.QUIET,
        fv=0.50,
        vol_short=0.0,
        toxicity=0.0,
        yes_view=view(0.49, 0.51),
        no_view=view(0.49, 0.51),
        pos_yes=Position("yes-token"),
        pos_no=Position("no-token"),
        profile=profile,
        now=1000.0,
    )
    base.update(over)
    return QuoteInputs(**base)


# ── round_to_tick ──────────────────────────────────────────────────────────


def test_round_to_tick_down_and_up():
    assert round_to_tick(0.5049, 0.01, 2, up=False) == 0.50
    assert round_to_tick(0.5051, 0.01, 2, up=True) == 0.51
    # clamps inside (0,1)
    assert round_to_tick(0.0, 0.01, 2, up=False) == 0.01
    assert round_to_tick(1.0, 0.01, 2, up=True) == 0.99


def test_compute_fair_value_flow_nudge():
    # positive flow nudges FV up, negative down, no flow = microprice
    assert compute_fair_value(0.50, 0.0, 0.01) == pytest.approx(0.50)
    assert compute_fair_value(0.50, 1.0, 0.01, weight=0.5) == pytest.approx(0.505)
    assert compute_fair_value(0.50, -1.0, 0.01, weight=0.5) == pytest.approx(0.495)


# ── two-sided quoting ────────────────────────────────────────────────────────


def test_quiet_market_quotes_both_sides_as_bids(meta, profile):
    tq = construct_quotes(_inputs(meta, profile))
    assert tq.regime == Regime.QUIET
    yes = [q for q in tq.quotes if q.token_id == "yes-token"]
    no = [q for q in tq.quotes if q.token_id == "no-token"]
    assert yes and no
    # both entry quotes are BUYs (USDC-collateralized two-sided quote)
    assert all(q.side == Side.BUY for q in yes)
    assert all(q.side == Side.BUY for q in no)


def test_pair_prices_sum_below_one(meta, profile):
    """BUY YES @ p and BUY NO @ q must satisfy p + q < 1 (merge edge)."""
    tq = construct_quotes(_inputs(meta, profile))
    top_yes = max(q.price for q in tq.quotes if q.token_id == "yes-token")
    top_no = max(q.price for q in tq.quotes if q.token_id == "no-token")
    assert top_yes + top_no < 1.0


def test_never_bids_through_fair_value(meta, profile):
    """No BUY should ever sit at or above FV - min_edge (YES) / (1-FV)-min_edge (NO)."""
    tq = construct_quotes(_inputs(meta, profile, fv=0.50))
    edge = profile.min_edge_ticks * meta.tick_size
    for q in tq.quotes:
        if q.side == Side.BUY and q.token_id == "yes-token":
            assert q.price <= 0.50 - edge + 1e-9
        if q.side == Side.BUY and q.token_id == "no-token":
            assert q.price <= 0.50 - edge + 1e-9  # NO fv is also 0.50 here


def test_layers_split_size(meta, profile):
    tq = construct_quotes(_inputs(meta, profile))
    yes = sorted((q for q in tq.quotes if q.token_id == "yes-token" and q.side == Side.BUY),
                 key=lambda q: -q.price)
    assert len(yes) == profile.layers
    # deeper layer is at a lower price
    assert yes[0].price > yes[1].price


# ── inventory skew ──────────────────────────────────────────────────────────


def test_long_yes_inventory_skews_quotes_down(meta, profile):
    """Holding YES should lower the YES bid and raise the NO bid vs flat."""
    flat = construct_quotes(_inputs(meta, profile, vol_short=0.02))
    longy = construct_quotes(
        _inputs(meta, profile, vol_short=0.02, pos_yes=Position("yes-token", 300, 0.5))
    )

    def top(tq, tok):
        ps = [q.price for q in tq.quotes if q.token_id == tok and q.side == Side.BUY]
        return max(ps) if ps else None

    # YES bid should not be higher when long YES; NO bid should not be lower
    assert top(longy, "yes-token") <= top(flat, "yes-token")
    assert top(longy, "no-token") >= top(flat, "no-token")


def test_reduce_only_emits_only_exits(meta, profile):
    tq = construct_quotes(
        _inputs(
            meta, profile, regime=Regime.REDUCE_ONLY,
            pos_yes=Position("yes-token", 100, 0.5),
        )
    )
    assert all(q.side == Side.SELL for q in tq.quotes)
    assert any(q.token_id == "yes-token" for q in tq.quotes)


def test_event_and_halted_pull_all_quotes(meta, profile):
    for regime in (Regime.EVENT, Regime.HALTED):
        tq = construct_quotes(
            _inputs(meta, profile, regime=regime, pos_yes=Position("yes-token", 100, 0.5))
        )
        assert tq.is_empty


# ── exits ────────────────────────────────────────────────────────────────────


def test_exit_sell_priced_above_fv_when_not_urgent(meta, profile):
    tq = construct_quotes(
        _inputs(meta, profile, pos_yes=Position("yes-token", 100, 0.4), yes_exit_urgency=0.0)
    )
    sells = [q for q in tq.quotes if q.side == Side.SELL and q.token_id == "yes-token"]
    assert sells
    assert sells[0].price >= 0.50  # at/above FV, a passive maker exit


def test_exit_never_below_best_bid(meta, profile):
    tq = construct_quotes(
        _inputs(
            meta, profile,
            pos_yes=Position("yes-token", 100, 0.4),
            yes_view=view(0.49, 0.51),
            yes_exit_urgency=1.0,  # maximally urgent
        )
    )
    sells = [q for q in tq.quotes if q.side == Side.SELL and q.token_id == "yes-token"]
    assert sells
    assert sells[0].price >= 0.49  # still a maker order, never crosses down


def test_no_exit_when_position_is_dust(meta, profile):
    tq = construct_quotes(
        _inputs(meta, profile, pos_yes=Position("yes-token", 1.0, 0.4))  # below min_order_size
    )
    assert not [q for q in tq.quotes if q.side == Side.SELL]


# ── spread widening ──────────────────────────────────────────────────────────


def test_toxicity_widens_spread(meta, profile):
    """Higher toxicity should push the YES bid lower (wider spread)."""
    calm = construct_quotes(_inputs(meta, profile, regime=Regime.TRENDING, toxicity=0.0))
    toxic = construct_quotes(_inputs(meta, profile, regime=Regime.TRENDING, toxicity=0.02))

    def top_yes(tq):
        ps = [q.price for q in tq.quotes if q.token_id == "yes-token" and q.side == Side.BUY]
        return max(ps) if ps else None

    assert top_yes(toxic) < top_yes(calm)


def test_quiet_regime_clamps_spread_to_reward_band(meta, profile):
    """In QUIET, even with high vol the bid stays within the reward band of FV."""
    tq = construct_quotes(_inputs(meta, profile, regime=Regime.QUIET, vol_short=0.5))
    band = meta.rewards_max_spread / 100.0  # 0.03
    top_yes = max(q.price for q in tq.quotes if q.token_id == "yes-token" and q.side == Side.BUY)
    # bid should be within (band + a tick of rounding) of FV
    assert top_yes >= 0.50 - band - meta.tick_size
