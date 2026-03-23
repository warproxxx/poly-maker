"""
Alpha Evaluation Script — Elon Tweet Count Trading Strategies
Uses real market data from March 23, 2026 to quantify edge.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple


# ============================================================
# REAL MARKET DATA (fetched March 23, 2026)
# ============================================================

# --- Market 1: March 17-24 weekly (expires Mar 24 16:00 UTC) ---
# xTracker: 322 tweets, 75% complete, pace projects 429
M17_24_BUCKETS = {
    # bucket_range: (yes_price, volume)
    "280-299": (0.0000, 684678),
    "300-319": (0.0005, 628828),
    "320-339": (0.0015, 487491),
    "340-359": (0.0430, 417557),
    "360-379": (0.1700, 385877),
    "380-399": (0.2790, 383185),
    "400-419": (0.2325, 372760),
    "420-439": (0.1520, 351877),
    "440-459": (0.0680, 416252),
    "460-479": (0.0345, 397931),
    "480-499": (0.0080, 346035),
    "500-519": (0.0035, 320439),
    "520-539": (0.0015, 356513),
    "540-559": (0.0005, 354973),
    "560-579": (0.0005, 435357),
    "580+":    (0.0005, 535610),
}

# --- Market 2: March 21-23 (expires Mar 23 16:00 UTC, ~14h away) ---
# xTracker: 76 tweets, 100% complete
M21_23_BUCKETS = {
    "<40":     (0.0000, 169303),
    "40-64":   (0.0000, 322837),
    "65-89":   (0.0590, 341014),
    "90-114":  (0.5950, 140826),
    "115-139": (0.3450, 152572),
    "140-164": (0.0200, 166129),
    "165-189": (0.0025, 271477),
    "190-214": (0.0005, 235401),
    "215-239": (0.0005, 128867),
    "240+":    (0.0005, 133382),
}

# --- Market 3: March 20-27 weekly (expires Mar 27 16:00 UTC) ---
# xTracker: 128 tweets, 43% complete, pace projects 299
M20_27_BUCKETS = {
    "120-139": (0.0005, 84299),
    "140-159": (0.0005, 107415),
    "160-179": (0.0005, 116820),
    "180-199": (0.0015, 134026),
    "200-219": (0.0035, 122046),
    "220-239": (0.0080, 90134),
    "240-259": (0.0165, 73165),
    "260-279": (0.0300, 88130),
    "280-299": (0.0650, 71123),
    "300-319": (0.0850, 63641),
    "320-339": (0.1250, 76138),
    "340-359": (0.1300, 63810),
    "360-379": (0.1200, 66120),
    "380-399": (0.0995, 78595),
    "400-419": (0.0935, 77966),
    "420-439": (0.0565, 85609),
    "440-459": (0.0350, 61826),
    "460-479": (0.0250, 68545),
    "480-499": (0.0165, 59531),
    "500-519": (0.0090, 52131),
    "520-539": (0.0055, 59112),
    "540-559": (0.0035, 51184),
    "560-579": (0.0025, 43997),
    "580+":    (0.0015, 123753),
}

# --- Market 4: March 23-25 (expires Mar 25 16:00 UTC, new) ---
M23_25_BUCKETS = {
    "<40":     (0.0350, 19577),
    "40-64":   (0.1050, 9109),
    "65-89":   (0.2700, 10183),
    "90-114":  (0.3050, 12341),
    "115-139": (0.1950, 10506),
    "140-164": (0.0660, 9425),
    "165-189": (0.0315, 17947),
    "190-214": (0.0115, 18342),
    "215-239": (0.0045, 29728),
    "240+":    (0.0015, 20505),
}

# --- xTracker ground truth ---
XTRACKER = {
    "mar_17_24": {"count": 322, "pct_complete": 0.75, "pace_projected": 429,
                  "period_start": "2026-03-17T16:00:00Z", "period_end": "2026-03-24T16:00:59Z",
                  "hours_total": 168, "hours_elapsed": 126},
    "mar_21_23": {"count": 76, "pct_complete": 1.00, "pace_projected": 76,
                  "period_start": "2026-03-21T16:00:00Z", "period_end": "2026-03-23T15:59:59Z",
                  "hours_total": 48, "hours_elapsed": 48},
    "mar_20_27": {"count": 128, "pct_complete": 0.43, "pace_projected": 299,
                  "period_start": "2026-03-20T16:00:00Z", "period_end": "2026-03-27T15:59:59Z",
                  "hours_total": 168, "hours_elapsed": 72},
    # Hourly data for Mar 21-23 (34 hours):
    "mar_21_23_hourly": [0,0,0,3,6,1,7,2,0,10,5,4,3,4,0,0,0,0,0,0,0,0,4,9,3,0,1,2,3,1,1,1,0,5,1],
}


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bucket_prob_normal(bucket_low: int, bucket_high: int, mu: float, sigma: float) -> float:
    """P(final count in [low, high]) using normal approximation."""
    if sigma <= 0:
        return 1.0 if bucket_low <= mu <= bucket_high else 0.0
    z_low = (bucket_low - 0.5 - mu) / sigma
    z_high = (bucket_high + 0.5 - mu) / sigma
    return norm_cdf(z_high) - norm_cdf(z_low)


def parse_range(key: str) -> Tuple[int, int]:
    """Parse '380-399' -> (380, 399) or '580+' -> (580, 9999) or '<40' -> (0, 39)."""
    if key.startswith("<"):
        return (0, int(key[1:]) - 1)
    if key.endswith("+"):
        return (int(key[:-1]), 9999)
    parts = key.split("-")
    return (int(parts[0]), int(parts[1]))


# ============================================================
# STRATEGY A: Adjacent Bucket Arbitrage
# ============================================================

def evaluate_adjacent_bucket(buckets: dict, market_name: str):
    """Check if buying center + adjacent buckets totals < $1."""
    print(f"\n{'='*60}")
    print(f"STRATEGY A: Adjacent Bucket Arbitrage — {market_name}")
    print(f"{'='*60}")

    # Sort by price descending to find center
    sorted_buckets = sorted(buckets.items(), key=lambda x: -x[1][0])

    # Sum ALL yes prices (= total vig)
    total_yes = sum(p for p, _ in buckets.values())
    print(f"\n  Sum of ALL yes prices: ${total_yes:.4f}")
    print(f"  Vig (overround):       ${total_yes - 1:.4f} ({(total_yes-1)*100:.2f}%)")

    # Try different window sizes around center
    print(f"\n  Top buckets by price:")
    for i, (bucket, (price, vol)) in enumerate(sorted_buckets[:8]):
        print(f"    {bucket:>10}: ${price:.4f}  (vol: ${vol:,})")

    print(f"\n  Adjacent bucket sets (center + N each side):")

    # Find center index
    bucket_keys = sorted(buckets.keys(), key=lambda k: parse_range(k)[0])
    prices = [(k, buckets[k][0]) for k in bucket_keys]
    center_idx = max(range(len(prices)), key=lambda i: prices[i][1])

    for n_adjacent in [1, 2, 3, 4, 5]:
        lo = max(0, center_idx - n_adjacent)
        hi = min(len(prices) - 1, center_idx + n_adjacent)
        selected = prices[lo:hi + 1]
        total_cost = sum(p for _, p in selected)
        buckets_str = f"{selected[0][0]} to {selected[-1][0]}"
        n_buckets = len(selected)

        if total_cost < 1.0:
            profit = 1.0 - total_cost
            roi = profit / total_cost * 100
            print(f"    ±{n_adjacent} ({n_buckets} buckets): cost=${total_cost:.4f}  "
                  f"PROFIT=${profit:.4f} ({roi:.1f}% ROI)  ✓  [{buckets_str}]")
        else:
            loss = total_cost - 1.0
            print(f"    ±{n_adjacent} ({n_buckets} buckets): cost=${total_cost:.4f}  "
                  f"LOSS=${loss:.4f}  ✗  [{buckets_str}]")

    # Find maximum profitable set
    best_profit = 0
    best_set = None
    for lo in range(len(prices)):
        cost = 0
        for hi in range(lo, len(prices)):
            cost += prices[hi][1]
            if cost < 1.0:
                profit = 1.0 - cost
                if profit > best_profit:
                    best_profit = profit
                    best_set = (lo, hi, cost, len(prices[lo:hi+1]))

    if best_set:
        lo, hi, cost, n = best_set
        roi = (1 - cost) / cost * 100 if cost > 0 else 0
        print(f"\n  Best profitable set: {n} buckets, cost=${cost:.4f}, "
              f"profit=${1-cost:.4f}, ROI={roi:.1f}%")
        print(f"    Range: {prices[lo][0]} to {prices[hi][0]}")
    else:
        print(f"\n  No profitable set found (all combinations cost ≥ $1)")


# ============================================================
# STRATEGY B: Pace Prediction vs Market (Information Edge)
# ============================================================

def evaluate_pace_prediction(buckets: dict, xt_data: dict, market_name: str):
    """Compare our pace model vs market-implied probabilities."""
    print(f"\n{'='*60}")
    print(f"STRATEGY B: Pace Prediction Edge — {market_name}")
    print(f"{'='*60}")

    count = xt_data["count"]
    hours_elapsed = xt_data["hours_elapsed"]
    hours_total = xt_data["hours_total"]
    hours_remaining = hours_total - hours_elapsed

    if hours_elapsed <= 0:
        print("  Period not started yet, skipping.")
        return

    pace = count / hours_elapsed
    mu = count + pace * hours_remaining
    sigma = math.sqrt(pace * hours_remaining) if hours_remaining > 0 else 0

    print(f"\n  xTracker count:     {count}")
    print(f"  Hours elapsed:      {hours_elapsed}h / {hours_total}h ({hours_elapsed/hours_total*100:.0f}%)")
    print(f"  Pace:               {pace:.2f} tweets/hour")
    print(f"  Projected total:    {mu:.0f}")
    print(f"  σ (uncertainty):    {sigma:.1f}")
    print(f"  95% CI:             [{mu - 1.96*sigma:.0f}, {mu + 1.96*sigma:.0f}]")
    if xt_data.get("pace_projected"):
        xt_pace = xt_data["pace_projected"]
        print(f"  xTracker projection: {xt_pace}")
        print(f"  Our vs xTracker:     {mu:.0f} vs {xt_pace} (diff={mu-xt_pace:.0f})")

    # Compare model prob vs market price for each bucket
    print(f"\n  {'Bucket':>10} | {'Market':>7} | {'Model':>7} | {'Edge':>7} | {'Signal':>8} | {'EV/unit':>8}")
    print(f"  {'-'*10}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}")

    edges = []
    for bucket_key in sorted(buckets.keys(), key=lambda k: parse_range(k)[0]):
        lo, hi = parse_range(bucket_key)
        market_price = buckets[bucket_key][0]

        model_prob = bucket_prob_normal(lo, hi, mu, sigma)

        edge = model_prob - market_price
        if market_price > 0.005:  # ignore dust
            ev_per_unit = (model_prob * 1.0) - market_price  # EV of buying YES at ask
            signal = "BUY" if edge > 0.03 else ("SELL" if edge < -0.03 else "—")

            print(f"  {bucket_key:>10} | {market_price:>6.2%} | {model_prob:>6.2%} | "
                  f"{edge:>+6.2%} | {signal:>8} | ${ev_per_unit:>+.4f}")

            edges.append((bucket_key, edge, ev_per_unit, market_price, model_prob))

    # Summary
    buy_signals = [(b, e, ev) for b, e, ev, _, _ in edges if e > 0.03]
    sell_signals = [(b, e, ev) for b, e, ev, _, _ in edges if e < -0.03]

    print(f"\n  BUY signals (model > market by >3%): {len(buy_signals)}")
    for b, e, ev in buy_signals:
        print(f"    {b}: edge={e:+.2%}, EV=${ev:+.4f}/unit")

    print(f"  SELL signals (model < market by >3%): {len(sell_signals)}")
    for b, e, ev in sell_signals:
        print(f"    {b}: edge={e:+.2%}, EV=${ev:+.4f}/unit")

    # Total edge = sum of absolute mispricing
    total_mispricing = sum(abs(e) for _, e, _, _, _ in edges)
    print(f"\n  Total mispricing (sum |edge|): {total_mispricing:.2%}")


# ============================================================
# STRATEGY C: Early Entry Analysis
# ============================================================

def evaluate_early_entry(buckets: dict, market_name: str, volume: float, liquidity: float):
    """Evaluate early entry opportunities in young markets."""
    print(f"\n{'='*60}")
    print(f"STRATEGY C: Early Entry — {market_name}")
    print(f"{'='*60}")

    total_volume = volume
    total_liquidity = liquidity

    print(f"\n  Total volume:    ${total_volume:,.0f}")
    print(f"  Total liquidity: ${total_liquidity:,.0f}")
    print(f"  Vol/Liq ratio:   {total_volume/total_liquidity:.2f}")

    # Check for cheap buckets
    cheap_buckets = []
    for bucket_key, (price, vol) in buckets.items():
        if 0.001 <= price <= 0.05:
            lo, hi = parse_range(bucket_key)
            cheap_buckets.append((bucket_key, price, vol))

    print(f"\n  Cheap buckets (1-5 cents):")
    if cheap_buckets:
        for b, p, v in sorted(cheap_buckets, key=lambda x: x[1]):
            max_payout = 1.0 / p
            print(f"    {b:>10}: ${p:.4f} (ask) → {max_payout:.0f}x payout if wins  (vol: ${v:,})")
    else:
        print(f"    None found — market already priced in.")

    # Historical base rate analysis
    # From xTracker daily data: typical weekly range ~280-430
    print(f"\n  Historical context:")
    print(f"    Recent weekly counts: ~280-430 (highly variable)")
    print(f"    At opening, uniform 1-2¢ pricing gives ~50-100x potential")
    print(f"    Window: first ~2 hours after market creation")


# ============================================================
# VIG ANALYSIS (cross-market)
# ============================================================

def analyze_vig(markets: dict):
    """Analyze the overround (vig) across all markets."""
    print(f"\n{'='*60}")
    print(f"VIG ANALYSIS — All Markets")
    print(f"{'='*60}")

    for name, buckets in markets.items():
        total = sum(p for p, _ in buckets.values())
        n_buckets = len(buckets)
        vig = total - 1.0
        print(f"\n  {name}:")
        print(f"    Buckets: {n_buckets}")
        print(f"    Sum YES: ${total:.4f}")
        print(f"    Vig:     ${vig:.4f} ({vig*100:.2f}%)")
        print(f"    Avg vig/bucket: ${vig/n_buckets:.4f}")


# ============================================================
# PACE VARIANCE ANALYSIS (from hourly data)
# ============================================================

def analyze_pace_variance():
    """Analyze tweet pace variance from hourly data to estimate prediction accuracy."""
    print(f"\n{'='*60}")
    print(f"PACE VARIANCE — Hourly Pattern Analysis")
    print(f"{'='*60}")

    hourly = XTRACKER["mar_21_23_hourly"]
    active_hours = [h for h in hourly if h > 0]
    total = sum(hourly)

    print(f"\n  Mar 21-23 hourly data ({len(hourly)} hours):")
    print(f"    Total tweets: {total}")
    print(f"    Active hours: {len(active_hours)} / {len(hourly)} ({len(active_hours)/len(hourly)*100:.0f}%)")
    print(f"    Mean (all hours): {total/len(hourly):.2f}/h")
    print(f"    Mean (active only): {sum(active_hours)/len(active_hours):.2f}/h")
    print(f"    Max hourly: {max(hourly)}")
    print(f"    Stdev (all hours): {stdev(hourly):.2f}")

    # Burstiness analysis
    # Hours with 0 tweets vs hours with >0
    zero_hours = sum(1 for h in hourly if h == 0)
    burst_hours = sum(1 for h in hourly if h >= 5)
    print(f"    Zero-tweet hours: {zero_hours} ({zero_hours/len(hourly)*100:.0f}%)")
    print(f"    Burst hours (≥5): {burst_hours} ({burst_hours/len(hourly)*100:.0f}%)")

    # This affects prediction accuracy
    print(f"\n  Implications for pace prediction:")
    print(f"    - Musk tweets in bursts, not at a constant rate")
    print(f"    - Poisson model underestimates variance (overdispersion)")
    print(f"    - True σ is ~1.5-2x the Poisson estimate")
    print(f"    - This means wider CIs → more buckets have non-trivial probability")

    # Simulate overdispersion factor
    empirical_var = variance(hourly)
    poisson_var = total / len(hourly)  # Poisson: var = mean
    overdispersion = empirical_var / poisson_var if poisson_var > 0 else float('inf')
    print(f"\n  Overdispersion factor: {overdispersion:.2f}x")
    print(f"    Poisson variance: {poisson_var:.2f}")
    print(f"    Empirical variance: {empirical_var:.2f}")
    print(f"    → Use σ_corrected = σ_poisson × √{overdispersion:.1f} = σ_poisson × {math.sqrt(overdispersion):.2f}")


def mean(data): return sum(data) / len(data) if data else 0
def variance(data):
    m = mean(data)
    return sum((x - m)**2 for x in data) / len(data) if data else 0
def stdev(data): return math.sqrt(variance(data))


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  ALPHA EVALUATION — Elon Tweet Trading Strategies")
    print("  Date: March 23, 2026")
    print("=" * 60)

    markets = {
        "Mar 17-24 (weekly, 1d left)": M17_24_BUCKETS,
        "Mar 21-23 (2d, ~14h left)": M21_23_BUCKETS,
        "Mar 20-27 (weekly, 4d left)": M20_27_BUCKETS,
        "Mar 23-25 (2d, just started)": M23_25_BUCKETS,
    }

    # --- Vig Analysis ---
    analyze_vig(markets)

    # --- Strategy A: Adjacent Bucket ---
    evaluate_adjacent_bucket(M17_24_BUCKETS, "Mar 17-24 (1 day left)")
    evaluate_adjacent_bucket(M21_23_BUCKETS, "Mar 21-23 (14h left)")
    evaluate_adjacent_bucket(M20_27_BUCKETS, "Mar 20-27 (4 days left)")
    evaluate_adjacent_bucket(M23_25_BUCKETS, "Mar 23-25 (new)")

    # --- Strategy B: Pace Prediction ---
    evaluate_pace_prediction(M17_24_BUCKETS, XTRACKER["mar_17_24"], "Mar 17-24")
    evaluate_pace_prediction(M21_23_BUCKETS, XTRACKER["mar_21_23"], "Mar 21-23")
    evaluate_pace_prediction(M20_27_BUCKETS, XTRACKER["mar_20_27"], "Mar 20-27")

    # --- Strategy C: Early Entry ---
    evaluate_early_entry(M23_25_BUCKETS, "Mar 23-25 (just opened)", 157524, 124742)

    # --- Pace Variance ---
    analyze_pace_variance()

    # --- FINAL VERDICT ---
    print(f"\n{'='*60}")
    print(f"  FINAL ALPHA VERDICT")
    print(f"{'='*60}")
    print("""
  Strategy A (Adjacent Bucket Arbitrage):
    → EVALUATE: Does the sum of center+adjacent bucket asks < $1?
    → If yes: guaranteed +EV, pure arb
    → If no: not profitable (vig consumes the edge)

  Strategy B (Pace Prediction):
    → EVALUATE: Does our model find >3% edge in any bucket?
    → Key: we have REAL-TIME xTracker data, market may lag 5-15 min
    → Overdispersion means Poisson model needs correction

  Strategy C (Early Entry):
    → EVALUATE: Can we buy at 1-2¢ in newly opened markets?
    → Best window: first 2 hours of market creation
    → Historical hit rate determines expected payout
    """)
