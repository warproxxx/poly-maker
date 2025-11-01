# Getting Started with Paper Trading

🎯 **Quick start guide for testing your Polymarket market-making bot risk-free**

## What You've Got

Your Polymarket bot now has **paper trading mode** - a complete simulation environment that lets you:

✅ Test strategies with virtual funds ($10,000 default)
✅ Use real-time Polymarket market data
✅ Demo to investors without risk (perfect for YC pitches)
✅ Validate performance before going live
✅ Track P&L, win rates, and trading activity

## 5-Minute Setup

### Step 1: Run the Setup Script

```bash
./setup_paper_trading.sh
```

This will:
- Create/update your `.env` file
- Enable paper trading mode
- Show you what needs to be configured

### Step 2: Add Your Credentials

Edit `.env` and add:

```bash
PAPER_TRADING=true
PAPER_TRADING_INITIAL_BALANCE=10000

# Required for market data (not for actual trading)
PK=your_private_key_here
BROWSER_ADDRESS=your_wallet_address_here
SPREADSHEET_URL=your_google_sheets_url
```

> **Note**: You still need valid Polymarket credentials because the bot fetches real market data. Your private key is **never used to sign transactions** in paper trading mode.

### Step 3: Start the Bot

```bash
python main.py
```

You'll see:

```
============================================================
🧪 PAPER TRADING MODE ENABLED
============================================================
All orders are simulated - no real trades will be executed
Market data is real-time from Polymarket API
------------------------------------------------------------
💰 Virtual Balance: $10,000.00 USDC
📊 Active Positions: 0
📝 Open Orders: 0
📈 Total Trades: 0
============================================================
```

### Step 4: Monitor Performance

Open a second terminal:

```bash
# One-time report
python view_paper_report.py

# Auto-refresh every 30 seconds
watch -n 30 python view_paper_report.py
```

## What to Expect

### First Few Minutes

The bot will:
1. Connect to Polymarket WebSocket (real-time order book data)
2. Load markets from your Google Sheet
3. Start analyzing spreads and liquidity
4. Place simulated orders on both sides (YES/NO)

### Order Behavior

Paper trading simulates realistic order behavior:
- **Orders placed**: Logged but not sent to Polymarket
- **Order fills**: Simulated based on market price movements
- **Position tracking**: Average prices calculated like real trading
- **Balance updates**: Virtual USDC tracked in real-time

### After 1 Hour

You should see:
- Several simulated trades executed
- Positions in multiple markets
- Initial P&L forming (could be positive or negative)

### After 24 Hours

Good time to evaluate:
- Total trades executed
- Win rate
- P&L percentage
- Which markets performed best

## Demo for Investors (YC Pitch)

### Setup (Before Meeting)

1. Start the bot 30-60 minutes before your pitch:
   ```bash
   PAPER_TRADING=true python main.py
   ```

2. Let it accumulate some trades and P&L

3. Prepare a terminal with the report visible:
   ```bash
   watch -n 30 python view_paper_report.py
   ```

### During Pitch

**Show them:**

1. **Live Trading Activity**
   - Terminal 1: Bot logs showing order placement
   - Terminal 2: Performance report updating in real-time

2. **Key Metrics**
   - Virtual balance starting at $10K
   - Current P&L (hopefully positive!)
   - Number of trades executed
   - Win rate percentage

3. **Risk Management**
   - Position limits being respected
   - Automatic position merging
   - Stop-loss logic in action

4. **Scalability**
   - "This is one bot with $10K"
   - "Imagine 100 users with $1M total"
   - "Same algorithms, distributed across markets"

**Talking Points:**

> "This bot is currently paper trading on Polymarket using real market data. It's automatically providing liquidity to prediction markets, earning yield from three sources: liquidity rewards, spread capture, and holding rewards. The algorithms you're seeing have been running for [X hours/days] and generated [Y%] return on $10K virtual capital."

### Export Data for Pitch Deck

```bash
# Copy trade history to Excel/Google Sheets
cp paper_trading/trades.csv ~/trades_export.csv

# Screenshot the performance report
python view_paper_report.py > performance_report.txt
```

## Understanding the Numbers

### Performance Report Breakdown

```
Initial Balance:          $10,000.00   ← Starting capital
USDC Balance:             $9,850.00    ← Available cash
Position Value:             $200.00    ← Holdings value
Current Balance:         $10,050.00    ← Total = USDC + positions
------------------------------------------------------------
P&L:                         $50.00 (+0.50%)  ← Profit/Loss
```

**What This Means:**
- You started with $10K
- Currently have $9,850 in cash
- Hold $200 in market positions
- Total value is $10,050
- Made $50 profit (0.5% return)

### Trade Types

| Icon | Type | Description |
|------|------|-------------|
| 🟢 | BUY | Opened long position |
| 🔴 | SELL | Closed position for profit |
| 🔄 | MERGE | Combined YES/NO positions to recover collateral |

### Win Rate Calculation

**Simple version** (current):
- Counts SELL trades above certain thresholds

**Future version** (roadmap):
- Compare sell price vs. average buy price
- Only count as "win" if sold for profit

## Comparing to Real Trading

### When to Switch to Real Money

Before going live, make sure:

✅ Paper trading ran for at least 24-48 hours
✅ P&L is positive (or you understand why it's negative)
✅ No errors or crashes occurred
✅ Bot respected all position limits
✅ You reviewed the trade log and understand behavior

### Differences to Expect

When you switch to real trading:

| Aspect | Paper Trading | Real Trading |
|--------|---------------|--------------|
| **Order fills** | Simulated/instant | Gradual, market-dependent |
| **Costs** | None | Gas fees (~$0.01-0.10 per tx) |
| **Slippage** | Not modeled | Can affect large orders |
| **Market impact** | None | Your orders affect book |
| **Risk** | Zero | Real money at risk |

**Recommendation**: Start real trading with 10-20% of your paper trading capital to validate performance.

## Troubleshooting

### "No module named 'pandas'"

Install dependencies:
```bash
pip install pandas python-dotenv
```

Or full requirements:
```bash
pip install -r requirements.txt
```

### Bot connects but no orders placed

**Check:**
1. Google Sheets has markets configured
2. Spreads are within acceptable range
3. Initial balance is sufficient for order sizes

**Debug:**
```bash
# Check what markets are loaded
grep "market" logs or terminal output
```

### "Authentication failed"

Even for paper trading, you need valid credentials for market data:
- PK must be a valid Ethereum private key
- BROWSER_ADDRESS must match the PK

### Paper trading state corrupted

**Reset:**
```bash
rm -rf paper_trading/
python main.py  # Will create fresh state
```

## Next Steps

### Phase 1: Validate Strategy (Now)

- [x] Paper trading mode implemented ✅
- [ ] Run for 48-72 hours
- [ ] Analyze performance
- [ ] Adjust parameters in Google Sheet
- [ ] Iterate until consistently profitable

### Phase 2: Real Trading (Soon)

- [ ] Switch PAPER_TRADING=false
- [ ] Start with small capital ($100-500)
- [ ] Monitor closely for first 24 hours
- [ ] Compare to paper trading results
- [ ] Scale up gradually

### Phase 3: Product Business (Future)

Based on your MVP summary, here's the path:

**Features to Build:**

1. **Multi-User Vault** (3-4 weeks)
   - Smart contract for pooled deposits
   - User dashboard showing their share
   - Auto-compounding of rewards

2. **Web Dashboard** (2-3 weeks)
   - React/Next.js frontend
   - Real-time P&L tracking
   - Market allocation view
   - Withdraw/deposit interface

3. **Fee Structure** (1 week)
   - Management fee (1-2% annually)
   - Performance fee (10-20% of profits)
   - Smart contract for fee distribution

4. **Advanced Features** (4-6 weeks)
   - Reward tracker integration
   - Historical performance charts
   - Market selection optimization
   - Risk-adjusted position sizing

**Tech Stack for Product:**
- **Backend**: FastAPI (Python) + PostgreSQL
- **Frontend**: Next.js + React
- **Blockchain**: QuickNode (Polygon RPC)
- **Infrastructure**: Vercel + AWS/Railway

**Estimated Yields:**
- Liquidity rewards: 4-10% APY
- Spread capture: 2-8% APY
- Holding rewards: 4% APY
- **Target: 10-20% total APY**

**Business Model:**
```
User deposits $1,000
  → Bot earns $150/year (15% yield)
  → 20% performance fee = $30
  → User keeps $120 (12% net)
  → You earn $30 per $1K managed

With $1M AUM = $30K/year revenue
With $10M AUM = $300K/year revenue
```

## Resources

- **Full Documentation**: [PAPER_TRADING.md](PAPER_TRADING.md)
- **Polymarket Docs**: https://docs.polymarket.com
- **Support**: Check GitHub issues or README

## Quick Commands Reference

```bash
# Setup
./setup_paper_trading.sh

# Run bot
python main.py

# View report (one-time)
python view_paper_report.py

# View report (continuous)
watch -n 30 python view_paper_report.py

# Check trade history
cat paper_trading/trades.csv

# Reset paper trading
rm -rf paper_trading/

# Switch to real trading
# Edit .env: PAPER_TRADING=false
```

---

**Ready to demo your bot? Run `python main.py` and show investors how market making generates consistent yield!** 🚀

**Questions?** Open an issue or check the docs.
