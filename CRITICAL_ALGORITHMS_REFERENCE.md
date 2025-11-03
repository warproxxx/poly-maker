# Critical Algorithms Reference - Original Poly-Maker

This document captures the exact algorithms, formulas, and logical conditions from the original poly-maker code to ensure no critical details are lost during the Nautilus integration.

## Core Pricing Algorithm

### `get_order_prices()` - Exact Implementation

```python
def get_order_prices(best_bid, best_bid_size, top_bid, best_ask, best_ask_size, top_ask, avgPrice, row):
    """
    Calculate bid and ask prices for quoting orders.
    
    Strategy:
    1. Undercut current best by 1 tick to gain queue priority
    2. Take over small size orders (< 5 shares)  
    3. Prevent crossing the spread
    4. Handle edge cases where bid equals ask
    """
    
    # Primary strategy: Undercut by 1 tick size
    bid_price = best_bid + row['tick_size']
    ask_price = best_ask - row['tick_size']

    # Takeover strategy: Replace small orders
    if best_bid_size < 5:
        bid_price = best_bid
    
    if best_ask_size < 5:
        ask_price = best_ask
    
    # Spread protection: Don't cross the market
    if bid_price >= top_ask:
        bid_price = top_bid

    if ask_price <= top_bid:
        ask_price = top_ask

    # Edge case: Prevent bid == ask
    if bid_price == ask_price:
        bid_price = top_bid
        ask_price = top_ask

    return bid_price, ask_price
```

**Key Principles:**
- **Tick Improvement**: Always try to be better by 1 tick
- **Small Size Takeover**: Replace orders < 5 shares
- **Spread Integrity**: Never cross bid/ask spread
- **Queue Priority**: Slight price improvement for better fills

## Position Sizing Algorithm

### `get_buy_sell_amount()` - Exact Implementation

```python
def get_buy_sell_amount(position, bid_price, row, other_token_position=0):
    """
    Sophisticated position sizing with multi-tier logic.
    
    Phases:
    1. Accumulation: Build to max_size
    2. Market Making: Continue providing liquidity
    3. Exit Strategy: Progressive position reduction
    """
    buy_amount = 0
    sell_amount = 0

    # Get configuration values
    max_size = row.get('max_size', row['trade_size'])
    trade_size = row['trade_size']
    
    # Calculate total exposure across both sides of market
    total_exposure = position + other_token_position
    
    # PHASE 1: ACCUMULATION (position < max_size)
    if position < max_size:
        # Continue building position up to max_size
        remaining_to_max = max_size - position
        buy_amount = min(trade_size, remaining_to_max)
        
        # Only start selling when we have substantial position
        if position >= trade_size:
            sell_amount = min(position, trade_size)
        else:
            sell_amount = 0
    
    # PHASE 2: MARKET MAKING (position >= max_size)
    else:
        # Always offer to sell when at max capacity
        sell_amount = min(position, trade_size)
        
        # Continue market making if total exposure allows
        if total_exposure < max_size * 2:  # 2x flexibility
            buy_amount = trade_size
        else:
            buy_amount = 0

    # MINIMUM SIZE COMPLIANCE
    if buy_amount > 0.7 * row['min_size'] and buy_amount < row['min_size']:
        buy_amount = row['min_size']

    # LOW-PRICE MULTIPLIER (for cheap assets)
    if bid_price < 0.1 and buy_amount > 0:
        if 'multiplier' in row and row['multiplier'] != '':
            buy_amount = buy_amount * int(row['multiplier'])
            
    return buy_amount, sell_amount
```

**Position Sizing Logic:**
1. **Gradual Build**: `trade_size` increments to `max_size`
2. **Exit Availability**: Always offer to sell once position >= `trade_size`
3. **Double Exposure**: Allow up to `2 * max_size` total exposure
4. **Minimum Compliance**: Ensure orders meet exchange minimums
5. **Low-Price Boost**: Multiply size for assets < $0.10

## Order Book Analysis

### `get_best_bid_ask_deets()` - Liquidity Analysis

```python
def get_best_bid_ask_deets(market, name, size, deviation_threshold=0.05):
    """
    Comprehensive order book analysis with depth metrics.
    
    Returns:
    - Best/second-best prices with size requirements
    - Liquidity within percentage bands
    - Market sentiment indicators
    - Token-specific price inversions
    """
    
    # Find prices meeting minimum size requirements
    best_bid, best_bid_size, second_best_bid, second_best_bid_size, top_bid = \
        find_best_price_with_size(all_data[market]['bids'], size, reverse=True)
    
    best_ask, best_ask_size, second_best_ask, second_best_ask_size, top_ask = \
        find_best_price_with_size(all_data[market]['asks'], size, reverse=False)
    
    # Calculate mid price and liquidity bands
    if best_bid is not None and best_ask is not None:
        mid_price = (best_bid + best_ask) / 2
        
        # Liquidity within deviation threshold (default 5%)
        bid_sum_within_n_percent = sum(
            size for price, size in all_data[market]['bids'].items() 
            if best_bid <= price <= mid_price * (1 + deviation_threshold)
        )
        
        ask_sum_within_n_percent = sum(
            size for price, size in all_data[market]['asks'].items() 
            if mid_price * (1 - deviation_threshold) <= price <= best_ask
        )
    else:
        mid_price = None
        bid_sum_within_n_percent = 0
        ask_sum_within_n_percent = 0

    # TOKEN2 (NO) PRICE INVERSION
    if name == 'token2':
        if all prices are not None:
            # Invert all prices: NO = 1 - YES
            best_bid, second_best_bid, top_bid, best_ask, second_best_ask, top_ask = \
                1-best_ask, 1-second_best_ask, 1-top_ask, 1-best_bid, 1-second_best_bid, 1-top_bid
            
            # Swap bid/ask sizes
            best_bid_size, second_best_bid_size, best_ask_size, second_best_ask_size = \
                best_ask_size, second_best_ask_size, best_bid_size, second_best_bid_size
            
            # Swap liquidity measures
            bid_sum_within_n_percent, ask_sum_within_n_percent = \
                ask_sum_within_n_percent, bid_sum_within_n_percent

    return {
        'best_bid': best_bid,
        'best_bid_size': best_bid_size,
        'second_best_bid': second_best_bid,
        'second_best_bid_size': second_best_bid_size,
        'top_bid': top_bid,
        'best_ask': best_ask,
        'best_ask_size': best_ask_size,
        'second_best_ask': second_best_ask,
        'second_best_ask_size': second_best_ask_size,
        'top_ask': top_ask,
        'bid_sum_within_n_percent': bid_sum_within_n_percent,
        'ask_sum_within_n_percent': ask_sum_within_n_percent
    }
```

### `find_best_price_with_size()` - Price Discovery

```python
def find_best_price_with_size(price_dict, min_size, reverse=False):
    """
    Find best and second-best prices meeting minimum size requirements.
    
    Logic:
    1. Sort prices (reverse for bids to get highest first)
    2. Find first price with sufficient size (best)
    3. Find second price with sufficient size (second-best)
    4. Track top price regardless of size
    """
    lst = list(price_dict.items())
    if reverse:
        lst.reverse()  # For bids: highest prices first
    
    best_price, best_size = None, None
    second_best_price, second_best_size = None, None
    top_price = None
    set_best = False

    for price, size in lst:
        # Always track the top price
        if top_price is None:
            top_price = price

        # Look for second-best after best is set
        if set_best:
            second_best_price, second_best_size = price, size
            break
        
        # Set best price (first one found)
        best_price, best_size = price, size
        set_best = True

    return best_price, best_size, second_best_price, second_best_size, top_price
```

## Position Management

### Position Update Logic - `update_positions()`

```python
def update_positions(avgOnly=False):
    """
    Smart position updates with race condition prevention.
    
    Logic:
    1. Get all positions from API
    2. Update average prices always
    3. Update sizes only if no pending trades
    4. Skip recent updates (< 5 seconds)
    """
    pos_df = client.get_all_positions()

    for idx, row in pos_df.iterrows():
        asset = str(row['asset'])

        # Initialize position if new
        if asset in positions:
            position = positions[asset].copy()
        else:
            position = {'size': 0, 'avgPrice': 0}

        # Always update average price
        position['avgPrice'] = row['avgPrice']

        if not avgOnly:
            # Full update mode
            position['size'] = row['size']
        else:
            # Protected update mode
            for col in [f"{asset}_sell", f"{asset}_buy"]:
                # Only update if no pending trades
                if (col not in performing or 
                    not isinstance(performing[col], set) or 
                    len(performing[col]) == 0):
                    
                    old_size = position.get('size', 0)
                    
                    # Skip if recently updated
                    if asset in last_trade_update:
                        if time.time() - last_trade_update[asset] < 5:
                            continue

                    # Update position size
                    if old_size != row['size']:
                        print(f"No trades pending. Updating {asset}: {old_size} → {row['size']}")
                        position['size'] = row['size']
                else:
                    print(f"ALERT: Skipping {asset} - pending trades: {performing[col]}")
    
        positions[asset] = position
```

### Position Averaging - `set_position()`

```python
def set_position(token, side, size, price, source='websocket'):
    """
    Sophisticated position averaging with cost basis tracking.
    
    Rules:
    1. Buys update weighted average price
    2. Sells maintain original cost basis
    3. Track update timestamps
    4. Handle position direction changes
    """
    token = str(token)
    size = float(size)
    price = float(price)

    # Track when position was updated
    last_trade_update[token] = time.time()
    
    # Convert sells to negative size
    if side.lower() == 'sell':
        size *= -1

    if token in positions:
        prev_price = positions[token]['avgPrice']
        prev_size = positions[token]['size']

        # AVERAGE PRICE CALCULATION
        if size > 0:  # Buying
            if prev_size == 0:
                # Starting new position
                avgPrice_new = price
            else:
                # Adding to position - weighted average
                avgPrice_new = (prev_price * prev_size + price * size) / (prev_size + size)
        elif size < 0:  # Selling
            # Maintain original cost basis when selling
            avgPrice_new = prev_price
        else:
            # No size change
            avgPrice_new = prev_price

        # Update position
        positions[token]['size'] += size
        positions[token]['avgPrice'] = avgPrice_new
    else:
        # New position
        positions[token] = {'size': size, 'avgPrice': price}

    print(f"Updated position from {source}: {positions[token]}")
```

## Risk Management Conditions

### Trading Conditions - Exact Logic

```python
# MAIN TRADING CONDITION
if position < max_size and position < 250 and buy_amount > 0 and spread >= 0.1:
    
    # REFERENCE PRICE CALCULATION
    sheet_value = row['best_bid']
    if detail['name'] == 'token2':
        sheet_value = 1 - row['best_ask']  # Invert for NO token
    
    sheet_value = round(sheet_value, round_length)
    price_change = abs(order['price'] - sheet_value)
    
    # RISK-OFF PERIOD CHECK
    fname = f'positions/{market}.json'
    if os.path.isfile(fname):
        risk_details = json.load(open(fname))
        start_trading_at = pd.to_datetime(risk_details['sleep_till'])
        current_time = pd.Timestamp.utcnow().tz_localize(None)
        
        if current_time < start_trading_at:
            send_buy = False
            print(f"Risk-off period active until {start_trading_at}")
    
    # VOLATILITY AND PRICE DEVIATION CHECK
    if (row['3_hour'] > params['volatility_threshold'] or 
        price_change >= 0.05):
        print(f"Volatility {row['3_hour']} > {params['volatility_threshold']} "
              f"or price deviation {price_change} >= 0.05")
        client.cancel_all_asset(order['token'])
    
    # REVERSE POSITION CHECK
    rev_token = REVERSE_TOKENS[str(token)]
    rev_pos = get_position(rev_token)
    if rev_pos['size'] > row['min_size']:
        print("Reverse position detected - cancelling orders")
        if orders['buy']['size'] > MIN_MERGE_SIZE:
            client.cancel_all_asset(order['token'])
        continue
    
    # MARKET SENTIMENT CHECK
    overall_ratio = bid_sum_within_n_percent / ask_sum_within_n_percent
    if overall_ratio < 0:
        send_buy = False
        client.cancel_all_asset(order['token'])
    
    # ORDER PLACEMENT TRIGGERS
    if send_buy:
        # 1. Better price available
        if best_bid > orders['buy']['price']:
            send_buy_order(order)
        
        # 2. Insufficient position + orders
        elif position + orders['buy']['size'] < 0.95 * max_size:
            send_buy_order(order)
        
        # 3. Current order too large
        elif orders['buy']['size'] > order['size'] * 1.01:
            send_buy_order(order)
```

### Order Update Logic - `send_buy_order()`

```python
def send_buy_order(order):
    """
    Smart order replacement with queue position preservation.
    
    Decision Matrix:
    - Price change > 0.5 cents → Replace
    - Size change > 10% → Replace  
    - Otherwise → Keep existing order
    """
    existing_buy_size = order['orders']['buy']['size']
    existing_buy_price = order['orders']['buy']['price']
    
    # Calculate change thresholds
    price_diff = abs(existing_buy_price - order['price']) if existing_buy_price > 0 else float('inf')
    size_diff = abs(existing_buy_size - order['size']) if existing_buy_size > 0 else float('inf')
    
    # Replacement decision
    should_cancel = (
        price_diff > 0.005 or              # 0.5 cent price change
        size_diff > order['size'] * 0.1 or # 10% size change
        existing_buy_size == 0             # No existing order
    )
    
    if should_cancel and (existing_buy_size > 0 or order['orders']['sell']['size'] > 0):
        print(f"Replacing order - price Δ: {price_diff:.4f}, size Δ: {size_diff:.1f}")
        client.cancel_all_asset(order['token'])
        
        # Place new order
        client.create_order(
            order['token'], 
            'BUY', 
            order['price'], 
            order['size'], 
            True if order['neg_risk'] == 'TRUE' else False
        )
    else:
        print(f"Keeping existing order - minor changes")
        return  # Preserve queue position
```

## Position Merging Algorithm

```python
# POSITION MERGING LOGIC
pos_1 = get_position(row['token1'])['size']
pos_2 = get_position(row['token2'])['size']

# Calculate merge amount
amount_to_merge = min(pos_1, pos_2)

# Only merge if above minimum threshold
if float(amount_to_merge) > MIN_MERGE_SIZE:
    # Get exact blockchain positions
    pos_1 = client.get_position(row['token1'])[0]
    pos_2 = client.get_position(row['token2'])[0]
    amount_to_merge = min(pos_1, pos_2)
    scaled_amt = amount_to_merge / 10**6  # Convert from blockchain units
    
    if scaled_amt > MIN_MERGE_SIZE:
        print(f"Merging {scaled_amt} positions")
        
        # Execute merge
        client.merge_positions(
            amount_to_merge, 
            market, 
            row['neg_risk'] == 'TRUE'
        )
        
        # Update local tracking
        set_position(row['token1'], 'SELL', scaled_amt, 0, 'merge')
        set_position(row['token2'], 'SELL', scaled_amt, 0, 'merge')
```

## Mathematical Formulas

### Weighted Average Price Calculation
```python
# When buying more of existing position:
new_avg_price = (old_avg_price * old_size + new_price * new_size) / (old_size + new_size)

# When selling:
avg_price = old_avg_price  # Unchanged cost basis
```

### Liquidity Band Calculation
```python
# Bid liquidity within threshold
bid_liquidity = sum(
    size for price, size in bids.items() 
    if best_bid <= price <= mid_price * (1 + deviation_threshold)
)

# Ask liquidity within threshold  
ask_liquidity = sum(
    size for price, size in asks.items()
    if mid_price * (1 - deviation_threshold) <= price <= best_ask
)
```

### Market Sentiment Ratio
```python
sentiment_ratio = bid_liquidity / ask_liquidity
# > 1.0 = Bullish (more bid volume)
# < 1.0 = Bearish (more ask volume)
```

These exact algorithms represent the core intelligence of the poly-maker system. Every threshold, formula, and logical condition has been battle-tested through actual trading and should be preserved precisely in the Nautilus integration. 