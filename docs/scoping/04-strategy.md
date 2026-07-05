# 04 — Strategy v2: Maker-Only Quoting for Political Markets

The v1 strategy is penny-jumping with an after-the-fact stop loss. v2 replaces
it with a quoting engine built around four ideas:

1. a **fair value estimate** derived purely from market microstructure (no
   external data in this phase — see 07 for the future feed layer),
2. **inventory-skewed, volatility-scaled quotes** that never cross the spread,
3. **liquidity rewards as an explicit term in the objective**, not a boolean
   filter,
4. **regime detection** that decides when *not* to quote — which is where most
   of the money is saved.

Strategy code is a pure function `(BookState, Inventory, Params, Clock) ->
TargetQuotes`, unit-testable and replayable (see §9).

## 0. The market we're fitting

Political markets on Polymarket have a specific microstructure profile:

- **Binary, bounded [0,1]**, usually inside **neg-risk event groups** (multi-
  candidate events where Σ YES = 1 by construction).
- **Long-dated with punctuated equilibrium**: weeks of low-vol mean-reversion
  interrupted by violent news repricing (debates, indictments, dropouts,
  election nights). The flow between events is heavily retail/directional
  (favorable for a maker); the flow *during* events is fast and toxic.
- **Early-resolution risk**: a candidate dropping out gates a market to 0
  instantly. There is no external feed to warn us in v2 — microstructure
  (sweeps, book evaporation) is the alarm, and size caps are the survival
  mechanism.
- Depth is deep at the touch on flagship markets, thin on down-ballot ones —
  parameters must scale with observed book depth, not fixed constants.

Everything below is designed against this profile.

## 1. Fair value (FV) engine

All inputs are local: the book we maintain from the WS and the trade tape.

- **Microprice**: depth-weighted mid over the top K levels (K≈3), i.e. mid
  pulled toward the thin side. Robust to size-1 dust orders via per-level
  minimum-size filtering (keep v1's `find_best_price_with_size` idea, tuned by
  observed depth instead of hardcoded 100/20 shares).
- **Flow adjustment**: EWMA of signed aggressor volume (from `last_trade_price`
  /trade events) over ~1–5 min nudges FV in the direction of persistent flow.
  Political markets trend on news; leaning with flow reduces adverse fills.
- **Cross-outcome consistency (neg-risk)**: Σ of YES microprices across the
  event should ≈ 1. Persistent deviation → books dislocated (news repricing in
  progress) → contributes to regime score (§5); large deviation is also the
  trigger for the optional arb module (§7).
- **Clamping**: FV is smoothed (short EWMA) and clamped against jumps unless
  the jump is confirmed by trades, not just quote flicker.

Explicitly *not* an input in v2: polls, news, other venues (see 07).

## 2. Volatility & toxicity engine

Replaces the spreadsheet's hour-stale "3_hour volatility" with live estimates:

- **Realized vol**: EWMA of squared FV returns at three horizons (~10s, ~1m,
  ~15m), computed on the WS stream. σ_short drives spread width; the
  short/long ratio drives regime detection.
- **Sweep detector**: single aggression that consumes ≥N levels or moves FV by
  ≥X ticks → immediate event flag (§5).
- **Markout tracker** (self-tuning core): for every one of our fills, record
  FV at +30s and +5m. Per-market EWMA of markout = realized adverse-selection
  cost. Consistently negative markouts automatically widen that market's
  spread / reduce its size via a toxicity multiplier. This is how the bot
  learns "this market eats me" without any human or external data.

## 3. Quote construction (maker-only)

### 3.1 Reservation price and half-spread

```
skew      = γ · σ_short · (q / q_max)                # in price units
r         = FV − skew                                # reservation price
δ         = max(δ_min,  c_vol·σ_short + c_tox·toxicity)
bid_raw   = r − δ ;  ask_raw = r + δ
```
- `q` = net inventory in the YES token (NO inventory counts negative),
  `q_max` = per-market cap. Long inventory pushes both quotes down: buy
  cheaper, sell more eagerly. This single mechanism replaces v1's pile of
  size-gating special cases.
- Fees: on CLOB V2 **makers pay zero** — no maker fee term in δ. Taker fees
  (politics 1.00%, per-market `feeSchedule` from the catalog, 03) matter to
  us twice: they fund the **maker rebates** income term (§4), and they enter
  the cost model of the optional set-arb module (§7) only.
- All prices then snap to tick and go through **placement logic**:

### 3.2 Placement: join, don't jump

- Default: place at the better of (raw price, one tick behind the touch) —
  i.e. **join the level or sit behind it**; jump the queue (improve the touch)
  only when `FV − best_ask` / `best_bid − FV` edge exceeds tick + costs. v1
  penny-jumps unconditionally, which wins queue position precisely when the
  price is about to be wrong.
- **Never cross**: candidate bid ≥ best_ask ⇒ reprice to best_ask − tick (and
  symmetric for asks), validated against the live book at send time. Enforced
  at the exchange too: **every quote is a Post-Only order** (added to CLOB
  Jan 2026, GTC/GTD — 03), which rejects rather than takes. Maker-only is a
  property of the system, not a convention.
- **Min edge vs FV**: bid ≤ FV − δ_edge_min always; we never pay through fair
  value for queue position or rewards.
- **Layering**: optionally split size across 2–3 levels per side (touch-join +
  deeper levels). Sweeps fill the deep levels at prices that already include
  the move; layered in-band size also raises the reward score (§4).
- **Churn control**: reprice only if |target − live| > reprice_ticks or size
  drift > 15%; batch cancel+place; respect the rate budget (03). Queue
  position is an asset — don't burn it for sub-tick prettiness.

### 3.3 Two-token quoting and the merge loop

On Polymarket, BUY NO @ q is economically SELL YES @ 1−q, but it is
collateralized by USDC rather than by YES inventory. v2 makes the **BUY-YES +
BUY-NO pair the canonical two-sided quote**:

- Both quotes are bids (USDC-collateralized) → we can quote two-sided with
  zero inventory, from day one, on both sides of the reward band.
- When both fill: hold YES @ p and NO @ q with p + q < 1 → **merge** pair back
  to 1 USDC. Realized edge = 1 − p − q, captured without ever selling. The
  merge (native Python, 03) runs opportunistically in the background.
- When inventory accumulates on one leg, exits are dual-routed, still maker:
  (a) keep/raise the opposite-token bid (merge exit), or
  (b) place a SELL limit on the held token above FV.
  The quoter maintains whichever route has the better expected time-to-fill ×
  price; often both, sized to not double-exit.

### 3.4 Sizing

- Base size per market from config; scaled down by toxicity, by inventory
  utilization (q/q_max), and near end-date (§6).
- Respect `orderMinSize`; low-price multiplier logic from v1 (more shares when
  price < 0.10) is replaced by sizing in **USDC notional**, constant per quote
  regardless of price level.
- No hardcoded 0.1–0.9 price band: quote anywhere the reward band and risk
  checks allow, but size shrinks near the boundaries where payoff asymmetry is
  extreme (long-shot bias zone; near-certain markets pay ~nothing to make).

## 4. Rewards and rebates as an objective

Two live income programs (03 §3), both maker-side, both enter the objective:

- **Liquidity rewards** (same family v1 targeted, confirmed live 2026):
  per-market daily rate, sampled ~per minute; score `S = ((v − s)/v)²` per
  order (s = distance from the dust-filtered *adjusted midpoint*, v =
  max_spread), min-size gate, two-sided rule
  `Q_min = max(min(Q_one, Q_two), max(Q_one/c, Q_two/c))` with c = 3.0, and —
  important — **when mid < 0.10 or > 0.90 only double-sided liquidity scores
  at all**. The formula already lives in v1's scanner (`add_formula_params`);
  v2 moves it into the strategy as a live utility term.
- **Maker rebates** (new Jan 2026): ~25% of taker fees collected in politics
  markets is redistributed daily to that market's makers pro-rata. Unlike
  rewards (paid for *resting* in-band), rebates are paid for *being filled* —
  they directly subsidize adverse selection and shift the optimizer toward
  tighter quoting in fee-enabled markets with heavy taker flow.

```
utility(placement) = E[spread capture] + E[reward $/day at this placement]
                     + E[rebate | fill] − E[adverse selection | regime]
                     − inventory penalty
```

Consequences the optimizer discovers on its own:
- **Quiet regime** → sit deeper inside the band with more size (reward-dense,
  low fill probability, low AS cost) — "farming posture".
- **Hot regime** → rewards can't compensate expected AS loss → widen beyond
  the band or pull entirely. v1 could never do this; its reward check was a
  one-way "must be inside band" constraint that *forced* it to quote tight
  exactly when it shouldn't.
- **Two-sidedness**: the Qmin rule (and the hard double-sided requirement at
  extreme mids) pays for balanced quoting — another reason the
  BUY-YES/BUY-NO pair posture (§3.3) is the default; it keeps both sides
  in-band even while carrying inventory.
- Income accounting: actual reward + rebate payouts pulled daily (03) and
  attributed per market, so the utility model's estimates are calibrated
  against reality instead of drifting.

## 5. Regime detection (when not to quote)

Per-market state machine, evaluated on every quoter wake:

| Regime | Trigger (any) | Behavior |
|---|---|---|
| QUIET | default | farming posture: in-band, layered, full size |
| TRENDING | flow EWMA persistent one-sided; σ_short/σ_long elevated | lean FV with flow, widen δ, half size |
| EVENT | sweep detector; FV jump > J ticks; neg-risk Σ dislocation; book depth evaporates | **pull all quotes**, cooloff T_c (~30–120s), re-enter at 2–3× δ decaying back to normal |
| REDUCE_ONLY | inventory ≥ hard cap; end-date proximity; risk manager order | exit quotes only |
| HALTED | WS stale > T; market flagged closed/`acceptingOrders=false`; kill switch | cancel all, no quoting |

The EVENT → re-enter-wide → decay pattern replaces v1's "stop-loss then sleep
4 hours via JSON file". Cooldowns are seconds-to-minutes and price-aware, not
hours and blind.

## 6. Inventory, exits, and lifecycle risk — without taker orders

Maker-only exit means **we cannot rely on being able to get out**. The
controls compensate:

- **Soft cap `q_soft`**: skew (§3.1) already leans quotes; beyond q_soft the
  adding side is pulled entirely, exit side gains urgency: exit price decays
  from FV + δ toward one tick above best bid over τ_urgency (still maker,
  never crossing). Urgency accelerates if FV drifts against the position.
- **Hard cap `q_max`**: reduce-only. Sizing (§3.4) makes approaching q_max
  progressively harder, so the hard stop is rarely the active constraint.
- **No cost-basis anchoring**: v1 refused to ask below avgPrice, converting
  losses into resolution lotteries. v2 prices exits off FV and urgency only;
  cost basis is reporting, not strategy.
- **Merge always-on**: min(YES, NO) ≥ threshold → merge to USDC (frees
  capital, realizes locked edge, zero market impact).
- **End-date ladder** (from catalog metadata): T−D days → size taper begins;
  T−H hours → REDUCE_ONLY; T−S → HALTED + cancel. Political markets also
  resolve early: the market WS now pushes **`market_resolved` / `new_market`
  events** (03 §5) — instant halt on resolution — with catalog refresh
  (closed/`acceptingOrders` flags) and the EVENT regime as backstops.
- **Per-market and global risk** (RiskManager, 02): market notional cap,
  neg-risk **event-group worst-case-loss cap** (multiple candidates in one
  event are one bet, not N), total exposure cap, daily realized-loss kill
  switch (halts quoting, keeps cancel/exit capability), stale-data halt.

## 7. Neg-risk structural opportunities (optional module, off by default)

Political events are neg-risk groups; the structure occasionally gifts money:

- **Set arbitrage**: if Σ best-asks of all outcomes < 1 − ε, buy the set
  (maker where possible, but this is the one place taker math is ever
  justified — behind a config flag, default off, consistent with the
  maker-only policy).
- **NegRiskAdapter conversions**: NO(i) sets convert to YES(others) + USDC —
  enables inventory rebalancing across outcomes without trading. Scoped in 03
  (§contracts); implementation phase 4+.
- Both are opportunistic add-ons; core PnL is quoting + rewards. Scoped now so
  the state model (event-group awareness) is built in from day one.

## 8. Parameters

`config/strategy.toml` holds named profiles (replaces the Hyperparameters
sheet); `markets.toml` maps markets → profile + overrides (05 has schemas).
Illustrative:

```toml
[profiles.political-longdated]
gamma            = 0.5     # inventory risk aversion (skew strength)
delta_min_ticks  = 2
c_vol            = 1.2     # spread per unit short-vol
c_tox            = 2.0     # spread per unit toxicity score
q_max_usdc       = 500     # hard inventory cap, notional
q_soft_frac      = 0.6
layers           = 2
reprice_ticks    = 2
debounce_ms      = 200
event_cooloff_s  = 60
end_date_taper_d = 7
reduce_only_h    = 24
```

Every v1 magic number (0.005 reprice, 250 cap, 0.95/0.97/1.01, 15s, 0.1–0.9
band, `max_size*2`) either becomes a named documented parameter or is deleted
by design. Hot-reload via watchfiles; changes apply on next quoter wake, no
restart.

## 9. Simulation, paper trading, and measurement

The strategy is only "much better" if we can prove it. Three rungs:

1. **Replay backtest** (`polymaker sim replay`): the journal (02) captures raw
   WS streams; the sim reconstructs books and runs the strategy with a queue-
   position fill model — conservative mode fills our order only when the tape
   prints *through* our price; optimistic mode fills pro-rata at the touch.
   Truth lies between; both are reported. Reward income is computed from the
   scoring formula on our simulated quotes. Start capturing journals from the
   moment Phase 2 lands, so weeks of political-market data exist before the
   strategy ships.
2. **Paper mode** (`polymaker run --paper`): full live pipeline, orders
   journaled but not posted; fills simulated from the live tape. The gate for
   live capital.
3. **Live KPIs** (05 §status): per-market markout curves (+30s/+5m), fill
   ratio, two-sided in-band uptime (the reward KPI), reward $ vs estimate,
   realized/unrealized PnL, inventory duration, EVENT-regime frequency.

Acceptance criteria to go live (Phase 4 gate, see 06): paper-mode ≥ 2 weeks on
≥ 10 political markets with (a) positive net PnL including simulated rewards
under the **conservative** fill model, (b) average +5m markout > −0.5 tick,
(c) zero risk-limit breaches.

## 10. Explicit non-goals in v2 (deferred to 07)

- External data: polls, news, social monitors, other venues (Kalshi et al).
- Taker execution of any kind (except the flagged neg-risk set-arb, default off).
- Cross-event statistical arbitrage.
- Sports/crypto-specific logic — the engine is generic, but tuning and the
  selector target political markets first.
