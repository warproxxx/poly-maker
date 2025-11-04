# Docker Deployment Guide

Complete guide for running the Polymarket Liquidity Bot in Docker containers.

---

## Quick Start

### 1. Prerequisites

- Docker 20.10+ installed
- Docker Compose 2.0+ installed
- Your Polymarket private key and wallet address
- Google Sheets URL (for market configuration)

### 2. Initialize Setup

```bash
make init
```

This creates:
- `.env` file from `.env.docker`
- Required directories (`logs/`, `data/`, `positions/`)

### 3. Configure Environment

Edit `.env` and add your credentials:

```bash
# Required
PK=your_private_key_here
BROWSER_ADDRESS=your_wallet_address_here
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_ID/edit

# Optional: For Google Sheets write access
# Place credentials.json in project root
GOOGLE_CREDENTIALS_PATH=/app/credentials.json
```

### 4. Build and Start

```bash
# Build images
make build

# Start all services
make up

# View logs
make logs
```

**That's it!** The bot is now running in Docker.

---

## Architecture

The system runs **3 separate services**:

```
┌─────────────────────┐
│   trading-bot       │  ← Main bot (market making)
│   Port: None        │
│   WebSocket: Yes    │
└─────────────────────┘

┌─────────────────────┐
│  market-updater     │  ← Scans markets every hour
│   Port: None        │
│   Updates: Sheets   │
└─────────────────────┘

┌─────────────────────┐
│  stats-updater      │  ← Updates stats every 3 hours
│   Port: None        │
│   Updates: Sheets   │
└─────────────────────┘
```

All services:
- Share the same `.env` configuration
- Mount persistent volumes for logs/data
- Auto-restart on failure
- Include health checks

---

## Services

### Trading Bot (`trading-bot`)

**Purpose:** Main market making bot

**What it does:**
- Connects to Polymarket WebSocket
- Places and manages orders
- Handles inventory and risk
- Uses dynamic spreads

**Command:** `python main.py`

**Logs:** `logs/trading.log`

**Health check:** Every 60 seconds

---

### Market Updater (`market-updater`)

**Purpose:** Market discovery and analysis

**What it does:**
- Scans all Polymarket markets
- Calculates volatility metrics
- Detects market regimes
- Ranks opportunities by Sharpe ratio
- Updates Google Sheets

**Command:** `python update_markets.py`

**Logs:** `logs/market-updater.log`

**Health check:** Every 120 seconds

**Runs:** Every hour (configurable)

---

### Stats Updater (`stats-updater`)

**Purpose:** Account statistics

**What it does:**
- Tracks positions
- Calculates P&L
- Updates earnings
- Writes to Google Sheets

**Command:** `python update_stats.py`

**Logs:** `logs/stats-updater.log`

**Health check:** Every 180 seconds

**Runs:** Every 3 hours (configurable)

---

## Common Commands

### Basic Operations

```bash
# Start all services
make up

# Stop all services
make down

# Restart all services
make restart

# View all logs (live)
make logs

# View specific service logs
make logs-trading
make logs-market
make logs-stats

# Check service status
make ps

# Check health
make health
```

### Development

```bash
# Start in foreground (see logs directly)
make dev

# Open shell in trading bot
make shell

# Validate configuration
make config

# Run tests
make test
```

### Restart Individual Services

```bash
# Restart only trading bot
make restart-trading

# Restart only market updater
make restart-market

# Restart only stats updater
make restart-stats
```

### Maintenance

```bash
# Backup data and logs
make backup

# Clean up everything
make clean

# Prune unused Docker resources
make prune
```

---

## File Structure

```
poly-maker/
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Service orchestration
├── .dockerignore          # Files to exclude from image
├── Makefile               # Convenience commands
├── healthcheck.py         # Health check script
├── .env                   # Your configuration (git-ignored)
├── .env.docker            # Example Docker config
├── credentials.json       # Google credentials (optional)
│
├── logs/                  # Mounted volume
│   ├── trading.log
│   ├── market-updater.log
│   └── stats-updater.log
│
├── data/                  # Mounted volume
│   └── *.csv             # Price history data
│
└── positions/             # Mounted volume
    └── *.json            # Risk management data
```

---

## Volumes

### Persistent Data

All important data is stored in mounted volumes:

```yaml
volumes:
  - ./logs:/app/logs          # Log files
  - ./data:/app/data          # Price history
  - ./positions:/app/positions # Position data
  - ./credentials.json:/app/credentials.json:ro  # Google credentials
```

**Benefits:**
- Data persists across container restarts
- Easy backup (just copy directories)
- Can inspect files from host machine
- Logs accessible without entering container

---

## Networking

All services run on a private Docker network:

```yaml
networks:
  polymarket-network:
    driver: bridge
```

**Benefits:**
- Services can communicate if needed
- Isolated from host network
- No port exposure (more secure)

---

## Health Checks

Each service has automatic health checks:

```yaml
healthcheck:
  test: ["CMD", "python", "healthcheck.py", "trading"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**What it checks:**
- Trading bot: Log file freshness, positions directory
- Market updater: Data file updates
- Stats updater: Stats log freshness

**Auto-restart:** If health check fails 3 times, container restarts

**View health:**
```bash
make health
# or
docker compose ps
```

---

## Configuration

### Environment Variables

All configuration via `.env` file:

```bash
# Feature flags
USE_DYNAMIC_SPREADS=true
DRY_RUN_MODE=false

# Update intervals
UPDATE_INTERVAL=5
MARKET_DISCOVERY_INTERVAL=3600

# Trading parameters
BASE_SPREAD_BPS=20
ABSOLUTE_MAX_POSITION=250

# See .env.docker for all options
```

### Override for Specific Service

Edit `docker-compose.yml`:

```yaml
services:
  trading-bot:
    environment:
      - UPDATE_INTERVAL=3  # Override for this service only
      - BASE_SPREAD_BPS=30
```

---

## Logs

### View Logs

```bash
# All services, live
make logs

# Specific service
make logs-trading

# Last 100 lines
docker compose logs --tail=100 trading-bot

# Since specific time
docker compose logs --since=30m trading-bot
```

### Log Files

Logs are written to mounted volumes:

```bash
# View from host
tail -f logs/trading.log
tail -f logs/market-updater.log
tail -f logs/stats-updater.log
```

### Log Rotation

Docker automatically rotates logs:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"    # Max 10MB per file
    max-file: "3"      # Keep 3 files
```

Total: 30MB per service max

---

## Debugging

### Check Container Status

```bash
make ps
# or
docker compose ps
```

### View Container Logs

```bash
# All logs
make logs

# Last 50 lines
docker compose logs --tail=50
```

### Enter Container Shell

```bash
# Trading bot
make shell

# Market updater
make shell-market

# Run commands inside container
docker compose exec trading-bot python config.py
```

### Check Configuration

```bash
make config
```

### Inspect Container

```bash
docker inspect polymarket-trading-bot
```

### View Resource Usage

```bash
docker stats
```

---

## Production Deployment

### 1. Set Environment to Production

```bash
# .env
DRY_RUN_MODE=false
LOG_TO_FILE=true
LOG_LEVEL=INFO
```

### 2. Enable Auto-Restart

Already configured in `docker-compose.yml`:

```yaml
restart: unless-stopped
```

Containers will:
- Auto-start on system boot
- Restart on failure
- Stay stopped if manually stopped

### 3. Set Up Monitoring

#### Option A: View Logs

```bash
# Monitor logs
make logs

# Or use external log aggregation
# (Datadog, Papertrail, CloudWatch, etc.)
```

#### Option B: Enable Prometheus + Grafana

Uncomment monitoring section in `docker-compose.yml`:

```bash
# Edit docker-compose.yml, uncomment monitoring section
docker compose up -d prometheus grafana

# Access Grafana
# http://localhost:3000
# Default: admin/admin
```

### 4. Set Up Backups

```bash
# Manual backup
make backup

# Automated backup (cron)
crontab -e

# Add:
0 0 * * * cd /path/to/poly-maker && make backup
```

### 5. Secure Credentials

```bash
# Ensure .env is not committed
git status  # Should not see .env

# Set proper permissions
chmod 600 .env
chmod 600 credentials.json
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker compose logs trading-bot
```

**Common issues:**
- Missing `.env` file → Run `make init`
- Invalid PK or BROWSER_ADDRESS → Check `.env`
- Missing credentials.json → Either provide it or remove from volumes

### Health Check Failing

**Check health status:**
```bash
make health
```

**Common issues:**
- Service crashed → Check logs
- No recent updates → Service might be stuck
- Permission issues → Check file permissions

### High Memory Usage

**Check resource usage:**
```bash
docker stats
```

**Solutions:**
- Reduce `MAX_WORKERS` in `.env`
- Increase `UPDATE_INTERVAL`
- Add memory limits to docker-compose.yml:

```yaml
services:
  trading-bot:
    mem_limit: 512m
```

### Logs Not Appearing

**Check log volume:**
```bash
ls -la logs/
```

**Check permissions:**
```bash
# Logs directory should be writable
chmod 755 logs/
```

**Check Docker logging:**
```bash
docker compose logs
```

### Can't Connect to Polymarket

**Check network:**
```bash
docker compose exec trading-bot ping api.polymarket.com
```

**Check WebSocket:**
```bash
docker compose exec trading-bot curl -I https://ws-subscriptions-clob.polymarket.com
```

**Firewall issues:**
- Ensure outbound HTTPS (443) allowed
- Ensure WebSocket connections allowed

---

## Advanced Usage

### Run Single Service

```bash
# Only trading bot
docker compose up trading-bot

# Only market updater
docker compose up market-updater
```

### Scale Services

```bash
# Run multiple market updaters (parallel discovery)
docker compose up --scale market-updater=3
```

### Custom Docker Image

```bash
# Build with custom tag
docker build -t my-polybot:v1.0 .

# Run custom image
docker run -it --env-file .env my-polybot:v1.0
```

### Development Mode

```bash
# Mount code as volume (hot reload)
docker compose -f docker-compose.dev.yml up
```

Create `docker-compose.dev.yml`:
```yaml
services:
  trading-bot:
    volumes:
      - .:/app  # Mount entire codebase
      - ./logs:/app/logs
```

---

## Security Best Practices

### 1. Never Commit Secrets

```bash
# Check before committing
git status

# Should NOT see:
# - .env
# - credentials.json
# - *.pem
# - *.key
```

### 2. Use Non-Root User

Already configured in Dockerfile:

```dockerfile
USER polybot  # Non-root user
```

### 3. Read-Only Credentials

credentials.json mounted as read-only:

```yaml
volumes:
  - ./credentials.json:/app/credentials.json:ro
```

### 4. Network Isolation

Services on private network:

```yaml
networks:
  polymarket-network:
    driver: bridge
```

### 5. Resource Limits

Add to `docker-compose.yml`:

```yaml
services:
  trading-bot:
    mem_limit: 512m
    cpus: 1.0
```

---

## Upgrading

### Update Code

```bash
# Pull latest code
git pull origin main

# Rebuild images
make build

# Restart services
make restart
```

### Update Dependencies

```bash
# Edit pyproject.toml
# Update version numbers

# Rebuild
make build

# Restart
make restart
```

---

## Uninstalling

```bash
# Stop and remove everything
make clean

# Remove images
docker rmi poly-maker_trading-bot
docker rmi poly-maker_market-updater
docker rmi poly-maker_stats-updater

# Remove volumes (CAUTION: deletes data!)
docker volume rm poly-maker_prometheus-data
docker volume rm poly-maker_grafana-data

# Remove directories
rm -rf logs/ data/ positions/
```

---

## Support

### Check Documentation
1. `CONFIGURATION.md` - Configuration guide
2. `ENHANCEMENTS.md` - Feature documentation
3. `README.md` - General usage

### Debug Checklist
- [ ] Check `.env` has correct values
- [ ] Check `make health` output
- [ ] Check `make logs` for errors
- [ ] Check `docker compose ps` status
- [ ] Check `docker stats` for resources
- [ ] Check `make config` validates

### Get Help
1. Check logs: `make logs`
2. Validate config: `make config`
3. Open GitHub issue with logs

---

## Performance Tuning

### For VPS/Cloud

```bash
# .env
UPDATE_INTERVAL=5
MAX_WORKERS=3
MARKET_DISCOVERY_INTERVAL=3600
```

### For Powerful Server

```bash
# .env
UPDATE_INTERVAL=3
MAX_WORKERS=10
MARKET_DISCOVERY_INTERVAL=1800
```

### For Limited Resources

```bash
# .env
UPDATE_INTERVAL=10
MAX_WORKERS=2
MARKET_DISCOVERY_INTERVAL=7200
```

---

## Conclusion

You now have:
- ✅ Fully containerized trading bot
- ✅ 3 separate services (isolation)
- ✅ Auto-restart on failure
- ✅ Health checks
- ✅ Persistent volumes
- ✅ Easy management (Makefile)
- ✅ Production-ready setup

**Start trading:**
```bash
make init    # Initialize
make build   # Build images
make up      # Start services
make logs    # Monitor
```

Happy trading! 🚀🐳
