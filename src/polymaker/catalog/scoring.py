"""Market attractiveness scoring for the scanner.

Combines the v1 reward-density intuition with the new maker-rebate income
stream and penalizes spread/extremes. Higher score = more attractive to make.
Pure functions over MarketMeta.
"""

from __future__ import annotations

from dataclasses import dataclass

from polymaker.domain import MarketMeta


@dataclass(frozen=True, slots=True)
class MarketScore:
    condition_id: str
    reward_density: float  # est. reward $/day per $100 of two-sided liquidity
    rebate_potential: float  # est. daily rebate $ available to makers
    spread: float
    extremity: float  # 0 = mid ~0.5 (good), 1 = near 0/1 (bad payoff asymmetry)
    score: float


def _mid(m: MarketMeta) -> float:
    if m.best_bid > 0 and m.best_ask > 0:
        return (m.best_bid + m.best_ask) / 2.0
    return 0.5


def reward_density(m: MarketMeta, quote_size_usdc: float = 100.0) -> float:
    """Rough reward $/day if we hold ~quote_size two-sided in-band.

    The exact per-order S((v-s)/v)^2 scoring depends on live competition; for
    ranking we use daily_rate scaled by how much of the (small) market our
    typical size represents, capped. This mirrors v1's gm_reward_per_100 as a
    relative ranking signal, not an absolute forecast.
    """
    if m.rewards_daily_rate <= 0 or m.rewards_max_spread <= 0:
        return 0.0
    liq = max(m.liquidity_num, quote_size_usdc)
    our_share = min(1.0, quote_size_usdc / liq)
    return m.rewards_daily_rate * our_share


def rebate_potential(m: MarketMeta) -> float:
    """Est. daily maker-rebate pool: taker_fee_rate * rebate_rate * daily volume."""
    if not m.fees_enabled or m.rebate_rate <= 0 or m.taker_fee_bps <= 0:
        return 0.0
    daily_vol = m.volume_num  # best proxy available from catalog; refined live
    taker_rate = m.taker_fee_bps / 10000.0
    # taker fee peaks at p*(1-p); use mid as the representative point
    mid = _mid(m)
    fee_factor = mid * (1.0 - mid)
    return daily_vol * taker_rate * fee_factor * m.rebate_rate * 0.01  # 1% daily-vol proxy


def extremity(m: MarketMeta) -> float:
    """0 near 0.5 (balanced), ->1 near the 0/1 boundary (skip these)."""
    mid = _mid(m)
    return min(1.0, abs(mid - 0.5) / 0.5)


def score_market(m: MarketMeta) -> MarketScore:
    rd = reward_density(m)
    rp = rebate_potential(m)
    ext = extremity(m)
    spread = max(0.0, m.best_ask - m.best_bid) if (m.best_bid and m.best_ask) else 1.0

    # income terms are additive; extremity and wide spreads discount the score
    income = rd + rp
    penalty = (1.0 - 0.5 * ext) * (1.0 / (1.0 + spread * 20.0))
    return MarketScore(
        condition_id=m.condition_id,
        reward_density=round(rd, 3),
        rebate_potential=round(rp, 3),
        spread=round(spread, 4),
        extremity=round(ext, 3),
        score=round(income * penalty, 4),
    )
