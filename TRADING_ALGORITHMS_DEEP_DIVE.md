# Trading Algorithms Deep Dive - Original Poly-Maker

This document provides a detailed analysis of the sophisticated trading algorithms and decision-making logic implemented in the original poly-maker system. These algorithms represent significant market making expertise that must be preserved in the Nautilus integration.

## Core Trading Decision Framework

### 1. Market Making Philosophy

The poly-maker implements a **sophisticated market neutral strategy** with these core principles:

- **Liquidity Provision**: Always aim to be on the best bid/ask when profitable
- **Risk Management**: Multiple layers of position and volatility controls
- **Capital Efficiency**: Automatic position merging to free up capital
- **Adaptive Sizing**: Position-aware order sizing to manage risk
- **Market Structure Awareness**: Different logic for YES vs NO tokens

### 2. Order Pricing Algorithm (`get_order_prices`)

The system uses a complex pricing algorithm that considers:

```python
def get_order_prices(best_bid, best_bid_size, top_bid, best_ask, best_ask_size, top_ask, avgPrice, row):
    # Key factors in pricing:
    # 1. Current market structure (bid/ask/sizes)
    # 2. Position cost basis (avgPrice)
    # 3. Market configuration parameters
    # 4. Liquidity analysis
    # 5. Spread considerations
```

**Critical Pricing Logic:**
- **Aggressive when profitable**: Price inside spread when advantageous
- **Conservative when risky**: Widen spreads in volatile conditions
- **Position-aware**: Adjust pricing based on existing position cost
- **Size-sensitive**: Consider order book depth for optimal placement

### 3. Position Sizing Algorithm (`get_buy_sell_amount`)

The position sizing follows sophisticated risk management:

```python
# Dynamic position sizing based on:
# 1. Current position vs target
# 2. Market volatility
# 3. Configuration parameters
# 4. Opposite position exposure
# 5. Available capital

max_size = row.get('max_size', row['trade_size'])
buy_amount = calculate_optimal_buy_size(position, max_size, market_conditions)
sell_amount = calculate_optimal_sell_size(position, profitability)
```

**Position Sizing Principles:**
- **Gradual Accumulation**: Build positions incrementally
- **Risk Limits**: Multiple position size controls
- **Opposing Position Awareness**: Consider YES/NO exposure
- **Market-Specific Limits**: Per-market configuration

## Advanced Market Making Features

### 1. Position Merging Strategy

**Automatic Capital Optimization:**
```python
# When holding both YES and NO tokens:
amount_to_merge = min(pos_1, pos_2)
if amount_to_merge > MIN_MERGE_SIZE:
    # Merge positions to free up USDC capital
    client.merge_positions(amount_to_merge, market, neg_risk)
    # Update local position tracking
    set_position(token1, 'SELL', scaled_amt, 0, 'merge')
    set_position(token2, 'SELL', scaled_amt, 0, 'merge')
```

**Benefits:**
- **Capital Efficiency**: Converts matched positions to USDC
- **Risk Reduction**: Eliminates offsetting exposures
- **Gas Optimization**: Only merge when economically viable
- **Automatic Execution**: No manual intervention required

### 2. Liquidity Analysis Engine

**Market Depth Calculation:**
```python
def get_best_bid_ask_deets(market, name, size, deviation_threshold=0.05):
    # Analyzes order book structure:
    # 1. Best prices with minimum size requirements
    # 2. Secondary price levels for depth analysis
    # 3. Liquidity within percentage bands
    # 4. Market sentiment indicators
    
    bid_sum_within_n_percent = sum(
        size for price, size in bids.items() 
        if best_bid <= price <= mid_price * (1 + deviation_threshold)
    )
```

**Liquidity Metrics:**
- **Depth Analysis**: Volume available at different price levels
- **Spread Quality**: Primary vs secondary price gaps
- **Market Sentiment**: Bid/ask volume ratios
- **Size Requirements**: Minimum liquidity thresholds

### 3. Risk Management Integration

**Multi-Layer Risk Framework:**

#### Layer 1: Position Limits
```python
# Hard position limits
if position < max_size and position < 250 and buy_amount > 0:
    # Trade only within configured limits
    # Absolute 250-share cap per position
    # Market-specific max_size from configuration
```

#### Layer 2: Volatility Controls
```python
# Volatility-based trading suspension
if row['3_hour'] > params['volatility_threshold']:
    client.cancel_all_asset(token)
    # Stop all trading when markets become too volatile
```

#### Layer 3: Risk-Off Periods
```python
# File-based cooldown periods
if os.path.isfile(f'positions/{market}.json'):
    risk_details = json.load(open(fname))
    if current_time < pd.to_datetime(risk_details['sleep_till']):
        send_buy = False
        # Don't trade during post-loss cooldown periods
```

#### Layer 4: Reverse Position Protection
```python
# Prevent conflicting positions
rev_token = REVERSE_TOKENS[str(token)]
if rev_pos['size'] > row['min_size']:
    # Cancel orders if holding significant opposite position
    client.cancel_all_asset(order['token'])
```

### 4. Order Management Strategy

**Smart Order Replacement Logic:**
```python
# Intelligent order updates vs cancellations
should_cancel = (
    price_diff > 0.005 or           # 0.5 cent price change
    size_diff > order['size'] * 0.1 # 10% size change
)

if should_cancel:
    client.cancel_all_asset(order['token'])
    # Place new order with updated parameters
else:
    # Keep existing order to maintain queue position
    return
```

**Order Placement Triggers:**
1. **Price Improvement**: `best_bid > current_order_price`
2. **Insufficient Size**: `position + orders < 0.95 * max_size`
3. **Over-sizing**: `current_order > target_order * 1.01`

### 5. Token-Specific Logic (YES vs NO)

**Price Inversion for NO Tokens:**
```python
if name == 'token2':  # NO token
    # Invert all prices since NO = 1 - YES
    best_bid, best_ask = 1 - best_ask, 1 - best_bid
    best_bid_size, best_ask_size = best_ask_size, best_bid_size
    # Handle all secondary prices and liquidity measures
```

**Reference Price Calculation:**
```python
# Different reference prices for YES vs NO
sheet_value = row['best_bid']
if detail['name'] == 'token2':
    sheet_value = 1 - row['best_ask']  # Inverted for NO token
```

## Market Structure Analysis

### 1. Order Book Processing

**Multi-Level Depth Analysis:**
```python
def find_best_price_with_size(price_dict, min_size, reverse=False):
    # Finds best prices meeting minimum size requirements
    # Returns primary and secondary price levels
    # Handles insufficient liquidity gracefully
    
    for price, size in price_list:
        if size >= min_size and not set_best:
            best_price, best_size = price, size
            set_best = True
        elif size >= min_size and set_best:
            second_best_price, second_best_size = price, size
            break
```

### 2. Market Sentiment Indicators

**Bid/Ask Volume Ratios:**
```python
# Calculate market sentiment from order book imbalance
overall_ratio = bid_sum_within_n_percent / ask_sum_within_n_percent

if overall_ratio < 0:
    send_buy = False  # Don't buy when sentiment is negative
    client.cancel_all_asset(order['token'])
```

### 3. Spread Analysis

**Minimum Spread Requirements:**
```python
spread = abs(top_ask - top_bid)
if spread >= 0.1:  # Minimum 10 cent spread requirement
    # Only trade when sufficient spread available
    # Ensures profitable market making opportunities
```

## Advanced Features

### 1. Google Sheets Integration

**Dynamic Parameter Updates:**
- Real-time configuration changes
- Market-specific parameter sets
- Volatility-based adjustments
- Performance tracking integration

### 2. Performance Tracking

**Trade Execution Monitoring:**
```python
# Track pending trades to prevent race conditions
performing[f"{token}_{side}"].add(trade_id)
performing_timestamps[f"{token}_{side}"][trade_id] = time.time()

# Cleanup stale trades after 15 seconds
if current_time - timestamp > 15:
    remove_from_performing(col, trade_id)
```

### 3. Position Averaging

**Sophisticated Cost Basis Calculation:**
```python
if size > 0:  # Buying more
    if prev_size == 0:
        avgPrice_new = price  # New position
    else:
        # Weighted average for additional purchases
        avgPrice_new = (prev_price * prev_size + price * size) / (prev_size + size)
elif size < 0:  # Selling
    avgPrice_new = prev_price  # Keep original cost basis
```

## Risk Controls Deep Dive

### 1. Volatility Management

**3-Hour Volatility Monitoring:**
- Real-time volatility calculation
- Market-specific thresholds
- Automatic trading suspension
- Order cancellation on volatility spikes

### 2. Position Risk Controls

**Multi-Tier Position Limits:**
1. **Market-Specific**: `max_size` from configuration
2. **Absolute**: 250 shares hard limit
3. **Relative**: 95% of target before size adjustments
4. **Opposing**: Consider reverse position exposure

### 3. Price Deviation Controls

**Reference Price Validation:**
```python
price_change = abs(order['price'] - sheet_value)
if price_change >= 0.05:  # 5 cent maximum deviation
    # Cancel orders if price moved too far from reference
    client.cancel_all_asset(order['token'])
```

## Performance Optimizations

### 1. Efficient Order Management

- **Queue Position Preservation**: Only update orders when necessary
- **Batch Operations**: Group related API calls
- **Intelligent Replacement**: Smart cancel/replace logic

### 2. Memory and Resource Management

- **Garbage Collection**: Explicit memory cleanup
- **Stale Data Removal**: Automatic cleanup of old tracking data
- **Connection Management**: Robust WebSocket handling

### 3. Race Condition Prevention

- **Trade State Tracking**: `performing` dictionary prevents conflicts
- **Timestamp Management**: Track when operations were initiated
- **Update Coordination**: Prevent simultaneous position updates

This sophisticated trading framework represents significant market making expertise developed through actual trading experience. The Nautilus integration must preserve these algorithms while leveraging the superior execution and risk management capabilities of the Nautilus framework. 