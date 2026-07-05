# 01 — Current State Audit (v1)

Honest inventory of what exists today, what's broken, and what dies in v2.
This is the baseline the rest of the scoping docs build on.

## What v1 is

A single-process Python market maker (~2,700 LOC) plus a separate market-scanner
script, glued together through a **Google Sheet** that acts as config store,
market database, and dashboard at the same time.

```
main.py                 entry point: REST polling thread + 2 websockets
trading.py              the entire strategy (perform_trade, 470 lines)
update_markets.py       scanner: crawls all markets, writes to Google Sheets hourly
update_stats.py         writes account stats/earnings back to Google Sheets
poly_data/              client wrapper, global mutable state, WS handlers, book
poly_utils/             Google Sheets access (incl. a read-only CSV-export hack)
data_updater/           scanner internals (reward math, volatility fetch)
poly_stats/             earnings/positions summary -> Sheets
poly_merger/            Node.js subprocess to merge YES+NO via Gnosis Safe
positions/*.json        ad-hoc risk-off state files written next to the code
```

### Data flow today

1. `update_markets.py` (separate process, ideally separate IP) crawls
   `clob.polymarket.com/sampling-markets` page by page, then fetches **one order
   book per market** via REST plus one `prices-history` call per market to
   compute volatility — thousands of sequential REST calls per scan, ~hourly.
   Results are pasted into the "All Markets" / "Volatility Markets" sheets.
2. A human picks rows into the "Selected Markets" sheet and tunes the
   "Hyperparameters" sheet.
3. `main.py` re-reads the sheet **every 30 seconds** (network call to Google in
   the hot path), polls positions/orders REST every 5s in a background *thread*,
   and maintains order books from the market websocket in the asyncio loop.
4. Every `book`/`price_change`/user event spawns `perform_trade(market)` as a
   new asyncio task, serialized per market by an `asyncio.Lock`.

## What's structurally wrong

### Concurrency model
- **threading + asyncio mixed**: a daemon thread mutates `global_state` (dicts of
  positions/orders) while asyncio tasks read them. No coherent locking
  (`global_state.lock` exists but is essentially unused).
- **Blocking I/O inside the event loop**: `py-clob-client` and `requests` are
  synchronous. Every order placement/cancel blocks the loop — while it's
  signing + POSTing, the bot is blind to every other market's book updates.
- **`perform_trade` holds the per-market lock through a `gc.collect()` and a
  hard-coded `await asyncio.sleep(2)`** (trading.py:470). Every quote decision
  on a market therefore takes ≥2s and events pile up behind the lock. This
  alone caps reactivity at ~0.5 Hz per market in a game where queue position
  and reaction to sweeps decide profitability.
- Event storm handling is "spawn a task per WS message" — no coalescing, no
  debounce; the lock queue grows unboundedly under load.

### State management
- One module of **global mutable dicts** (`global_state.py`) shared across a
  thread and dozens of tasks. Position tracking is a merge of three sources
  (data-api REST, user WS fills, on-chain balance) reconciled with the
  `performing` set + 15-second staleness hack — a hand-rolled, race-prone
  answer to "did my fill land yet?".
- `set_order()` in `poly_data/data_utils.py:136` **overwrites both sides** of a
  token's order record with a dict containing only the side that just updated —
  the other side's `{price, size}` silently vanishes until the next 5s REST poll.
- Local order book is keyed by condition_id, stores only the YES token book,
  derives the NO view by `1 - price`. Fine in principle, but book resync after
  WS reconnect relies on the server re-sending a `book` snapshot; there's no
  sequence-gap detection or hash check (the WS actually provides a book `hash`).

### Google Sheets as infrastructure
- Config store, market DB, ops dashboard, and inter-process message bus are all
  one spreadsheet. It's rate-limited (Sheets API quota), slow (hundreds of ms
  per read), needs service-account credentials, and pulls a network dependency
  into the trading loop. The "read-only mode" fallback in
  `poly_utils/google_utils.py` literally guesses gid numbers 0–4 against a CSV
  export URL.
- The scanner and the bot communicate *through* the sheet, so market metadata
  in the hot path can be an hour stale (`row['best_bid']` used as a sanity
  reference in trading.py:356 comes from the sheet).

### Code quality
- Bare `except:` everywhere (~30 sites), `print()` as the only logging, no
  tests at all, no types, dead code left as comments, `gc.collect()` sprinkled
  as a superstition (7 call sites), `deets` reused as both the outcome list and
  the book snapshot inside the same loop (trading.py:158/197).
- `data_updater/` duplicates `poly_utils` (two `google_utils.py`, two
  `trading_utils.py` with different contents).
- Pinned to **Python 3.9** (.python-version = 3.9.18, EOL Oct 2025) and
  `py-clob-client==0.28.0`. That client line is **dead**: Polymarket cut over
  to CLOB V2 on 2026-04-28 (new order signing, new contracts) and archived
  py-clob-client — **v1 of this bot cannot place an order at all anymore**
  (see 03). This isn't a refactor of a working bot; it's a rebuild of a
  non-functional one.
- A **Node.js subprocess** (`poly_merger/`) exists solely to call
  `mergePositions` through a Gnosis Safe — a whole second runtime, package.json
  and ethers v5 dependency for one contract call that web3.py can do.

### Strategy weaknesses (why it loses money — detailed fix in 04-strategy.md)
- **Quote logic is penny-jumping**: `bid = best_bid + tick`, `ask = best_ask -
  tick`, with a couple of size-based exceptions. No fair-value estimate, no
  microprice, no inventory skew — position size only gates *whether* to quote,
  never *where*.
- **Adverse selection is handled after the fact**: the only defenses are an
  hourly 3-hour volatility number from the spreadsheet and a stop-loss that
  **crosses the spread** (sells at best bid — a taker exit, exactly what we
  want to ban) then sleeps the market for hours via a JSON file on disk.
- **Rewards are a filter, not an objective**: the scanner computes
  reward-per-100 carefully, but the live quoter only checks "is my bid inside
  the incentive band" as a boolean. Placement within the band (where the
  reward-vs-fill-risk tradeoff actually lives) is never optimized.
- Hard-coded magic everywhere: 0.1–0.9 price band, 250 share absolute cap,
  0.005 reprice threshold, 15s staleness, 0.95/0.97/1.01 ratios, `max_size*2`
  total-exposure allowance.
- Take-profit reprices only when 2% away from target; sell-side quote sits at
  `avgPrice` floor (trading.py / trading_utils.py:136) — i.e. the bot refuses
  to exit below cost, which turns losers into resolution lottery tickets.

## What's worth keeping (conceptually)

- **The two-token + merge insight**: buying YES and NO such that both fill and
  merging the pair back to USDC is a maker-only exit that never crosses the
  spread. v2 promotes this from an afterthought to a core mechanism.
- Book maintenance via `SortedDict` and the YES/NO mirror trick — cheap and
  correct.
- The desired-vs-existing order diffing idea in `send_buy_order`/`send_sell_order`
  (only cancel/replace on meaningful change) — right instinct, generalized into
  a proper reconciler in v2.
- The scanner's reward-per-$100 estimator (`add_formula_params` implements the
  official S(v,s) = ((v−s)/v)² scoring) — the math moves into v2's selector.
- The `performing` concept (in-flight fills gate REST reconciliation) — becomes
  a real state machine instead of dicts of sets.

## What dies in v2

| Component | Fate |
|---|---|
| Google Sheets (gspread, gspread-dataframe, google-auth, service accounts) | **Deleted.** Local files + SQLite (02/05) |
| `poly_merger/` Node.js + ethers + package.json | **Deleted.** Native Python Safe execution (03) |
| `update_stats.py`, `poly_stats/` (Sheets dashboards) | **Deleted.** Replaced by local status CLI/log (05) |
| `data_updater/` sampling-markets crawl + per-market book fetch | **Deleted.** Gamma API scanner, minutes → seconds (03/05) |
| `global_state.py` module-level dicts | **Deleted.** Typed state store owned by the engine (02) |
| Background REST polling thread | **Deleted.** Single asyncio loop; REST only for reconciliation (02) |
| `positions/*.json` risk files | **Deleted.** SQLite state (02) |
| Python 3.9 pin, py-clob-client 0.28 (archived, V1-only) | Upgraded: 3.12+, py-clob-client-v2 + own async HTTP (03) |
| `print()` logging, bare excepts, gc.collect() | Replaced: structured logging, real error policy (02/05) |

## Repo facts for reference

- uv is **already adopted** (uv.lock, pyproject.toml, hatchling build) — v2
  keeps uv and finishes the job: bump `requires-python` to ≥3.12, refresh all
  pins, add ruff + mypy + pytest as dev group, `src/` layout.
- Git history is shallow and healthy; no CI exists; MIT licensed; README
  already warns the v1 strategy is unprofitable.
