# Codebase Audit

## Summary
This audit reviews speed, reliability, and hardening concerns observed in the current Polymaker codebase.

## Findings
1. **Runtime crash in price change handler**: `process_price_change` references `asset_id`, which is undefined. Any `price_change` event that flows through this path will raise a `NameError`, breaking websocket processing and trading. The function likely intended to compare against the provided `asset` or a field in the incoming payload before mutating the order book cache.
2. **Concurrent state races across threads and async tasks**: Shared dictionaries such as `performing`, `performing_timestamps`, `orders`, and `positions` are mutated from a background thread (`update_periodically`), websocket handlers, and trading coroutines without synchronization. Although `global_state.lock` exists, it is never used, so data structures can be mutated concurrently, risking inconsistent reads and `RuntimeError` (e.g., size changed during iteration) as well as stale trading decisions.
3. **Unbounded task spawning on every price tick**: `process_data` calls `asyncio.create_task(perform_trade(...))` for every `book` and `price_change` update. For fast-moving markets this can queue a large number of trading tasks per market despite the per-market lock, wasting CPU and increasing latency. A debounce or coalescing strategy would reduce overhead and prevent backlogs.

## Recommendations
- Fix the undefined variable in `process_price_change` and ensure the handler safely ignores irrelevant tokens without crashing the websocket loop.
- Introduce locking or other concurrency controls around shared state mutations (e.g., context managers using `global_state.lock`) so background updates and websocket events cannot interfere with each other.
- Batch or debounce trading triggers inside `process_data` (e.g., only schedule a trade once per event loop tick per market) to avoid excessive task creation under heavy websocket traffic.
