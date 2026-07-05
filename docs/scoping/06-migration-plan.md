# 06 — Migration Plan

Phased so that every phase leaves the repo in a working, testable state, and
the risky unknowns (wallet auth on V2, pUSD) are attacked first. v1 cannot
trade anyway (CLOB V1 is gone — 03), so there is no parallel-run constraint:
we are building v2 in place, deleting v1 as replacements land.

## Phase 0 — Repo hygiene & toolchain (small)

- `src/polymaker/` package skeleton (02 layout), typer CLI stub.
- pyproject: `requires-python = ">=3.12"`, `.python-version` → 3.12.x, fresh
  `uv lock`; dev group: ruff, mypy, pytest, pytest-asyncio; ruff replaces
  black; GitHub Actions running lint+types+tests.
- Delete immediately (nothing depends on them working): `poly_stats/`,
  `update_stats.py`, the read-only Sheets CSV hack, dead commented code.
  The rest of the v1 code (`trading.py`/`main.py`/`data_updater/` …) was parked
  under `legacy/` during the port and has now been deleted — it survives only in
  git history on `main`.
- Remove deps: gspread, gspread-dataframe, google-auth. Add: httpx, pydantic,
  structlog, typer, rich, watchfiles, uvloop, py-clob-client-v2.

**Exit:** `uv run polymaker --help` works; CI green; no Google imports left.

## Phase 1 — Catalog, config, scanner (replaces Sheets as data source)

- pydantic config models + TOML loading + hot reload (05 §1).
- Gamma keyset client, tag resolution, SQLite catalog, market scoring
  (rewards + rebates + vol), `polymaker scan` / `markets` / `markets add`
  (05 §2).
- CLOB public data client (books batch, midpoints, prices-history) for
  enrichment.

**Exit:** politics markets scanned, ranked, and selected into `markets.toml`
in seconds, with no Google anywhere. (v1 bot is now un-runnable — fine, see
above.)

## Phase 2 — Execution core (the V2 unknowns live here — do the spikes first)

- **Spike A (days, throwaway code): wallet auth on V2.** Wrap USDC→pUSD,
  set allowances, place + cancel one post-only order with our exact wallet
  (signature_type 2), read it back on the user WS. Resolves 03 §9 items 3/7.
  Decision output: keep proxy wallet vs. move to EOA; py-clob-client-v2 vs.
  direct signing.
- **Spike B: WS contract.** Capture live `book`/`price_change`/`best_bid_ask`
  /`tick_size_change` payloads (custom features on), confirm ping/pong,
  write the parsers against reality.
- Then build: MarketDataService (books + analytics + resync), UserStream,
  StateStore + order/trade state machine, ExecutionGateway (signer, httpx,
  rate budgeter, heartbeats, batch ops, reconciler), Merger (native Python,
  Safe-or-EOA per Spike A), journal.
- Integration test: on 1–2 quiet live markets with $10-size manual targets,
  prove place/cancel/fill/merge/reconcile round-trips, then heartbeat-driven
  auto-cancel on kill.

**Exit:** engine can hold a hand-specified quote set live, survive WS drops,
crashes, and restarts safely. Journal capture running 24/7 from here on (the
backtester's data supply).

## Phase 3 — Strategy engine (04) + simulation

- Pure strategy module: FV, vol/toxicity, regime machine, quote construction,
  reward/rebate utility, inventory/exit logic — with unit tests per component.
- Replay backtester over the journals accumulated since Phase 2; parameter
  study for the political profiles.
- Paper mode (`run --paper`) end-to-end.
- Delete the parked v1 code — the port is done. (Done: `legacy/` removed.)

**Exit:** paper trading ≥2 weeks, ≥10 political markets, meeting the
acceptance gates from 04 §9 (positive PnL under conservative fills, markouts
> −0.5 tick at +5m, zero risk breaches).

## Phase 4 — Live rollout + ops hardening

- RiskManager fully wired (caps, kill switches, event-group limits), alert
  webhook, `status`/`pnl`/`flatten`/`doctor` polished.
- Go live: 2–3 markets at minimum size → widen coverage/size on weekly review
  of the KPI set. us-east VPS placement.
- Reward/rebate reconciliation against actual daily payouts.

**Exit:** stable unattended operation; income attribution (spread vs rewards
vs rebates) reported per market.

## Phase 5 — Deferred (separately scoped)

- External data feeds (07): polls, news, cross-venue.
- Neg-risk set-arb + NegRiskAdapter conversions (04 §7) if the structural
  edge shows up in captured data.
- Optional: RTDS `activity` flow features, Prometheus/Grafana, Polymarket US
  venue.

## Deletion ledger (what's gone by the end of Phase 3)

`trading.py`, `main.py`, `update_markets.py`, `update_stats.py`, `poly_data/`,
`poly_utils/`, `poly_stats/`, `data_updater/`, `poly_merger/` (entire Node
runtime), `positions/` runtime dir, `credentials.json` expectations,
`SPREADSHEET_URL`, Python 3.9 pin, gspread/gspread-dataframe/google-auth,
py-clob-client (v1), pandas-in-hot-path, all `print()` logging, all bare
excepts, all `gc.collect()` calls.

## Risk register

| Risk | Mitigation |
|---|---|
| V2 SDK auth bugs with proxy/Safe wallets | Spike A first; EOA fallback decided in days, not after building |
| pUSD mechanics undocumented corners | Spike A covers wrap/allowance/merge collateral; treat collateral as per-market config |
| WS payload drift (young V2 docs) | Spike B parses from captured reality; parsers tolerate unknown fields |
| Maker-only exits too slow in a news jump | Position caps sized for survivable worst case (04 §6); EVENT regime pulls quotes early; accept this as the strategy's core tradeoff |
| Rewards program parameters shift | All reward math data-driven from per-market API fields; utility recalibrated from actual payouts |
| Strategy underperforms | Paper-gate before capital; journal-driven iteration loop is the product as much as the bot |
