"""
Health check script for Docker containers.

Usage:
    python healthcheck.py [service_name]

Service names:
    - trading: Main trading bot
    - market-updater: Market discovery service
    - stats-updater: Statistics service
"""

import sys
import os
import time
from pathlib import Path


def check_trading_bot():
    """Check if trading bot is healthy."""
    # Check if main process is responsive
    # Look for recent activity in logs or state files

    # Check 1: Process is running (if we got here, Python is working)

    # Check 2: Check for recent log activity (last 5 minutes)
    log_file = Path('/app/logs/trading.log')
    if log_file.exists():
        mtime = log_file.stat().st_mtime
        age = time.time() - mtime
        if age > 300:  # 5 minutes
            print(f"UNHEALTHY: Log file not updated in {age:.0f} seconds")
            return False

    # Check 3: Check if positions directory exists and is writable
    positions_dir = Path('/app/positions')
    if not positions_dir.exists():
        print("UNHEALTHY: Positions directory missing")
        return False

    print("HEALTHY: Trading bot is running")
    return True


def check_market_updater():
    """Check if market updater is healthy."""
    # Check for recent data updates

    # Check 1: Data directory exists
    data_dir = Path('/app/data')
    if not data_dir.exists():
        print("UNHEALTHY: Data directory missing")
        return False

    # Check 2: Check for recent CSV files (should update hourly)
    csv_files = list(data_dir.glob('*.csv'))
    if csv_files:
        latest_mtime = max(f.stat().st_mtime for f in csv_files)
        age = time.time() - latest_mtime
        if age > 7200:  # 2 hours (market updater runs every hour)
            print(f"UNHEALTHY: No data updates in {age/3600:.1f} hours")
            return False

    print("HEALTHY: Market updater is running")
    return True


def check_stats_updater():
    """Check if stats updater is healthy."""
    # Check for recent stats updates

    # Check 1: Log file exists and is recent
    log_file = Path('/app/logs/stats-updater.log')
    if log_file.exists():
        mtime = log_file.stat().st_mtime
        age = time.time() - mtime
        if age > 14400:  # 4 hours (stats updater runs every 3 hours)
            print(f"UNHEALTHY: Stats not updated in {age/3600:.1f} hours")
            return False

    print("HEALTHY: Stats updater is running")
    return True


def main():
    """Main health check function."""
    if len(sys.argv) < 2:
        service = "trading"
    else:
        service = sys.argv[1]

    try:
        if service == "trading":
            healthy = check_trading_bot()
        elif service == "market-updater":
            healthy = check_market_updater()
        elif service == "stats-updater":
            healthy = check_stats_updater()
        else:
            print(f"Unknown service: {service}")
            sys.exit(1)

        if healthy:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"UNHEALTHY: Health check failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
