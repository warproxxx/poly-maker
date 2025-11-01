# Paper Trading Mode

🧪 **Test your Polymarket market-making strategies without risking real money**

Paper trading mode allows you to simulate trading with virtual funds while using real market data from Polymarket. This is perfect for:
- Testing and refining your trading strategies
- Demonstrating the bot to potential investors (YC pitches, etc.)
- Learning how the bot operates before going live
- Validating algorithm performance

## Quick Start

### 1. Enable Paper Trading

Create a `.env` file (or copy `.env.example`) and add:

```bash
PAPER_TRADING=true
PAPER_TRADING_INITIAL_BALANCE=10000

# You still need these for market data access
PK=your_private_key_here
BROWSER_ADDRESS=your_wallet_address_here
SPREADSHEET_URL=your_google_sheet_url
```

### 2. Run the Bot

```bash
python main.py
```

You'll see a banner indicating paper trading mode is active:

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

### 3. View Performance Report

While the bot is running or after stopping it:

```bash
python view_paper_report.py
```

## How It Works

### What's Simulated (Virtual)
- **Order Placement**: Orders are logged but not sent to Polymarket
- **Order Fills**: Simulated based on your order prices and market activity
- **Balances**: Virtual USDC balance starting at your configured amount
- **Positions**: Tracked internally with average prices
- **Merging**: Position merges are simulated and credited instantly

### What's Real
- **Market Data**: Real-time order book data via WebSocket
- **Prices**: Actual market prices from Polymarket
- **Trading Logic**: Same algorithms as real trading mode
- **Spread Calculations**: Based on live market conditions

## Features

### State Persistence

All paper trading data is saved to `paper_trading/` directory:

- `state.json` - Current balances, positions, and orders
- `trades.csv` - Complete trade history for analysis

You can stop and restart the bot without losing your paper trading session.

### Performance Tracking

The bot automatically generates performance reports every 5 minutes showing:
- Initial vs. current balance
- Profit/Loss ($ and %)
- Total trades executed
- Win rate
- Active positions
- Open orders

### Trade Logging

Every simulated trade is logged with:
- Timestamp
- Token ID
- Side (BUY/SELL/MERGE)
- Size
- Price
- Running balance

Export `paper_trading/trades.csv` to Excel/Google Sheets for detailed analysis.

## Example Use Cases

### Testing Strategies

Run the bot in paper trading mode for 24-48 hours to validate your parameters:

```bash
# .env
PAPER_TRADING=true
PAPER_TRADING_INITIAL_BALANCE=10000
```

Check performance:
```bash
python view_paper_report.py
```

### YC/Investor Demo

Start the bot during your pitch to show live trading:

```bash
# Terminal 1: Run the bot
PAPER_TRADING=true python main.py

# Terminal 2: Show periodic reports
watch -n 60 python view_paper_report.py
```

Investors can see:
- Real-time order placement
- Position management
- P&L tracking
- Risk management in action

### A/B Testing

Run multiple configurations simultaneously:

```bash
# Terminal 1: Conservative strategy
PAPER_TRADING=true python main.py

# Terminal 2: Aggressive strategy (different Google Sheet)
PAPER_TRADING=true SPREADSHEET_URL=aggressive_params python main.py
```

Compare results in `paper_trading/` directories.

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER_TRADING` | `false` | Enable/disable paper trading |
| `PAPER_TRADING_INITIAL_BALANCE` | `10000` | Starting USDC balance |

### Advanced: Multiple Sessions

To run multiple paper trading sessions, modify the state directory in `paper_trading_client.py`:

```python
self.state_dir = f"paper_trading_{session_name}"
```

## Understanding the Reports

### Performance Report

```
📊 PAPER TRADING PERFORMANCE REPORT
============================================================
Initial Balance:          $10,000.00
USDC Balance:             $9,850.00
Position Value:             $200.00
Current Balance:         $10,050.00
------------------------------------------------------------
P&L:                         $50.00 (+0.50%)
============================================================
Total Trades:                    25
Win Rate:                     60.0%
Active Positions:                 3
Open Orders:                      6
------------------------------------------------------------
Session Start:       2024-11-01T10:00:00
Last Update:         2024-11-01T15:30:00
============================================================
```

**Key Metrics:**
- **USDC Balance**: Available cash for new orders
- **Position Value**: Estimated value of holdings (size × avg price)
- **Current Balance**: Total portfolio value (USDC + positions)
- **P&L**: Profit/Loss since start
- **Win Rate**: Percentage of profitable trades (simplified)

### Trade Log

```
📈 RECENT TRADES (Last 10)
------------------------------------------------------------
🟢 BUY     100.00 @ $0.4500 | Balance: $9,550.00 | 2024-11-01 10:15:23
🔴 SELL     50.00 @ $0.5500 | Balance: $9,577.50 | 2024-11-01 10:45:12
🔄 MERGE    45.00 @ $1.0000 | Balance: $9,622.50 | 2024-11-01 11:20:45
...
```

**Emoji Legend:**
- 🟢 BUY - Long position
- 🔴 SELL - Close position
- 🔄 MERGE - Position merge (recovered collateral)

## Switching to Real Trading

Once you've validated your strategy:

1. **Update .env:**
   ```bash
   PAPER_TRADING=false
   ```

2. **Ensure funds:**
   - Check your Polymarket wallet has sufficient USDC
   - Approve USDC spending on the Polymarket contract

3. **Start small:**
   - Use conservative parameters initially
   - Lower `trade_size` and `max_size` in Google Sheet

4. **Monitor closely:**
   - Watch the first few hours carefully
   - Verify orders are placing correctly
   - Check gas fees and transaction costs

## Tips for Accurate Simulation

### Good Practices

✅ Run paper trading for at least 24 hours to see different market conditions
✅ Use realistic initial balance ($1K-$10K)
✅ Test during high-volatility periods
✅ Review `trades.csv` to understand bot behavior
✅ Adjust Google Sheet parameters between tests

### Limitations

⚠️ Paper trading doesn't account for:
- Gas fees (Polygon)
- Order fill delays
- Slippage on large orders
- Market impact of your orders
- Network congestion

⚠️ Fill simulation is simplified in MVP:
- Orders may fill instantly vs. real gradual fills
- No partial fill delays
- Perfect execution assumed

For production use, monitor initial real trades carefully and compare to paper trading results.

## Troubleshooting

### "No paper trading state found"

**Solution**: Start the bot with `PAPER_TRADING=true` first to create the state file.

### Orders not filling

**Solution**: Paper trading fills are currently simulated gradually. In the MVP, fills happen based on periodic checks. This will be enhanced to match real order book trades in future versions.

### Report shows $0 balance

**Solution**: Check `paper_trading/state.json` - if corrupted, delete it and restart the bot to create fresh state.

### Can't find trades.csv

**Solution**: The file is created after the first simulated trade. Place at least one order first.

## Roadmap

Future enhancements for paper trading:

- [ ] Real-time order matching against actual market trades
- [ ] Historical backtesting mode
- [ ] Web dashboard for paper trading visualization
- [ ] Compare paper vs. real trading performance
- [ ] Multi-account simulation (for vault product testing)
- [ ] Slippage and gas fee simulation
- [ ] Export reports to PDF for investor presentations

## Support

For issues or questions:
- Check the main README.md
- Review `paper_trading/state.json` for state details
- Enable verbose logging in `main.py`

---

**Ready to go live?** Make sure to thoroughly test your strategies in paper trading mode first. Good luck! 🚀
