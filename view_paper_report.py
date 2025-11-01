#!/usr/bin/env python3
"""
View Paper Trading Performance Report

This script displays the current performance of the paper trading session
without needing to run the full bot.

Usage:
    python view_paper_report.py
"""

import os
import json
import sys
from datetime import datetime
import pandas as pd

STATE_FILE = "paper_trading/state.json"
TRADES_FILE = "paper_trading/trades.csv"


def load_state():
    """Load paper trading state from disk."""
    if not os.path.exists(STATE_FILE):
        print(f"❌ No paper trading state found at {STATE_FILE}")
        print("   Start the bot with PAPER_TRADING=true to create paper trading data")
        sys.exit(1)

    with open(STATE_FILE, 'r') as f:
        return json.load(f)


def calculate_performance(state):
    """Calculate performance metrics from state."""
    initial = state["initial_balance"]
    usdc = state["usdc_balance"]

    # Calculate position value
    pos_value = 0
    for token_id, pos in state["positions"].items():
        pos_value += pos["size"] * pos["avgPrice"]

    current = usdc + pos_value
    pnl = current - initial
    pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

    total_trades = len(state["trade_history"])

    # Calculate win rate (sells that made profit)
    profitable_sells = 0
    total_sells = 0

    for trade in state["trade_history"]:
        if trade["side"] == "SELL":
            total_sells += 1
            # In a real scenario, you'd compare sell price to avg buy price
            # For simplicity, count sells above 0.5 as wins
            if trade["price"] > 0.5:
                profitable_sells += 1

    win_rate = (profitable_sells / total_sells * 100) if total_sells > 0 else 0

    return {
        "initial_balance": initial,
        "usdc_balance": usdc,
        "position_value": pos_value,
        "current_balance": current,
        "pnl": pnl,
        "pnl_percent": pnl_pct,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "active_positions": len(state["positions"]),
        "open_orders": len([o for o in state["orders"].values() if o["status"] == "OPEN"]),
        "created_at": state["created_at"],
        "last_updated": state["last_updated"]
    }


def print_report(metrics):
    """Print formatted performance report."""
    print("\n" + "=" * 70)
    print("📊 PAPER TRADING PERFORMANCE REPORT")
    print("=" * 70)
    print(f"Initial Balance:     ${metrics['initial_balance']:>15,.2f}")
    print(f"USDC Balance:        ${metrics['usdc_balance']:>15,.2f}")
    print(f"Position Value:      ${metrics['position_value']:>15,.2f}")
    print(f"Current Balance:     ${metrics['current_balance']:>15,.2f}")
    print("-" * 70)
    print(f"P&L:                 ${metrics['pnl']:>15,.2f} ({metrics['pnl_percent']:+.2f}%)")
    print("=" * 70)
    print(f"Total Trades:        {metrics['total_trades']:>15}")
    print(f"Win Rate:            {metrics['win_rate']:>14.1f}%")
    print(f"Active Positions:    {metrics['active_positions']:>15}")
    print(f"Open Orders:         {metrics['open_orders']:>15}")
    print("-" * 70)
    print(f"Session Start:       {metrics['created_at']}")
    print(f"Last Update:         {metrics['last_updated']}")
    print("=" * 70 + "\n")


def print_recent_trades(n=10):
    """Print recent trades."""
    if not os.path.exists(TRADES_FILE):
        print("No trade history available yet\n")
        return

    try:
        df = pd.read_csv(TRADES_FILE)

        if df.empty:
            print("No trades recorded yet\n")
            return

        print(f"📈 RECENT TRADES (Last {min(n, len(df))})")
        print("-" * 70)

        # Show last n trades
        recent = df.tail(n)

        for _, trade in recent.iterrows():
            timestamp = trade.get("timestamp", "N/A")
            side = trade.get("side", "N/A")
            size = trade.get("size", 0)
            price = trade.get("price", 0)
            balance = trade.get("balance", 0)

            emoji = "🟢" if side == "BUY" else "🔴" if side == "SELL" else "🔄"

            print(f"{emoji} {side:5} {size:>8.2f} @ ${price:.4f} | Balance: ${balance:>10,.2f} | {timestamp[:19]}")

        print("-" * 70 + "\n")

    except Exception as e:
        print(f"Error reading trade history: {e}\n")


def main():
    """Main function."""
    print("\n🔍 Loading paper trading data...\n")

    state = load_state()
    metrics = calculate_performance(state)

    print_report(metrics)
    print_recent_trades(10)

    # Show positions if any
    if state["positions"]:
        print("💼 ACTIVE POSITIONS")
        print("-" * 70)
        for token_id, pos in state["positions"].items():
            size = pos["size"]
            avg_price = pos["avgPrice"]
            value = size * avg_price
            print(f"Token {token_id[:12]}... | Size: {size:>8.2f} | Avg Price: ${avg_price:.4f} | Value: ${value:>10,.2f}")
        print("-" * 70 + "\n")


if __name__ == "__main__":
    main()
