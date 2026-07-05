# 05 — Local Config, Market Selection, and Operations

Google Sheets currently plays four roles: config store, market database,
selection UI, and dashboard. v2 replaces each with a local equivalent. The
test: **a laptop with the repo, a `.env`, and a funded wallet is a complete
deployment.** No Google account, no service-account JSON, no second IP running
a scanner.

## 1. Configuration files (replaces Hyperparameters + Selected Markets sheets)

All TOML, all in `config/`, all validated by pydantic at load, all
hot-reloadable via watchfiles (applied at the next quoter wake; invalid edits
are rejected with a logged diff, keeping the last good config — an edit can
never crash the bot).

### `config/config.toml` — engine & account
```toml
[wallet]
# secrets stay in .env: PK, BROWSER_ADDRESS; this file only references them
signature_type = 2            # revisit after Phase 2 wallet spike (03 §1)

[engine]
debounce_ms          = 200
reconcile_interval_s = 30
heartbeat            = true    # exchange dead-man switch (03 §3)
journal              = true    # raw WS/order journal for the backtester

[risk]                         # global — per-market caps live in markets.toml
max_total_exposure_usdc   = 5000
max_event_group_loss_usdc = 1000     # neg-risk group worst-case
daily_loss_kill_usdc      = 250
ws_stale_halt_s           = 10
```

### `config/strategy.toml` — named parameter profiles
Schema in 04 §8. Profiles (`political-longdated`, `political-hot`, …) replace
the Hyperparameters sheet's `param_type` groups.

### `config/markets.toml` — the trade list (replaces Selected Markets sheet)
```toml
[[markets]]
slug     = "will-x-win-the-2028-democratic-nomination"
profile  = "political-longdated"
q_max_usdc = 800               # optional per-market overrides of the profile

[[markets]]
condition_id = "0x37a6de..."   # slug or condition_id both accepted
profile      = "political-hot"
enabled      = false           # keep the entry, stop quoting
```
The bot resolves slugs → tokens/metadata via the catalog at startup and on
reload. Adding a market while running = edit file, save; the engine
subscribes, seeds the book, starts quoting. Removing/disabling = cancel that
market's orders, unsubscribe. This is the entire "market management UI".

`.env` keeps only secrets: `PK`, `BROWSER_ADDRESS`, optional RPC URL override.
`SPREADSHEET_URL` and `credentials.json` are deleted.

## 2. Market catalog & scanner (replaces data_updater + All/Volatility Markets sheets)

`state.db` (SQLite) holds the market catalog; the scanner is a subcommand, not
a second deployment:

- `polymaker scan` — Gamma keyset sweep with server-side filters (03 §4):
  politics tag(s), active, min liquidity/volume, end-date window, rewards
  present. Enriches the shortlist with batch `/books` depth and reward-density
  estimates (the v1 `add_formula_params` math, kept) **plus the maker-rebate
  estimate** (taker-fee volume × rebate share — 03 §3). Writes to SQLite.
  Seconds per run; scheduled inside the bot process (e.g. every 15 min) —
  the "run on a different IP" advice dies with the crawl that motivated it.
- `polymaker markets` — rank/browse the catalog in the terminal (rich table):
  `polymaker markets --tag politics --min-reward 20 --max-vol-sum 20 --sort score`.
  Score = expected daily income (rewards + rebates) vs. volatility & spread
  risk — v1's `gm_reward_per_100` / `volatility_sum` composite, recalibrated.
- `polymaker markets add <slug> [--profile P]` — appends to `markets.toml`
  (file remains the source of truth; the command is a convenience editor).
- Volatility for ranking: `prices-history` coarse estimate at scan time;
  markets we quote get live WS-derived vol which supersedes it.

## 3. Runtime CLI (replaces update_stats.py + Summary sheet + eyeballing prints)

Single `polymaker` entrypoint (typer):

| Command | Purpose |
|---|---|
| `polymaker run [--paper]` | start the engine (paper mode: full pipeline, no order POSTs) |
| `polymaker status` | positions, open quotes, inventory, PnL, regime per market (reads SQLite; works while the bot runs) |
| `polymaker pnl [--daily]` | realized/unrealized PnL, reward + rebate income vs. estimates |
| `polymaker flatten [market]` | reduce-only mode (maker exits) for one/all markets |
| `polymaker cancel-all` | panic button (also runs automatically at startup) |
| `polymaker scan` / `markets` | catalog (above) |
| `polymaker sim replay ...` | backtester (04 §9) |
| `polymaker doctor` | preflight: wallet auth spike checks, pUSD balance/allowances, WS reachability, clock skew |

## 4. Observability

- **structlog** JSON logs to `logs/` + human-readable console. Every order
  decision logs its inputs (FV, σ, inventory, regime) — a quote is always
  explainable after the fact.
- **Journal** (`journal/*.jsonl`): raw WS in / orders out. Feeds the
  backtester and post-mortems.
- **SQLite** is the queryable operational record: fills, orders, PnL marks,
  reward payouts, risk events. Any dashboard we want later (Grafana, a small
  web page) reads this — no scoping dependency on it now.
- **Alerting (minimal, phase 4)**: kill-switch trips, WS-stale halts,
  reconcile divergence, heartbeat failures → log at CRITICAL + optional
  webhook URL in config (generic; Discord/Telegram/ntfy all take a POST).
- KPI set defined in 04 §9 (markouts, two-sided in-band uptime, fill ratio,
  income vs. estimate).

## 5. Deployment & runtime ops

- **uv end-to-end** (already adopted; finish the job): `requires-python =
  ">=3.12"`, refreshed lock, `uv run polymaker ...`, dev group with ruff,
  mypy, pytest, pytest-asyncio. Delete the 3.9 pin.
- **Placement**: any always-on Linux box; latency to the CLOB (AWS us-east
  region) is the one infra knob that matters for queue position — a small VPS
  in us-east-1 beats a laptop on wifi. Not required for correctness.
- **Supervision**: systemd unit example in the README (`Restart=always`);
  startup sequence is cancel-all → snapshot → resume, so a restart is always
  safe. The exchange heartbeat covers the gap between death and restart.
- **CI (GitHub Actions)**: ruff + mypy + pytest on PR. No deploy pipeline
  needed for a single-operator bot.
- **State backup**: `state.db` + `config/` are the whole world; journal grows
  ~MBs/day per market — rotate + optionally compress with age.

## 6. Security notes

- `PK` only ever in `.env` (gitignored) / environment; never in TOML, logs,
  or SQLite. Log wallet addresses truncated.
- The CLI never prints secrets; `doctor` verifies without echoing.
- Dependencies pinned via uv.lock; renovate/dependabot optional later.
