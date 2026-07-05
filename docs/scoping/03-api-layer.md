# 03 — API Layer: V1 → V2 Migration

Polymarket executed a **hard, non-backward-compatible cutover to CLOB V2 on
April 28, 2026**. V1-signed orders stopped working that day; the legacy
`py-clob-client` this repo pins (0.28.0; latest 0.34.6) was **archived May 11,
2026** and cannot trade against V2. There is no incremental path — the API
layer is a rewrite, which is exactly what this scoping assumes.

Primary sources: [V2 migration guide](https://docs.polymarket.com/v2-migration),
[changelog](https://docs.polymarket.com/changelog),
[llms.txt doc index](https://docs.polymarket.com/llms.txt).

## 1. What changed in CLOB V2

| Area | V1 (this repo) | V2 (target) |
|---|---|---|
| Base URL | `https://clob.polymarket.com` | same URL, new backend |
| Order struct | `nonce`, `feeRateBps`, `taker` fields | removed; adds `timestamp` (ms), `metadata`, `builder`; fees set by protocol at match time |
| EIP-712 domain | Exchange version "1" | version **"2"**, new verifying contracts |
| Exchange contracts | `0x4bFb41d5...` / neg-risk `0xC5d563A3...` | CTF Exchange V2 `0xE111180000d2663C0091e4f400237545B87B996B`; Neg Risk CTF Exchange V2 `0xe2222d279d744050d28e00520010520000310F59` |
| Collateral | USDC.e (`0x2791Bca1...`) | **pUSD** (ERC-20, 1:1 USDC-backed); API traders wrap via the Collateral Onramp contract and set pUSD allowances |
| Auth | L1 EIP-712 + L2 HMAC headers | **unchanged**; existing API keys carried over |
| Fees | fields existed, mostly zero | **makers pay zero**; taker-only fees `fee = C · feeRate · p·(1−p)` per category (Politics 1.00%, geopolitics/world-events free); live rate from each market's `feeSchedule` — never hardcode |
| Neg-risk | PartialCreateOrderOptions flag | fully supported; neg-risk orders sign against the neg-risk V2 contract (SDK handles) |

### Consequences for us
- **Wallet/allowance setup is a new ops step**: wrap USDC→pUSD via the onramp,
  approve pUSD to the V2 exchange (buys) and conditional tokens (sells).
  Balance checks read pUSD, not USDC.e (v1's hardcoded USDC contract in
  `polymarket_client.py:78` dies).
- **Signature-type risk**: v1 runs `signature_type=2` (Polymarket proxy/Safe
  funder). `py-clob-client-v2` has a cluster of open auth bugs around
  signature types 2/3 and Safe wallets (issues #70/#85/#87/#90/#91) and
  "invalid order version" migration confusion (#92). **Phase 2 starts with a
  wallet-auth spike**: place/cancel one order with our exact wallet setup
  before building anything on top. Fallback: EOA wallet (signature_type=0).
- Fine ticks now exist (0.001, even 0.0025); `tick_size_change` events (fires
  crossing 0.96/0.04) must be handled live or orders start rejecting.

## 2. Client library choice

| Option | Status | Call |
|---|---|---|
| `py-clob-client` 0.34.x | archived, V1-only | **dead — remove** |
| **`py-clob-client-v2`** (1.0.2, Jul 2026) | official successor, active | **use for Phase 2.** Sync-only → wrap calls we need in a thin async adapter, or use it only for signing/building and POST via httpx ourselves |
| `polymarket-client` (py-sdk) | official unified SDK, **beta**, sync+async | watch; adopt when stable if its async client is solid — re-evaluate at Phase 2 start |
| Direct: `py_order_utils` + eth-account + httpx | max control | fallback if the v2 client's sync-ness or Safe bugs block us; order signing is a well-documented EIP-712 struct |

Decision: **start with `py-clob-client-v2` for order building/signing, own the
HTTP layer with httpx** (async, connection-pooled, our rate budgeter, our
retries). The signing code is pure CPU and composes fine with our loop. This
also keeps us one small step from going fully direct if the SDK disappoints.

## 3. Endpoints v2 uses (and the v1 habits they replace)

### Trading (CLOB, L2 auth)
- `POST /order` — single post-only/GTC/GTD order.
- **`POST /orders` (batch, ≤15)** — quote both tokens × layers in one request;
  v1 placed orders one blocking call at a time.
- `DELETE /orders` (≤1,000 ids) — targeted mass cancel; replaces v1's
  cancel-all-per-asset churn.
- `DELETE /cancel-market-orders`, `DELETE /cancel-all` — recovery paths
  (startup, kill switch).
- **`POST /heartbeats`** (Jan 2026): opt-in dead-man switch — miss a ~10s
  heartbeat window and the exchange cancels all our orders. **Mandatory for
  v2**: a maker-only book of stale quotes after a crash/network partition is
  the biggest tail risk we have. ExecutionGateway sends one every ~5s.
- **Order types**: GTC, GTD, FOK, FAK, and **Post-Only (Jan 2026, GTC/GTD
  only)** — the enforcement mechanism for our maker-only mandate (04 §3.2);
  every quote goes out post-only.

### Market data (REST, no auth)
- `GET /book`, **`POST /books` (batch)**, `/midpoint(s)`, `/price(s)` —
  snapshots at startup/resync. The scanner uses batch `/books` instead of v1's
  one-book-per-market crawl.
- `GET /prices-history` — still exists; only used by the scanner for coarse
  historical vol (live vol comes from our own WS-derived estimates).
- `GET /sampling-markets` — replaced by Gamma for discovery (below); CLOB
  market metadata (`min_incentive_size`, `max_incentive_spread`, tick size,
  neg_risk) still fetched per selected market as authoritative.

### Rewards & earnings
- Liquidity-rewards program is live and mechanically the same family as v1:
  score `S = ((v−s)/v)²`, adjusted midpoint (dust-filtered), two-sided
  `Q_min = max(min(Q_one,Q_two), max(Q_one/c, Q_two/c))` with c=3.0,
  per-minute sampling, daily payout, $1/market minimum, **double-sided
  quoting required to score at all when mid < 0.10 or > 0.90**.
  [docs](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
- **Maker Rebates Program (new, Jan 2026)**: ~20–25% of taker fees collected
  in fee-enabled categories (politics 25%-ish) rebated daily to that market's
  makers pro-rata. A second income stream v1 never knew about — enters the
  strategy utility function (04 §4) and the market selector's scoring (05).
- Earnings actuals: rewards user endpoints (v1's `poly_stats` hit a
  polymarket.com internal API with L2 headers; v2 uses the documented rewards
  endpoints) — pulled daily into SQLite for calibration.

### Relayer (only if we keep Safe-style wallets)
- Relayer `POST /submit` now returns `{transactionID, state}` — poll
  `GET /transaction` for the hash. Affects the merge flow if executed via
  proxy wallet (§6).

## 4. Market discovery: Gamma API (the "better, faster market list")

v1's scanner crawled `sampling-markets` page by page then fetched **one order
book + one price history per market** — thousands of sequential calls, ~hourly
cadence, results pasted into Google Sheets. v2 replaces the whole pipeline
with Gamma (`https://gamma-api.polymarket.com`, no auth):

- **`GET /markets/keyset`** (Apr 2026, cursor-paginated, limit ≤100; the
  offset endpoints are slated for deprecation — build keyset-first) with
  server-side filters: `active`, `closed` (defaults false now), `tag_id` (+
  `related_tags`) for **politics**, `liquidity_num_min`, `volume_num_min`,
  `end_date_min/max`, `rewards_min_size`.
- One response row already carries what v1 burned two extra calls per market
  to compute: `bestBid`, `bestAsk`, `spread`, `liquidityNum`, `volumeNum` (+
  24h/1wk/1mo), `rewardsMinSize`, `rewardsMaxSpread`, `feeSchedule`/`feesEnabled`,
  `orderPriceMinTickSize`, `orderMinSize`, `negRisk`, `clobTokenIds`,
  `conditionId`, `endDate`.
- Tag IDs are numeric — resolve once via `GET /tags`, cache in SQLite.
- A politics-filtered scan is **a handful of paginated requests (seconds)**
  vs. v1's ~hour; run it every few minutes if we like. Rate limits are ample
  (Gamma 4,000 req/10s global, `/markets` 300/10s).
- Depth/reward-optimality checks for the shortlist only: batch `POST /books`
  on candidate tokens.
- Event grouping for neg-risk risk caps comes from `GET /events/keyset`
  (markets nest their event; events give us the sibling-outcome structure).

## 5. WebSockets

Same hosts as v1 (`wss://ws-subscriptions-clob.polymarket.com/ws/{market,user}`)
— **URLs unchanged by the V2 cutover** — but the payloads moved:

- **Market channel**: subscribe with
  `{"assets_ids": [...], "type": "market", "custom_feature_enabled": true}`.
  Events: `book` (snapshot), `price_change` (**schema changed Sept 2025 —
  now includes best_bid/best_ask; re-derive the parser from current docs**),
  `tick_size_change`, `last_trade_price` (includes `fee_rate_bps`), and with
  the custom flag: **`best_bid_ask`, `new_market`, `market_resolved`**.
  `market_resolved` is a free early-resolution alarm for the risk ladder
  (04 §6). The old ~100-token subscription cap was removed (May 2025).
- **User channel**: auth payload as v1, but scope subscriptions with
  `"markets": [condition_ids]`. `order` + `trade` events, trade status ladder
  `MATCHED → MINED → CONFIRMED / RETRYING / FAILED` (maps directly onto the
  02 state machine).
- **Ping/pong**: reportedly server pings every 5s with a 10s pong deadline —
  not confirmed on the official channel pages; **verify empirically** and make
  keepalive parameters config, not constants.
- **RTDS** (`wss://ws-live-data.polymarket.com`, Sept 2025): separate
  real-time data service — `activity` (all trades/matches platform-wide),
  `comments`, crypto/equity prices, `clob_user` topic. Not needed for the
  core loop; the `activity` topic is a cheap future enhancement for
  cross-market flow signals (still Polymarket-internal data, so it doesn't
  violate the no-external-feeds rule; noted in 07).

## 6. On-chain layer (merge + balances) — Node.js dies

- **Merger rewrite in Python** (web3.py 7.x, which the repo already ships):
  `mergePositions` on the ConditionalTokens contract (plain markets) or the
  NegRiskAdapter (neg-risk), exactly what `poly_merger/merge.js` does through
  ethers v5. For proxy/Safe wallets, execute through the Safe with
  `safe-eth-py`, or via Polymarket's relayer client — decide in the Phase 2
  wallet spike (same spike as §1 signature-type risk; if we land on an EOA,
  the Safe code path disappears entirely).
- **pUSD questions to resolve in the spike** (docs are young): pUSD token
  address; whether V2-era markets' CTF collateral is pUSD (merge returns pUSD)
  and whether pre-V2 political markets still merge to USDC.e; onramp
  wrap/unwrap mechanics and gas. The Merger and the balance sheet code treat
  collateral as config-driven per market, not a constant.
- Balances: pUSD ERC-20 for cash, CTF `balanceOf` for positions (unchanged),
  data-api `/positions` for cross-checks (rate limit 150/10s — reconcile use
  only).

## 7. Rate budget (per official limits, Jun 2026)

Relevant ceilings: `POST /order` 5,000/10s burst; batch `POST /orders`
2,000/10s; `DELETE /orders` 2,000/10s; `cancel-market-orders` 1,500/10s;
books/prices 500–1,500/10s; Cloudflare throttles (queues) rather than 429s —
so the real risk is **silent latency injection**, not errors.

For ~50 markets × 2 tokens × 2 layers ≈ 200 live orders, a full re-quote is
~14 batch calls — nothing. The ExecutionGateway still gets a token-bucket
budgeter (config: fraction of documented limits, default 25%) because
throttle-queueing would silently add latency exactly when the market is
moving; the budgeter surfaces pressure as a metric + shed-load policy
(skip reprices whose edge < threshold first) instead.

## 8. Out of scope

- **Polymarket US** (docs.polymarket.us): separate CFTC-regulated venue,
  separate API/auth/SDKs. Not targeted; noted for the future in 07.
- Builder attribution (`builderCode`): not needed unless we monetize order
  flow; field exists in the order struct if ever wanted.

## 9. Open items to verify at implementation time

1. WS ping/pong contract (empirical test).
2. `py-sdk` maturity re-check at Phase 2 start (async client + WS coverage).
3. pUSD address / onramp mechanics / merge collateral (wallet spike).
4. Exact current `price_change` + `best_bid_ask` payload schemas.
5. Maker-rebate payout currency (USDC vs pUSD) — accounting only.
6. Whether heartbeats interact with batch cancels/cancel-all on reconnect.
7. Signature type 2 (proxy/Safe) health in `py-clob-client-v2` (issue tracker
   before the spike).
