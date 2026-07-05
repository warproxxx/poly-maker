# 02 — v2 Architecture

Single async Python process, local-file config, typed state, no threads, no
Google, no Node. Everything the bot needs to run lives in the repo directory.

## Design principles

1. **One event loop.** All I/O is async. Anything blocking (order signing is
   CPU-trivial; EIP-712 signing is ~1ms) stays inline; anything slow-blocking
   that can't be made async is banished to `asyncio.to_thread` — but the goal
   is zero such call sites.
2. **Websocket-first, REST-reconcile.** The WS feeds are the source of truth
   for books, orders, and fills in real time. REST is used for (a) startup
   snapshots, (b) periodic drift reconciliation, (c) actions. Never poll REST
   for something the WS already pushes.
3. **Desired-state reconciliation.** The strategy never "places an order"; it
   emits a *target quote set* per market. The execution layer diffs targets
   against live open orders and issues the minimal cancel/place set, applying
   tolerances (don't churn for sub-tick / sub-10% size changes) and rate-limit
   budgets. This is the v1 `should_cancel` instinct, made a first-class layer.
4. **Local-first ops.** Config = files in the repo. State = SQLite. Dashboards
   = CLI. An operator with a laptop and the repo can run, inspect, and tune
   everything with no external accounts beyond the Polymarket wallet.
5. **Deterministic and testable.** Strategy is a pure function
   `(BookState, Inventory, Params, Clock) -> TargetQuotes`. That makes replay
   backtesting and unit tests trivial and is the enabler for 04-strategy.

## Process layout

```
                    ┌────────────────────────────────────────────┐
                    │                 polymaker run              │
                    │                                            │
  Gamma REST ──────▶│ MarketCatalog (refresh ~60s, metadata)     │
                    │                                            │
  CLOB market WS ──▶│ MarketDataService                          │
                    │   └─ per-market OrderBook (seq/hash check) │
  CLOB user WS ────▶│ UserStream                                 │
                    │   └─ fills / order lifecycle events        │
                    │                                            │
                    │ StateStore (positions, open orders, PnL)   │
                    │   ▲ WS events        ▲ REST reconcile      │
                    │                                            │
                    │ StrategyEngine                             │
                    │   └─ per-market Quoter task (debounced)    │
                    │        emits TargetQuotes                  │
                    │                                            │
                    │ RiskManager (pre-trade gates, kill switch) │
                    │                                            │
                    │ ExecutionGateway                           │
                    │   ├─ order signer (EIP-712, local)         │
                    │   ├─ REST client (async, rate budgeted)    │
                    │   └─ reconciler (target vs live diff)      │
                    │                                            │
                    │ Merger (YES+NO -> USDC, web3.py native)    │
                    │                                            │
                    │ Persistence: SQLite + JSONL event journal  │
                    │ Telemetry: structlog -> console/file       │
                    └────────────────────────────────────────────┘
```

### Component responsibilities

**MarketCatalog** — market metadata (tokens, tick size, neg-risk flag, reward
params, fees, end date) fetched from Gamma/CLOB REST (see 03). Refreshed on a
slow timer, cached in SQLite. Nothing in the hot path ever awaits this.

**MarketDataService** — owns the market WS connection(s). Maintains one
`OrderBook` per subscribed market: `SortedDict` bids/asks (keep v1's approach),
YES-canonical with NO-side views derived. Handles: snapshot on subscribe,
`price_change` deltas, `tick_size_change`, book-hash verification when
available, and reconnect-with-resnapshot. Exposes sync accessors (microprice,
depth-within-band, imbalance) — pure reads, no awaits — plus an
`asyncio.Event`-style dirty flag per market that wakes the Quoter.

**UserStream** — user WS channel: order placements/cancels/matches and trade
status transitions (MATCHED → MINED → CONFIRMED / FAILED). Feeds StateStore.
Replaces v1's `performing` dicts with an explicit per-order/per-trade state
machine (see below).

**StateStore** — single owner of positions and open orders. In-memory, typed
(dataclasses), persisted to SQLite on change (WAL mode; writes are µs-cheap).
Three inputs, one arbitration rule:
- WS fill events apply immediately (optimistic),
- REST reconciliation (every ~30s, and on demand after anomalies) corrects
  drift *only* for tokens with no in-flight trades,
- on-chain balance is consulted only by the Merger before merging.
This is v1's `performing`/`last_trade_update`/`avgOnly` logic, but as one
explicit component with tests instead of three dicts and a timeout.

**StrategyEngine / Quoter** — one lightweight task per market. Loop:
```
wait for (book dirty | fill | timer tick | param change), coalesced
debounce: recompute at most once per N ms (default 200ms), immediately on fill
compute TargetQuotes = strategy(book, inventory, params, clock)   # pure
hand to RiskManager -> ExecutionGateway
```
No lock held during I/O; the Quoter never awaits network calls itself.

**RiskManager** — pre-trade checks (per-market notional cap, global exposure
cap, neg-risk group cap, max open order value, price sanity band vs recent
mid), plus global circuit breakers (drawdown kill switch, WS staleness halt,
API error-rate halt). Owns the "reduce-only" and "halt" market modes. Detailed
policy in 04-strategy.md §Risk.

**ExecutionGateway** — the only component that talks to the CLOB REST API for
actions. Async HTTP (httpx), local EIP-712 signing (V2 order format), a
token-bucket rate budgeter tuned to documented API limits (03), batch
place/cancel endpoints, **post-only on every quote**, and the target-vs-live
reconciler with churn tolerances. Also owns the **exchange heartbeat** (03):
a ~5s keepalive; if the process dies or partitions, the exchange cancels all
our orders within ~10s — the dead-man switch a maker-only bot must have.
Every request/response is journaled.

**Merger** — pure-Python replacement for poly_merger (03 §Merge). Triggered by
StateStore when min(YES,NO) ≥ merge threshold; runs as a low-priority task,
never blocks quoting.

**Persistence** — `state.db` (SQLite): market catalog cache, positions, order
history, fills, PnL marks, risk events. `journal/*.jsonl`: append-only raw
event log (WS messages in, orders out) — this is also the capture format the
backtester replays (04 §Simulation).

**Telemetry** — structlog JSON to file + human console; `polymaker status`
CLI reads SQLite for positions/PnL/quotes (05). Optional later: Prometheus
exporter. No Sheets dashboards.

## Order/trade state machine

Replaces `performing` + timestamps + 15s cleanup:

```
Order:  DRAFT -> SIGNED -> POSTED -> LIVE -> {PARTIALLY_FILLED} -> DONE
                              └─ REJECTED            └─ CANCELED
Trade:  MATCHED -> MINED -> CONFIRMED
             └────────────-> FAILED (position rolled back, reconcile forced)
```
Timeouts are per-transition (e.g. MATCHED without MINED after T → force REST
reconcile for that token) instead of one global 15s sweep.

## Package layout

```
poly-maker/
├── pyproject.toml            # uv-managed; python >=3.12
├── uv.lock
├── config/
│   ├── config.toml           # bot settings: wallet env refs, global risk, engine knobs
│   ├── strategy.toml         # named parameter profiles (replaces Hyperparameters sheet)
│   └── markets.toml          # selected markets + per-market overrides (replaces Selected Markets)
├── src/polymaker/
│   ├── cli.py                # `polymaker` entrypoint: run/scan/markets/status/flatten/...
│   ├── config.py             # pydantic-settings models, TOML load, hot-reload (watchfiles)
│   ├── catalog/              # Gamma/CLOB market discovery + scoring (05)
│   ├── marketdata/           # WS client, order book, book analytics
│   ├── userstream/           # user WS, event parsing
│   ├── state/                # StateStore, models, SQLite persistence
│   ├── strategy/             # pure quoting logic + parameter models (04)
│   ├── risk/                 # RiskManager, circuit breakers
│   ├── execution/            # signer, REST client, rate budgeter, reconciler
│   ├── merge.py              # native merge (03)
│   ├── journal.py            # JSONL event journal
│   └── sim/                  # replay backtester + paper-trading mode (04)
├── tests/
└── docs/scoping/
```

`poly_data`, `poly_utils`, `poly_stats`, `data_updater`, `poly_merger`,
`trading.py`, `main.py`, `update_markets.py`, `update_stats.py` are all
deleted once their replacements land (06 has the phasing).

## Concurrency & performance notes

- Python 3.12+ (faster asyncio, per-interpreter GIL groundwork irrelevant here
  — one loop is enough; this workload is I/O bound with tiny CPU bursts).
- `uvloop` as the event loop (free ~2-4x loop throughput on macOS/Linux).
- WS message → book update → quoter wake is all sync code on the loop; the
  only awaits in the hot path are the WS `recv` and the outbound HTTP.
- Signing: `py_order_utils`/eth-account key ops are ~1ms — sign inline, no
  executor.
- Target: event-to-order-POST latency < 50ms internally (network to Polymarket
  will dominate at ~50–150ms; colocating the box geographically near the CLOB
  (AWS us-east) is an ops choice, noted in 05).
- Memory: no gc.collect() calls; books for ~50 markets are a few MB.

## Error policy

- No bare excepts. Each component defines recoverable (log + retry with
  backoff) vs fatal (halt quoting, keep cancel capability, alert) errors.
- On any uncertainty about our own open-order/position state → freeze new
  quotes for that market, force reconcile, resume. "When confused, cancel and
  resync" is the universal recovery.
- On process crash: the exchange heartbeat has already cancelled our orders
  within ~10s; startup sequence is cancel-all (belt) → REST snapshot → resume.

## Dependency set (target)

| Purpose | Package |
|---|---|
| HTTP | httpx (async) |
| WS | websockets (current) |
| Signing/order building | **py-clob-client-v2** (V1 client is archived/dead); direct py_order_utils + eth-account if we outgrow it (03) |
| Chain (merge, balances) | web3.py 7.x |
| Config/validation | pydantic v2 + pydantic-settings, tomllib |
| Hot reload | watchfiles |
| State | sqlite3 stdlib (+ tiny DAO layer; no ORM) |
| Logging | structlog |
| CLI | typer + rich |
| Loop | uvloop |
| Dev | ruff, mypy, pytest, pytest-asyncio |

pandas/numpy leave the runtime hot path (they remain fine inside the scanner
and sim analysis). gspread, gspread-dataframe, google-auth, py-clob-client
(v1), and the entire Node/ethers runtime go; sortedcontainers stays (book).
