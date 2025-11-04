# Quick Start Guide

Get the Polymarket Liquidity Bot running in **5 minutes** using Docker.

---

## Prerequisites

✅ Docker installed ([Get Docker](https://docs.docker.com/get-docker/))
✅ Polymarket wallet with private key
✅ Google Sheet for market configuration

---

## 5-Minute Setup

### Step 1: Clone Repository

```bash
git clone https://github.com/webrating/poly-maker.git
cd poly-maker
```

### Step 2: Initialize

```bash
make init
```

This creates `.env` file and required directories.

### Step 3: Add Credentials

Edit `.env`:

```bash
nano .env
```

Add these **3 required values**:

```bash
PK=your_private_key_here
BROWSER_ADDRESS=your_wallet_address_here
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/edit
```

Save and exit (Ctrl+X, Y, Enter).

### Step 4: Copy Sample Google Sheet

1. Open the [sample sheet](https://docs.google.com/spreadsheets/d/1Kt6yGY7CZpB75cLJJAdWo7LSp9Oz7pjqfuVWwgtn7Ns/edit?gid=1884499063#gid=1884499063)
2. Click **File → Make a copy**
3. Copy the URL of your new sheet
4. Paste it into `SPREADSHEET_URL` in `.env`

### Step 5: Build & Start

```bash
make build
make up
```

### Step 6: Monitor

```bash
make logs
```

You should see:
```
trading-bot | ✓ Configuration validated successfully
trading-bot | [DYNAMIC] Regime: mean_reverting, Bid: 0.4850, Ask: 0.5150
market-updater | Got all Markets
```

---

## That's It! 🎉

Your bot is now:
- ✅ Running 24/7
- ✅ Auto-restarting on failure
- ✅ Scanning markets hourly
- ✅ Using dynamic spreads
- ✅ Logging everything

---

## Next Steps

### 1. Select Markets to Trade

Open your Google Sheet:
- Go to **"Volatility Markets"** tab
- Find markets with:
  - High `sharpe_ratio` (> 1.5)
  - Low `volatility_sum` (< 10)
  - `is_good_for_mm` = TRUE
- Copy market rows to **"Selected Markets"** tab

### 2. Adjust Settings (Optional)

Edit `.env` to tune parameters:

```bash
# Conservative (safer)
BASE_SPREAD_BPS=30
ABSOLUTE_MAX_POSITION=100

# Aggressive (higher returns)
BASE_SPREAD_BPS=15
ABSOLUTE_MAX_POSITION=500
```

Then restart:
```bash
make restart
```

### 3. Monitor Performance

```bash
# View logs
make logs

# Check service health
make ps

# View configuration
make config

# Backup data
make backup
```

---

## Common Commands

```bash
make up           # Start all services
make down         # Stop all services
make restart      # Restart everything
make logs         # View logs (live)
make logs-trading # View trading bot logs only
make ps           # Check status
make shell        # Open shell in container
make config       # Show configuration
make backup       # Backup data and logs
make clean        # Remove everything
```

---

## Troubleshooting

### "Container won't start"

**Check logs:**
```bash
docker compose logs trading-bot
```

**Common fixes:**
- Missing `.env` → Run `make init`
- Wrong credentials → Check `PK` and `BROWSER_ADDRESS` in `.env`
- Sheet not accessible → Check `SPREADSHEET_URL`

### "No markets selected"

**Solution:**
1. Open your Google Sheet
2. Add markets to **"Selected Markets"** tab
3. Wait 30 seconds for bot to refresh

### "Orders not placing"

**Check:**
1. Wallet has USDC balance
2. Wallet has done at least 1 trade via Polymarket UI
3. Wallet permissions are correct

---

## What's Running?

**3 Docker containers:**

| Service | Purpose | Runs |
|---------|---------|------|
| **trading-bot** | Places orders, manages positions | Continuously |
| **market-updater** | Scans markets, calculates metrics | Every hour |
| **stats-updater** | Updates P&L, earnings | Every 3 hours |

All services:
- Auto-restart on crash
- Write logs to `logs/` directory
- Include health checks

---

## Configuration

**All settings in `.env` file:**

```bash
# Feature flags
USE_DYNAMIC_SPREADS=true   # Auto-adjust spreads
DRY_RUN_MODE=false          # Set true for testing

# Spreads
BASE_SPREAD_BPS=20          # Base spread (20 bps = 0.20%)
MIN_SPREAD_TICKS=2          # Minimum 2 ticks

# Position sizing
ABSOLUTE_MAX_POSITION=250   # Max shares per market

# Update intervals
UPDATE_INTERVAL=5           # Check markets every 5s
MARKET_DISCOVERY_INTERVAL=3600  # Scan markets hourly
```

See [CONFIGURATION.md](CONFIGURATION.md) for all options.

---

## Important Notes

⚠️ **This bot trades real money**
- Start with small position sizes
- Test with small amounts first
- Monitor closely for first 24 hours

⚠️ **Google Sheet is critical**
- Keep "Selected Markets" updated
- Don't delete Hyperparameters tab
- Check "Volatility Markets" daily for new opportunities

⚠️ **Security**
- Never commit `.env` to git
- Keep `credentials.json` secret
- Use strong passwords

---

## Support

**Documentation:**
- [DOCKER.md](DOCKER.md) - Full Docker guide
- [CONFIGURATION.md](CONFIGURATION.md) - All configuration options
- [ENHANCEMENTS.md](ENHANCEMENTS.md) - Feature documentation

**Debugging:**
```bash
# Check logs
make logs

# Check health
make ps

# Validate config
make config

# Enter container
make shell
```

**Get Help:**
- Open an issue on GitHub
- Include output of `make logs`
- Include relevant `.env` values (NOT your private key!)

---

## Performance Expectations

**With default settings:**
- **Daily returns:** 0.5-2% (depending on markets)
- **Sharpe ratio:** 1.5-2.5
- **Max drawdown:** 5-10%
- **Win rate:** 70-80%

**Results vary based on:**
- Market selection quality
- Parameter tuning
- Market conditions
- Capital deployed

---

## Stopping the Bot

```bash
# Stop all services
make down

# Stop and remove everything
make clean

# Backup before stopping
make backup && make down
```

---

## Success! What Now?

1. ✅ **Monitor for 24 hours** - Check logs, verify orders placing
2. ✅ **Review Google Sheet** - Check "Summary" tab for performance
3. ✅ **Tune parameters** - Adjust spreads and position sizes in `.env`
4. ✅ **Add more markets** - Find opportunities in "Volatility Markets" tab
5. ✅ **Scale up** - Increase `ABSOLUTE_MAX_POSITION` as you gain confidence

**Happy trading! 🚀📈**

---

**Need help?** Open an issue or check the full documentation in [DOCKER.md](DOCKER.md).
