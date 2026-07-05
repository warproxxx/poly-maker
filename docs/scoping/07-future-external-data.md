# 07 — Future: External Data Feeds (deferred, scoped now)

v2 trades political markets on **microstructure alone** (04 §1). That is a
deliberate constraint, not a belief that external data has no value — the
architecture reserves a seat for it so adding feeds later is additive, not a
refactor. This doc scopes the seat and the candidate feeds; **none of this is
built in v2.**

## Architectural seat (built in v2, empty)

The strategy signature already is `(BookState, Inventory, Params, Clock) ->
TargetQuotes`. The extension is one optional input:

```
SignalBus: name -> {value, confidence, as_of, ttl}
```

- Strategy reads signals as **FV adjusters and regime inputs** with explicit
  staleness: a signal past its TTL contributes nothing (fail-safe to pure
  microstructure — the bot must never be worse than v2 because a feed died).
- Feed adapters are separate async tasks (or even separate processes writing
  to the bus via SQLite/socket) — never in the quote path; the hot loop only
  reads a dict.
- Every signal is journaled like WS data, so the replay backtester (04 §9)
  can grade any feed's marginal value before it touches live quotes. **A feed
  earns its way in through replay evidence, or it doesn't ship.**

## Candidate feeds for political markets (rough priority)

1. **Event calendar (highest value / lowest effort)**: debates, primaries,
   election nights, court dates, scheduled rulings. Even a hand-maintained
   `calendar.toml` (date, market tags, severity) lets the regime machine
   pre-widen/pull *before* scheduled volatility instead of reacting to the
   first sweep. No API needed to start.
2. **Cross-venue prices**: Kalshi (public API), and Polymarket US as it
   grows. Same-event price divergence is both an FV prior and a toxicity
   warning (fast flow often arbs venues; if Kalshi moved and we didn't, our
   quote is stale). Clean REST/WS, well-bounded work.
3. **Poll aggregates / forecast models**: RCP/538-style averages, Silver
   Bulletin, model outputs. Slow-moving FV anchor for long-dated markets —
   mostly useful as a *sanity band* (flag when market FV drifts far from
   model FV) rather than a quoting signal.
4. **News/headline triggers**: wire headlines, X/Twitter firehose, Google
   Trends spikes. Highest alpha, highest noise and engineering cost;
   realistically an "instant EVENT-regime trigger" (pull quotes on keyword
   burst), not a pricing input. Last in line.
5. **Polymarket-internal extras** (not really "external", could land earlier):
   RTDS `activity` topic for platform-wide flow/toxicity features, comment
   velocity per market as an attention proxy (03 §5).

## Explicitly out of scope until then

- Any taker execution driven by signals (feeds inform *maker* quoting only —
  the maker-only policy survives the feed era).
- LLM/news-summarization pipelines, sentiment models.
- Trading the Polymarket US venue (separate API/regulatory surface — 03 §8).

## Preconditions before starting this phase

- v2 live and stable through at least one high-volatility political event.
- Journal + replay infrastructure proven (it is the evaluation harness here).
- KPI baseline established, so each feed's marginal contribution is measured
  against a known control.
