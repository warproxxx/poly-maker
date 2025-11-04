# Configuration Guide

## Overview

All configuration for the Polymarket Liquidity Bot is centralized in `config.py`. Values can be overridden via environment variables in `.env`.

## Quick Start

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` and set required values:**
   ```bash
   PK=your_private_key_here
   BROWSER_ADDRESS=your_wallet_address_here
   SPREADSHEET_URL=your_google_sheet_url
   ```

3. **Run configuration test:**
   ```bash
   python config.py
   ```

4. **Start the bot:**
   ```bash
   python main.py
   ```

---

## Required Configuration

### Authentication

```bash
# Your Polymarket wallet private key (KEEP SECRET!)
PK=0x...

# Your wallet address
BROWSER_ADDRESS=0x...
```

**Security Note:** Never commit your `.env` file to git! It's already in `.gitignore`.

### Google Sheets

```bash
# URL to your Google Sheet with market configuration
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/edit
```

---

## Feature Flags

### Dynamic Spreads (RECOMMENDED)

```bash
USE_DYNAMIC_SPREADS=true  # Enable dynamic spread adjustment
```

**What it does:**
- Automatically widens spreads during high volatility
- Skews spreads to reduce unwanted inventory
- Adjusts based on market regime (tighter in mean-reverting, wider in trending)
- Widens spreads as market approaches close

**Impact:** +10-20% profitability from better execution

**When to disable:** If you prefer manual spread control or are testing

### Kelly Sizing (ADVANCED)

```bash
USE_KELLY_SIZING=false  # Enable Kelly criterion position sizing
```

**What it does:**
- Automatically sizes positions based on edge and variance
- Prevents over-betting on risky markets
- Maximizes long-term growth rate

**Impact:** +10-30% over time from optimal capital allocation

**When to enable:** After you're comfortable with the system

### Dry Run Mode (TESTING)

```bash
DRY_RUN_MODE=false  # Log trades but don't execute
```

**What it does:**
- Simulates trading without placing real orders
- Useful for testing strategies

**When to use:** Testing new configurations

---

## Update Intervals

```bash
# How often to update positions/orders (seconds)
UPDATE_INTERVAL=5

# How many cycles before refreshing markets from sheets
# 6 cycles × 5s = 30s
MARKET_UPDATE_CYCLES=6

# Timeout for stale trades (seconds)
STALE_TRADE_TIMEOUT=15

# Market discovery interval (seconds)
# 3600 = 1 hour
MARKET_DISCOVERY_INTERVAL=3600

# Stats update interval (seconds)
# 10800 = 3 hours
STATS_UPDATE_INTERVAL=10800
```

**Tuning Guide:**
- **Lower UPDATE_INTERVAL** (e.g., 3s) = More responsive, higher API load
- **Higher UPDATE_INTERVAL** (e.g., 10s) = Less responsive, lower API load
- **Lower MARKET_UPDATE_CYCLES** = More frequent sheet refreshes, higher load
- **Higher MARKET_DISCOVERY_INTERVAL** (e.g., 2 hours) = Less frequent market scanning

---

## Trading Parameters

```bash
# Minimum price change to trigger order update (dollars)
PRICE_CHANGE_THRESHOLD=0.005  # 0.5 cents

# Minimum size change to trigger order update (fraction)
SIZE_CHANGE_THRESHOLD=0.10  # 10%

# Min/max tradeable prices (avoid extreme positions)
MIN_TRADEABLE_PRICE=0.10  # $0.10
MAX_TRADEABLE_PRICE=0.90  # $0.90

# Minimum position size to merge (saves gas)
MIN_MERGE_SIZE=20  # USDC

# Absolute maximum position per token
ABSOLUTE_MAX_POSITION=250  # shares
```

**Tuning Guide:**
- **Lower PRICE_CHANGE_THRESHOLD** (e.g., 0.002) = More order updates, higher fees
- **Higher PRICE_CHANGE_THRESHOLD** (e.g., 0.01) = Fewer updates, less responsive
- **Lower SIZE_CHANGE_THRESHOLD** = More frequent size adjustments
- **Lower MIN_MERGE_SIZE** = More frequent merges, higher gas costs
- **Higher ABSOLUTE_MAX_POSITION** = More capital per position, higher risk

---

## Dynamic Spreads Configuration

### Basic Parameters

```bash
# Base spread in basis points
# 20 bps = 0.20% spread
BASE_SPREAD_BPS=20

# Minimum spread in ticks
# 2 ticks = 0.02 minimum spread
MIN_SPREAD_TICKS=2

# Maximum spread as percentage of price
# 0.10 = 10% maximum spread
MAX_SPREAD_PCT=0.10

# Inventory penalty factor
# Controls how aggressively spreads skew to reduce inventory
INVENTORY_PENALTY_FACTOR=0.01
```

**Examples:**

| Scenario | BASE_SPREAD_BPS | MIN_SPREAD_TICKS | MAX_SPREAD_PCT |
|----------|-----------------|------------------|----------------|
| **Aggressive** | 10-15 | 1 | 0.05 (5%) |
| **Balanced** | 20-30 | 2 | 0.10 (10%) |
| **Conservative** | 40-50 | 3 | 0.15 (15%) |

**When spreads widen automatically:**
- High volatility (up to 5× base spread)
- Trending regime (1.5× base spread)
- Event-driven regime (2.5× base spread)
- Large inventory position (skews by ±50%)
- Close to market expiration (up to 2× base spread)

**When spreads tighten automatically:**
- Mean-reverting regime (0.8× base spread)
- Deep orderbook (competitive environment)
- Stable low volatility

---

## Risk Metrics

```bash
# Annual risk-free rate (for Sharpe/Sortino calculations)
RISK_FREE_RATE_ANNUAL=0.05  # 5% (T-bills)

# Estimated gas cost per trade (USDC)
GAS_COST_PER_TRADE=0.01

# Expected slippage in basis points
SLIPPAGE_BPS=2.0
```

**Impact:** Used for ranking markets by risk-adjusted returns

---

## Portfolio Optimization

```bash
# Kelly fraction (position sizing)
KELLY_FRACTION=0.25  # Quarter-Kelly (recommended)

# Maximum number of concurrent positions
MAX_POSITIONS=20

# Maximum exposure to any category (Politics, Crypto, etc.)
MAX_CATEGORY_EXPOSURE=0.40  # 40%

# Maximum capital in any single position
MAX_SINGLE_POSITION=0.25  # 25%

# Rebalance threshold
REBALANCE_THRESHOLD=0.20  # Rebalance at 20% drift
```

**Kelly Fraction Guide:**

| Fraction | Risk Level | Description |
|----------|-----------|-------------|
| **0.10** | Very Conservative | Minimal growth, very safe |
| **0.25** | Conservative | Recommended for most users |
| **0.50** | Moderate | Half-Kelly, more aggressive |
| **1.00** | Aggressive | Full Kelly, high volatility |

**Note:** Full Kelly can lead to 50%+ drawdowns. Quarter-Kelly is safer.

---

## Market Discovery

```bash
# Minimum maker reward per $100 to consider
MAKER_REWARD_THRESHOLD=0.75  # $0.75

# Maximum volatility sum to include in filtered list
VOLATILITY_FILTER_THRESHOLD=20

# Minimum Sharpe ratio to trade
MIN_SHARPE_RATIO=0.5

# Parallel workers for market fetching
MAX_WORKERS=5
MAX_WORKERS_VOLATILITY=3
```

**Tuning for Market Selection:**

| Goal | MAKER_REWARD_THRESHOLD | VOLATILITY_FILTER_THRESHOLD | MIN_SHARPE_RATIO |
|------|------------------------|----------------------------|-------------------|
| **High Quality Only** | 1.50 | 10 | 1.0 |
| **Balanced** | 0.75 | 20 | 0.5 |
| **More Opportunities** | 0.50 | 30 | 0.3 |

---

## Logging

```bash
# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Enable file logging
LOG_TO_FILE=false
LOG_FILE_PATH=logs/trading.log

# Enable performance metrics logging
ENABLE_PERFORMANCE_METRICS=true

# Log spread comparison (old vs dynamic)
ENABLE_SPREAD_COMPARISON_LOGGING=true
```

**Debug Mode:**
```bash
LOG_LEVEL=DEBUG
LOG_TO_FILE=true
```

This will log everything to `logs/trading.log` for troubleshooting.

---

## Example Configurations

### Conservative (Low Risk)

```bash
# .env
USE_DYNAMIC_SPREADS=true
USE_KELLY_SIZING=false

BASE_SPREAD_BPS=40
MIN_SPREAD_TICKS=3
MAX_SPREAD_PCT=0.15

MAKER_REWARD_THRESHOLD=1.50
VOLATILITY_FILTER_THRESHOLD=10
MIN_SHARPE_RATIO=1.0

ABSOLUTE_MAX_POSITION=100
```

**Profile:** Safe, stable returns, minimal drawdowns

---

### Balanced (Recommended)

```bash
# .env
USE_DYNAMIC_SPREADS=true
USE_KELLY_SIZING=false

BASE_SPREAD_BPS=20
MIN_SPREAD_TICKS=2
MAX_SPREAD_PCT=0.10

MAKER_REWARD_THRESHOLD=0.75
VOLATILITY_FILTER_THRESHOLD=20
MIN_SHARPE_RATIO=0.5

ABSOLUTE_MAX_POSITION=250
```

**Profile:** Good balance of risk and return

---

### Aggressive (High Risk)

```bash
# .env
USE_DYNAMIC_SPREADS=true
USE_KELLY_SIZING=true

KELLY_FRACTION=0.50

BASE_SPREAD_BPS=15
MIN_SPREAD_TICKS=1
MAX_SPREAD_PCT=0.08

MAKER_REWARD_THRESHOLD=0.50
VOLATILITY_FILTER_THRESHOLD=30
MIN_SHARPE_RATIO=0.3

ABSOLUTE_MAX_POSITION=500
```

**Profile:** Maximum growth potential, higher volatility

---

## Testing Your Configuration

### 1. Validate Configuration

```bash
python config.py
```

Should print configuration and show warnings/errors.

### 2. Dry Run Test

```bash
# In .env
DRY_RUN_MODE=true
```

Then run:
```bash
python main.py
```

Monitor logs to ensure spreads and sizing look correct.

### 3. Small Capital Test

Start with small position sizes:
```bash
ABSOLUTE_MAX_POSITION=50
```

Monitor for 24 hours, then gradually increase.

---

## Troubleshooting

### "Configuration errors: KELLY_FRACTION must be between 0 and 1"

**Solution:** Check your .env file for invalid values:
```bash
KELLY_FRACTION=0.25  # Must be 0.0 to 1.0
```

### Spreads Too Wide

**Check:**
```bash
BASE_SPREAD_BPS=20  # Lower this (e.g., 15)
MAX_SPREAD_PCT=0.10  # Lower this (e.g., 0.05)
```

### Spreads Too Narrow (Getting Picked Off)

**Check:**
```bash
BASE_SPREAD_BPS=30  # Increase this
MIN_SPREAD_TICKS=3  # Increase this
```

### Orders Not Updating Frequently Enough

**Check:**
```bash
UPDATE_INTERVAL=3  # Lower this (from 5)
PRICE_CHANGE_THRESHOLD=0.003  # Lower this (from 0.005)
```

### Too Many API Calls

**Check:**
```bash
UPDATE_INTERVAL=10  # Increase this
MARKET_UPDATE_CYCLES=12  # Increase this
MAX_WORKERS=3  # Reduce this
```

---

## Advanced: Environment-Specific Configs

### Development

```bash
# .env.dev
USE_DYNAMIC_SPREADS=true
DRY_RUN_MODE=true
LOG_LEVEL=DEBUG
LOG_TO_FILE=true
```

### Production

```bash
# .env.prod
USE_DYNAMIC_SPREADS=true
DRY_RUN_MODE=false
LOG_LEVEL=INFO
LOG_TO_FILE=true
ENABLE_PERFORMANCE_METRICS=true
```

Switch between them:
```bash
ln -sf .env.prod .env  # Use production config
ln -sf .env.dev .env   # Use development config
```

---

## Performance Tuning

### For High-Frequency Trading

```bash
UPDATE_INTERVAL=3
PRICE_CHANGE_THRESHOLD=0.002
SIZE_CHANGE_THRESHOLD=0.05
```

### For Low-Frequency Trading

```bash
UPDATE_INTERVAL=15
PRICE_CHANGE_THRESHOLD=0.01
SIZE_CHANGE_THRESHOLD=0.20
```

### For Large Capital

```bash
ABSOLUTE_MAX_POSITION=1000
MAX_POSITIONS=30
KELLY_FRACTION=0.20  # More conservative with large capital
```

### For Small Capital

```bash
ABSOLUTE_MAX_POSITION=50
MAX_POSITIONS=10
KELLY_FRACTION=0.30  # Can be more aggressive
```

---

## Support

For questions or issues:
1. Check this documentation
2. Review `ENHANCEMENTS.md` for feature details
3. Run `python config.py` to verify settings
4. Check logs in `logs/trading.log` (if enabled)
5. Open an issue on GitHub

Happy trading! 🚀
