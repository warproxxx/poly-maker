# poly-maker (v2)

A maker-only market-making bot for **Polymarket CLOB V2**, focused on political
markets. Single async process, local-file config (no Google Sheets), typed and
tested. This is a ground-up rewrite of v1 — see [`docs/scoping/`](docs/scoping/00-overview.md)
for the design and [`docs/scoping/06-migration-plan.md`](docs/scoping/06-migration-plan.md)
for the plan. The original v1 code has been removed; see the git history (branch
`main`) if you need to reference it.

> [!WARNING]
> Market making on Polymarket is competitive and can lose money. This is a
> reference implementation and a research harness, not a guaranteed-profitable
> product. Test in `--paper` mode first; go live with small size.

## What it does

- Discovers political markets via the **Gamma API** (seconds, not the v1 hour-long
  crawl) and ranks them by reward + rebate income vs. volatility/spread risk.
- Maintains a live order book per token from the **market WebSocket**.
- Quotes **maker-only** (every order is post-only): a fair-value + inventory-skew
  strategy that posts BUY-YES and BUY-NO as the canonical two-sided quote, with
  live volatility/toxicity estimation and a regime machine that pulls quotes
  during news events. See [`docs/scoping/04-strategy.md`](docs/scoping/04-strategy.md).
- Reconciles a target quote set against live orders with churn tolerances; runs
  the exchange **heartbeat** dead-man switch; enforces risk caps and a daily-loss
  kill switch.
- Config, market selection, and state are **local files + SQLite**. An operator
  with the repo, a `.env`, and a funded wallet is a complete deployment.

## Install

Uses [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync --extra dev          # install deps + dev tools
uv run polymaker --help
```

## Configure

```bash
cp .env.example .env         # then edit: PK + BROWSER_ADDRESS (same wallet as the UI)
```

### Which wallet address?

Polymarket's current **deposit-wallet** architecture (rolled out ~June 2026)
shows several addresses in the UI, and the labels are inconsistent. What matters:

- **`BROWSER_ADDRESS` = the funder** — the *smart-contract wallet that actually
  holds your pUSD and positions*. Depending on the account it may be shown as the
  "deposit" or "developer" address; the reliable test is which one holds the
  money. `polymaker doctor` reads the balance so you can confirm.
- **`PK` = the private key of your signer** — the EOA (e.g. your MetaMask account)
  that *owns/controls* that wallet. This is a **different** address than the
  funder, and that's correct: your key signs on behalf of the wallet that holds
  the funds. (A "deployer" / factory address, if shown, is Polymarket's shared
  contract — ignore it.)

Set `signature_type` in `config/config.toml` to match how the account was made:
`3` = POLY_1271 deposit wallet (current default), `2` = older browser-wallet
Gnosis Safe, `1` = email/magic proxy, `0` = plain EOA. A wrong type fails loudly
(`polymaker doctor` / `livetest` report it). Approvals must have been granted
from the funding wallet — trading once in the UI does this. See
[`docs/scoping/03-api-layer.md`](docs/scoping/03-api-layer.md) §1/§9.

Everything else is TOML under [`config/`](config/):

- `config.toml` — wallet/engine/risk/execution settings
- `strategy.toml` — named parameter profiles (`political-longdated`, `political-hot`)
- `markets.toml` — the trade list (populated via the CLI below)

## Use

```bash
# 1. discover + rank political markets (writes to state.db)
uv run polymaker scan
uv run polymaker markets

# 2. add markets to the trade list
uv run polymaker markets-add <slug> --profile political-longdated

# 3. dry run: full pipeline against the live feed, no orders posted
uv run polymaker run --paper

# 4. preflight the wallet before going live
uv run polymaker doctor

# 5. one safe live round-trip (~$5 post-only order, placed deep and cancelled)
uv run polymaker livetest

# 6. go live
uv run polymaker run

# ops
uv run polymaker status        # positions / open orders
uv run polymaker cancel-all    # panic button
```

## Architecture

```
market WS ─▶ OrderBook ─▶ (wake) ─▶ Quoter ─▶ strategy (pure) ─▶ reconcile ─▶ ExecutionGateway
user WS   ─▶ StateStore                                         RiskManager ┘   (post-only, heartbeat)
Gamma     ─▶ Catalog/scanner ─▶ SQLite            periodic REST reconcile ┘
```

The strategy layer is a pure function `(book, inventory, params, clock) →
TargetQuotes` — deterministic and unit-tested. The engine owns all I/O and
state around it. Full component map in
[`docs/scoping/02-architecture.md`](docs/scoping/02-architecture.md).

## Develop

```bash
uv run pytest                 # unit suite (offline)
POLYMAKER_LIVE=1 uv run pytest tests/test_live_marketdata.py   # live WS integration
uv run ruff check src tests   # lint
uv run mypy src               # types (strict)
```

## Status / roadmap

Implemented: config, catalog/scanner, order book + analytics, strategy (FV,
vol/toxicity, regime, quoting), state store + lifecycle, execution gateway +
reconciler + heartbeat, market/user websockets, risk manager, merger (EOA path),
engine, CLI, paper mode, journal capture. 83 tests; the market-data path is
verified live.

Spike-gated (need the live wallet — see [`docs/scoping/03-api-layer.md`](docs/scoping/03-api-layer.md) §9):
V2 order signing with a Safe/proxy wallet (`livetest` is the probe), pUSD
wrap/allowance mechanics, exact user-WS field names, native Safe merge execution.

Deferred (scoped, not built): replay backtester over captured journals, external
data feeds (polls/news/cross-venue — [`docs/scoping/07-future-external-data.md`](docs/scoping/07-future-external-data.md)).

## License

MIT
