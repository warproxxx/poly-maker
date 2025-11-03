# Original Poly-Maker System Documentation

This document provides comprehensive documentation of the original poly-maker market making system to preserve all critical implementation details during the Nautilus Trader integration.

## System Overview

The poly-maker is a sophisticated automated market making bot for Polymarket prediction markets that:
- Makes markets on binary prediction outcomes (YES/NO tokens)
- Manages risk through position limits and volatility controls
- Integrates with Google Sheets for configuration management
- Uses real-time WebSocket feeds for market data
- Implements automatic position merging to optimize capital efficiency

## Architecture Components

### 1. Main Application Flow (`main.py`)

```python
# Application lifecycle:
1. Initialize PolymarketClient
2. Load initial data (update_once)
   - Markets from Google Sheets
   - Current positions from API
   - Current orders from API
3. Start background update thread (update_periodically)
4. Start WebSocket connections (market + user data)
5. Main loop with reconnection handling
```

**Key Patterns:**
- **Threading Model**: Background thread for periodic updates (5s cycle)
- **WebSocket Management**: Dual connections (market data + user data) with auto-reconnect
- **Memory Management**: Explicit garbage collection every cycle
- **Error Handling**: Comprehensive try/catch with traceback logging

### 2. Global State Management (`global_state.py`)

The system uses a centralized global state pattern:

```python
# Market Data
all_tokens = []           # List of all tokens being tracked
REVERSE_TOKENS = {}       # Mapping YES↔NO tokens in same market
all_data = {}            # Order book data {market_id: {bids: {}, asks: {}}}
df = None                # Market configuration from Google Sheets

# Client & Parameters
client = None            # PolymarketClient instance
params = {}              # Trading parameters by market type

# Trading State
performing = {}          # Tracks pending trades {token_side: {trade_ids}}
performing_timestamps = {} # When trades were initiated (for cleanup)
orders = {}              # Current orders {token: {buy: {}, sell: {}}}
positions = {}           # Current positions {token: {size, avgPrice}}
```

**Critical Detail**: The `performing` state prevents race conditions by tracking trades that have been submitted but not yet confirmed on-chain.

### 3. Trading Logic (`trading.py`)

#### Core Trading Function: `perform_trade(market)`

The main trading logic follows this sequence:

1. **Position Merging** (Capital Optimization)
   ```python
   # If holding both YES and NO tokens, merge to free capital
   amount_to_merge = min(pos_1, pos_2)
   if amount_to_merge > MIN_MERGE_SIZE:
       client.merge_positions(amount_to_merge, market, neg_risk)
   ```

2. **Market Analysis** (For each token)
   ```python
   # Get order book depth and calculate optimal prices
   deets = get_best_bid_ask_deets(market, token_name, 100, 0.1)
   bid_price, ask_price = get_order_prices(...)
   buy_amount, sell_amount = get_buy_sell_amount(...)
   ```

3. **Order Management**
   ```python
   # Smart order replacement logic
   should_cancel = (
       price_diff > 0.005 or          # 0.5 cent price change
       size_diff > order['size'] * 0.1 # 10% size change
   )
   ```

#### Risk Management Logic

**Position Limits:**
```python
# Multiple position size checks
if position < max_size and position < 250 and buy_amount > 0:
    # Absolute cap of 250 shares per position
    # Market-specific max_size from configuration
```

**Volatility Protection:**
```python
if row['3_hour'] > params['volatility_threshold']:
    client.cancel_all_asset(token)  # Cancel all orders
```

**Risk-Off Periods:**
```python
# File-based risk management state
fname = f'positions/{market}.json'
if os.path.isfile(fname):
    risk_details = json.load(open(fname))
    if current_time < pd.to_datetime(risk_details['sleep_till']):
        send_buy = False  # Don't trade during cooldown
```

**Reverse Position Protection:**
```python
# Don't buy more if holding significant opposite position
rev_token = REVERSE_TOKENS[str(token)]
if rev_pos['size'] > row['min_size']:
    # Cancel orders to avoid conflicting positions
```

#### Order Placement Logic

**Buy Order Conditions:**
1. Position below max_size AND below absolute limit (250)
2. Calculated buy_amount > 0
3. Market spread >= 0.1 (minimum spread requirement)
4. Not in risk-off period
5. Volatility below threshold
6. Price within 0.05 of reference price
7. No significant reverse position
8. Market sentiment ratio >= 0

**Buy Order Triggers:**
1. Better price available (`best_bid > current_order_price`)
2. Insufficient position (`position + orders < 0.95 * max_size`)
3. Order too large (`current_order > target_order * 1.01`)

**Sell Order Logic** (Currently mostly commented out):
- Take-profit based on average cost + threshold
- Position-based sizing
- Price improvement logic

### 4. Trading Utilities (`trading_utils.py`)

#### Order Book Analysis: `get_best_bid_ask_deets()`

```python
# Sophisticated order book analysis
- Finds best/second-best prices with minimum size requirements
- Calculates liquidity within percentage thresholds
- Handles token1 vs token2 (YES vs NO) price inversions
- Returns comprehensive market structure data
```

#### Key Functions:

**`find_best_price_with_size()`**:
- Finds best price with sufficient liquidity
- Handles minimum size requirements
- Returns primary and secondary price levels

**Price Calculations**:
```python
# Token2 (NO) prices are inverted from token1 (YES)
if name == 'token2':
    best_bid, best_ask = 1 - best_ask, 1 - best_bid
```

### 5. Data Management (`data_utils.py`)

#### Position Tracking

**`update_positions(avgOnly=False)`**:
```python
# Smart position updates to prevent race conditions
if not avgOnly:
    position['size'] = row['size']  # Full update
else:
    # Only update if no pending trades
    if col not in performing or len(performing[col]) == 0:
        position['size'] = row['size']
```

**`set_position(token, side, size, price, source)`**:
```python
# Sophisticated average price calculation
if size > 0:  # Buying
    if prev_size == 0:
        avgPrice_new = price  # New position
    else:
        # Weighted average for additional buys
        avgPrice_new = (prev_price * prev_size + price * size) / (prev_size + size)
elif size < 0:  # Selling
    avgPrice_new = prev_price  # Keep original cost basis
```

#### Order Tracking

**`update_orders()`**:
- Fetches all open orders from API
- Organizes by token and side (buy/sell)
- Maintains consistent data structure

### 6. WebSocket Handling (`websocket_handlers.py`)

#### Market Data WebSocket
```python
# Subscribes to order book updates for all tracked tokens
uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
message = {"assets_ids": chunk}  # List of token IDs
```

#### User Data WebSocket
```python
# Receives order and trade confirmations
# Processes real-time position updates
# Handles order status changes
```

**Key Features:**
- Automatic reconnection on disconnect
- Ping/pong heartbeat management
- Error handling with traceback logging

### 7. Data Processing (`data_processing.py`)

#### Trade Execution Tracking

**`add_to_performing(token, side, trade_id)`**:
```python
# Prevents race conditions by tracking pending trades
performing[key].add(trade_id)
performing_timestamps[key][trade_id] = time.time()
```

**`remove_from_performing(key, trade_id)`**:
```python
# Cleanup completed/stale trades
# Prevents indefinite blocking of position updates
```

### 8. Google Sheets Integration

#### Market Configuration
- **"Selected Markets"**: Markets to actively trade
- **"All Markets"**: Database of available markets  
- **"Hyperparameters"**: Trading parameters by market type
- **"Volatility Markets"**: Markets sorted by trading opportunity

#### Parameter Structure
```python
params = {
    'market_type': {
        'volatility_threshold': 0.3,
        'stop_loss_threshold': -10.0,
        'take_profit_threshold': 5.0,
        'max_spread': 2.0,
        'trade_size': 50.0
    }
}
```

## Key Constants and Thresholds

### Trading Thresholds
```python
MIN_MERGE_SIZE = 20              # Minimum position size for merging
MAX_POSITION_SIZE = 250          # Absolute position limit
PRICE_CHANGE_THRESHOLD = 0.05    # Max price deviation from reference
VOLATILITY_THRESHOLD = 0.3       # Max 3-hour volatility
MIN_SPREAD = 0.1                 # Minimum spread to trade
ORDER_UPDATE_THRESHOLD = 0.005   # Price change to trigger order update
SIZE_UPDATE_THRESHOLD = 0.1      # Size change % to trigger order update
```

### Time Constants
```python
UPDATE_INTERVAL = 5              # Seconds between data updates
MARKET_UPDATE_INTERVAL = 30      # Seconds between market data refresh
STALE_TRADE_TIMEOUT = 15         # Seconds before removing stale trades
POSITION_UPDATE_COOLDOWN = 5     # Seconds between position updates
```

## Advanced Features

### 1. Position Merging Logic
```python
# Automatic capital optimization
# Merges YES + NO positions → USDC
# Only when both positions > MIN_MERGE_SIZE
# Considers negative risk markets
```

### 2. Liquidity Analysis
```python
# Calculates bid/ask volume within price ranges
# Uses deviation thresholds (default 5%)
# Provides market sentiment indicators
```

### 3. Risk Management
```python
# File-based risk-off periods
# Volatility-based trading suspension
# Position limit enforcement
# Reverse position protection
```

### 4. Order Management
```python
# Smart order replacement (vs cancellation)
# Size-based order updates
# Price improvement logic
# Spread-based trading decisions
```

## Data Flow Architecture

```
Google Sheets ←→ Configuration Updates
     ↓
Market Selection & Parameters
     ↓
WebSocket Feeds → Order Book Data → Trading Analysis
     ↓                    ↓
Position Updates ←→ Global State ←→ Order Management
     ↓                    ↓
Risk Assessment → Trading Decisions → Order Placement
     ↓
Trade Execution → Position Merging → Performance Tracking
```

## Critical Implementation Details

### 1. Race Condition Prevention
- `performing` state tracks pending trades
- Position updates skip tokens with pending trades
- Timestamp-based stale trade cleanup

### 2. Order Book Management
- Real-time WebSocket updates
- Dual-sided market analysis (bids/asks)
- Token1/Token2 price inversion handling

### 3. Position Calculation
- Weighted average cost basis
- Separate buy/sell impact on averages
- Source tracking (API vs WebSocket)

### 4. Error Recovery
- Automatic WebSocket reconnection
- Graceful handling of API failures
- Comprehensive logging for debugging

### 5. Memory Management
- Explicit garbage collection
- Stale data cleanup
- Bounded data structures

## Risk Controls Summary

1. **Position Limits**: Per-market max_size + absolute 250 limit
2. **Volatility Protection**: Stop trading when 3h volatility > threshold
3. **Risk-Off Periods**: Cooldown after stop-losses
4. **Reverse Position Check**: Prevent conflicting positions
5. **Price Deviation Limits**: Max 5 cent difference from reference
6. **Minimum Spread**: Only trade when spread >= 10 cents
7. **Market Sentiment**: Consider bid/ask volume ratios

## Performance Optimizations

1. **Efficient Order Updates**: Only replace when necessary
2. **Position Merging**: Automatic capital optimization  
3. **Stale Trade Cleanup**: Prevent system blocking
4. **Memory Management**: Regular garbage collection
5. **Batch Operations**: Group related API calls

This documentation captures the sophisticated trading logic, risk management, and system architecture that makes the original poly-maker effective. All these patterns and thresholds should be preserved in the Nautilus Trader integration to maintain the proven market making performance. 