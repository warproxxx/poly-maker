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
    """Estimated daily maker-rebate POOL for the market, using the exact V2 fee
    formula (per-market rate + rebate rate, no hardcoding).

    Per-share taker fee = fee_rate * p*(1-p)  (py_clob_client_v2/fees.py).
    Daily taker shares ~ vol_24h / mid, so:
        daily fees   = (vol/mid) * fee_rate * mid*(1-mid) = vol * fee_rate * (1-mid)
        rebate pool  = daily fees * rebate_rate
    This is the whole-market pool; your take is (your maker-fill share) x pool.
    It's a trailing-volume estimate — actual depends on future flow + fill share.
    """
    if not m.fees_enabled or m.rebate_rate <= 0 or m.taker_fee_bps <= 0:
        return 0.0
    vol24 = m.volume_24hr
    if vol24 <= 0:
        return 0.0
    fee_rate = m.taker_fee_bps / 10000.0
    mid = _mid(m)
    daily_fees = vol24 * fee_rate * (1.0 - mid)
    return round(daily_fees * m.rebate_rate, 2)


def extremity(m: MarketMeta) -> float:
    """0 near 0.5 (balanced), ->1 near the 0/1 boundary (skip these)."""
    mid = _mid(m)
    return min(1.0, abs(mid - 0.5) / 0.5)


def score_market(m: MarketMeta) -> MarketScore:
    rd = reward_density(m)  # our estimated reward income (share-adjusted)
    rp = rebate_potential(m)  # total daily rebate POOL (for display)
    ext = extremity(m)
    spread = max(0.0, m.best_ask - m.best_bid) if (m.best_bid and m.best_ask) else 1.0

    # our estimated income = reward share + (rebate pool * our fill/liquidity share);
    # extremity and wide spreads discount the score
    ref = 100.0
    our_share = min(0.5, ref / max(m.liquidity_num, ref))  # you won't own a whole pool
    income = rd + rp * our_share
    penalty = (1.0 - 0.5 * ext) * (1.0 / (1.0 + spread * 20.0))
    # viability: a market needs real book depth to actually quote — otherwise a
    # near-zero-liquidity market games "our share" to the top of the ranking
    viability = min(1.0, m.liquidity_num / 2000.0)
    return MarketScore(
        condition_id=m.condition_id,
        reward_density=round(rd, 3),
        rebate_potential=round(rp, 3),  # the market's total daily rebate pool
        spread=round(spread, 4),
        extremity=round(ext, 3),
        score=round(income * penalty * viability, 4),
    )
