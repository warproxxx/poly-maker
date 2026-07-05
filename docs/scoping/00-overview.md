# Poly-Maker v2 — Scoping Overview

**Date: 2026-07-05.** Scope for a ground-up v2 of this Polymarket market-making
bot, targeting political markets.

## Why now (the forcing function)

Polymarket cut over to **CLOB V2 on April 28, 2026** — new order signing, new
exchange contracts, pUSD collateral — and archived the `py-clob-client`
library this repo is built on. **v1 of this bot can no longer place an
order.** We are not refactoring a working system; we're rebuilding a dead one,
which frees us to fix everything at once.

## Goals

1. **CLOB V2 migration** — new client (`py-clob-client-v2`), V2 order signing,
   pUSD collateral handling, post-only orders, heartbeat dead-man switch,
   batch endpoints. → [03-api-layer.md](03-api-layer.md)
2. **Kill Google Sheets** — config, market selection, and dashboards become
   local TOML files + SQLite + a `polymaker` CLI. A laptop with the repo and a
   funded wallet is a complete deployment. → [05-config-and-ops.md](05-config-and-ops.md)
3. **Fast market discovery** — Gamma API keyset queries with server-side
   politics/liquidity/reward filters replace the hour-long
   crawl-every-orderbook scanner: seconds, one process. → [03](03-api-layer.md) §4, [05](05-config-and-ops.md) §2
4. **Much better strategy** — fair-value + inventory-skew quoting, live
   volatility/toxicity estimation, regime detection (knowing when *not* to
   quote), rewards **and** the new maker-rebates program as explicit objective
   terms, and a replay backtester + paper mode to prove it before capital.
   → [04-strategy.md](04-strategy.md)
5. **Maker-only, always** — every order is post-only; exits are repriced
   limits, the YES+NO merge loop, and size discipline. No taker orders,
   period. → [04](04-strategy.md) §3, §6
6. **Faster & simpler** — one async process (no threads, no Node.js
   subprocess, no gc.collect() folklore), uvloop, event-to-order latency
   target <50ms internal, Python 3.12+, uv end-to-end, typed and tested.
   → [02-architecture.md](02-architecture.md)
7. **Political markets first, external data later** — v2 trades on
   microstructure alone; the architecture reserves an explicit seat (SignalBus)
   for polls/news/cross-venue feeds in a later phase.
   → [07-future-external-data.md](07-future-external-data.md)

## Reading order

| Doc | Contents |
|---|---|
| [01-current-state.md](01-current-state.md) | Audit of v1: what exists, what's broken, what dies, what's worth keeping |
| [02-architecture.md](02-architecture.md) | v2 design: components, state machine, package layout, dependencies |
| [03-api-layer.md](03-api-layer.md) | CLOB V2 migration facts, client choice, endpoints, websockets, rate limits, on-chain/merge |
| [04-strategy.md](04-strategy.md) | The quoting engine: FV, vol/toxicity, regimes, rewards+rebates utility, risk, simulation |
| [05-config-and-ops.md](05-config-and-ops.md) | Local config schemas, scanner/CLI, observability, deployment |
| [06-migration-plan.md](06-migration-plan.md) | Phases 0–5, exit criteria, deletion ledger, risk register |
| [07-future-external-data.md](07-future-external-data.md) | Deferred feed layer, scoped so it's additive later |

## Headline decisions (details in the docs)

- **Build in place, delete v1 as we go** — v1 can't trade anyway; no parallel
  run. (The v1 code was parked under `legacy/` during the port and has since
  been deleted — it lives on in git history on `main`.)
- **Two de-risking spikes before building** (Phase 2): wallet auth on V2 with
  our proxy-wallet setup (known SDK bugs around signature types), and live WS
  payload capture (schemas changed post-2025 and docs are young).
- **BUY-YES + BUY-NO is the canonical two-sided quote** — USDC(pUSD)-
  collateralized on both sides, pairs merge back to cash with locked edge,
  and it satisfies the rewards program's two-sidedness rules.
- **Paper-trading gate before live capital**: ≥2 weeks, ≥10 markets, positive
  PnL under a conservative fill model, markouts > −0.5 tick at +5m.

## Open questions (tracked in 03 §9)

WS ping/pong contract; `py-sdk` (beta unified SDK) maturity; pUSD
wrap/allowance/merge-collateral mechanics; current `price_change` payload
schema; rebate payout currency; signature-type-2 health in the v2 SDK.
