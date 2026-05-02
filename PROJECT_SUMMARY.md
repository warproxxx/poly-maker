# Poly Market Maker Project Summary

## Review Scope

This summary covers the checked-in project code and intentionally ignores generated, local, and sensitive paths named in `.gitignore`, including `.venv/`, `data/`, `positions/`, `node_modules/`, `.env*`, and credential files.

## High-Level Strategy Overview

This project implements an automated market maker for Polymarket binary prediction markets. The bot uses Google Sheets as the operator-facing control plane: selected markets, market metadata, and per-market hyperparameters are read from worksheets, while separate updater scripts refresh market discovery and account statistics back into the same spreadsheet.

The live trading loop connects to Polymarket market and user websockets. Market websocket messages maintain an in-memory order book for subscribed tokens, and every book or price update can trigger the trading routine for the affected market. User websocket messages update local state for orders, fills, pending trades, and positions so the bot does not rely only on slower polling.

For each selected binary market, the strategy evaluates both outcome tokens. It finds usable bid and ask levels that satisfy a minimum displayed size, computes target quote prices just inside the spread when appropriate, and maintains buy/sell orders with configurable tick size, trade size, maximum spread, minimum order size, and maximum position size. It avoids excessive churn by keeping existing orders when price and size changes are small.

Inventory and risk controls are central to the implementation. The bot builds positions up to a configured `max_size`, avoids buying one outcome when it already holds a meaningful reverse outcome position, caps very large positions, and uses a take-profit rule based on average entry price. It also implements a stop-loss/risk-off path: if PnL falls below a configured threshold while spread is tight enough to exit, or if short-term volatility is too high, it sells at the best bid, cancels remaining market orders, and records a temporary sleep period for that market in `positions/`.

The bot also tries to improve capital efficiency by merging opposing YES/NO positions. When both outcome positions in the same market exceed `MIN_MERGE_SIZE`, it calls the Node.js `poly_merger` utility to merge positions on Polygon, recovering collateral and reducing offsetting inventory.

## Top-Level Files

| File | Purpose |
| --- | --- |
| `README.md` | Project introduction, setup instructions, runtime commands, Google Sheets configuration notes, and warning that the bot is a reference implementation rather than a guaranteed profitable system. |
| `main.py` | Main market-making entry point. Initializes `PolymarketClient`, loads markets/positions/orders, starts a background polling thread, and keeps market/user websocket connections alive. |
| `trading.py` | Core strategy implementation. Computes target quotes, manages buy/sell orders, handles inventory limits, stop-loss, take-profit, reverse-position checks, and position merging. |
| `update_markets.py` | Long-running market discovery updater. Fetches active Polymarket markets, estimates rewards and volatility, ranks markets, and writes `All Markets`, `Volatility Markets`, and `Full Markets` sheets. |
| `update_stats.py` | Long-running stats updater. Periodically writes account positions, open orders, and reward earnings into the spreadsheet summary tab. |
| `pyproject.toml` | Python project metadata, dependency pins, package build configuration, and development tool settings. |
| `.env.example` | Template for required environment variables: Polymarket private key, wallet/Safe address, and spreadsheet URL. |
| `.python-version` | Local Python version marker. |
| `.gitignore` | Ignore rules for local envs, credentials, generated data, positions, logs, caches, Node dependencies, and build artifacts. |
| `LICENSE` | MIT license. |
| `uv.lock` | Locked dependency resolution for the UV package manager. |

## Python Packages and Modules

### `poly_data`

| Module | Purpose |
| --- | --- |
| `poly_data/__init__.py` | Package marker. |
| `poly_data/abis.py` | Embedded JSON ABI strings for ERC20, Polymarket negative-risk adapter, and conditional token contracts. |
| `poly_data/CONSTANTS.py` | Shared trading constants; currently defines `MIN_MERGE_SIZE`. |
| `poly_data/global_state.py` | Central mutable runtime state: tracked tokens, reverse token mapping, order books, selected market dataframe, client, hyperparameters, pending trade tracking, open orders, and positions. |
| `poly_data/polymarket_client.py` | Wrapper around Polymarket CLOB, Polygon Web3, and data APIs. Handles order creation/cancelation, balance/position/order queries, and delegates position merging to `poly_merger/merge.js`. |
| `poly_data/data_utils.py` | State synchronization helpers. Updates positions, open orders, selected markets, reverse-token maps, and exposes getters/setters for local position/order state. |
| `poly_data/data_processing.py` | Websocket message processing. Maintains sorted in-memory order books, handles price changes, tracks pending trade IDs, updates local positions/orders from user events, and schedules strategy runs. |
| `poly_data/trading_utils.py` | Strategy math helpers. Finds best price levels with enough size, converts token2 books into the opposite outcome perspective, computes quote prices, rounding, and buy/sell amounts. |
| `poly_data/utils.py` | Spreadsheet loading and parsing for selected markets and hyperparameters, plus a simple JSON pretty-printer. Supports read-only fallback when credentials are unavailable. |
| `poly_data/websocket_handlers.py` | Async websocket clients for Polymarket market data and user events. Subscribes to selected assets and forwards messages to processing functions. |

### `data_updater`

| Module | Purpose |
| --- | --- |
| `data_updater/find_markets.py` | Market discovery and scoring pipeline. Fetches sampling markets, computes reward-per-capital estimates, pulls historical prices, calculates volatility windows, and builds ranked dataframes for spreadsheet output. |
| `data_updater/google_utils.py` | Google Sheets connector for the updater. Authenticates with service-account credentials or falls back to public CSV read-only wrappers. |
| `data_updater/trading_utils.py` | Utility functions for updater-side Polymarket access, approval transactions, simple order placement, and rough position valuation. |
| `data_updater/erc20ABI.json` | ERC20 ABI used by updater approval utilities. |

### `poly_stats`

| Module | Purpose |
| --- | --- |
| `poly_stats/__init__.py` | Package marker. |
| `poly_stats/account_stats.py` | Account reporting pipeline. Combines open orders, positions, selected-market membership, and rewards/earnings, then writes a summary dataframe to Google Sheets. |

### `poly_utils`

| Module | Purpose |
| --- | --- |
| `poly_utils/__init__.py` | Package marker. |
| `poly_utils/google_utils.py` | Shared Google Sheets access layer with authenticated and read-only modes. Used by trading and stats code to load configured worksheets. |

## Node.js Position Merger

| File | Purpose |
| --- | --- |
| `poly_merger/README.md` | Documents the standalone position-merging utility and how it is invoked. |
| `poly_merger/package.json` | Node package metadata and dependencies, mainly `ethers` and `dotenv`. |
| `poly_merger/package-lock.json` | Locked Node dependency tree. |
| `poly_merger/merge.js` | CLI script called by Python to merge opposing positions. Builds the correct transaction for regular vs negative-risk markets and executes it through the configured Safe wallet. |
| `poly_merger/safe-helpers.js` | Helpers for packing signatures and executing Safe transactions. |
| `poly_merger/safeAbi.js` | Gnosis Safe ABI used by `safe-helpers.js` and `merge.js`. |

## Runtime Flow

1. `main.py` creates a `PolymarketClient`.
2. `poly_data.data_utils.update_markets()` loads selected markets and hyperparameters from Google Sheets.
3. `update_positions()` and `update_orders()` initialize local account state from Polymarket APIs.
4. Market and user websockets start.
5. Market book updates update `global_state.all_data` and schedule `trading.perform_trade()`.
6. User order/trade updates update local positions/orders and schedule another strategy pass.
7. A background polling thread periodically refreshes average prices, open orders, selected market configuration, and clears stale pending trades.
8. If opposing positions are large enough, `trading.py` calls `PolymarketClient.merge_positions()`, which invokes `poly_merger/merge.js` to merge positions on-chain.

## Configuration Surfaces

The main configurable behavior lives in Google Sheets rather than local config files:

- `Selected Markets`: markets the bot should actively trade.
- `All Markets`: discovered market metadata and reward estimates.
- `Full Markets`: broader market-discovery output used by stats.
- `Volatility Markets`: lower-volatility candidates sorted for review.
- `Hyperparameters`: parameter sets keyed by `param_type`, including stop-loss, take-profit, volatility threshold, and sleep period values.

Environment variables provide secrets and external locations:

- `PK`: private key used by Polymarket and Polygon clients.
- `BROWSER_ADDRESS`: wallet/Safe address used as the funder and merge executor.
- `SPREADSHEET_URL`: Google Sheet used for configuration and reporting.
