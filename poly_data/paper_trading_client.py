"""
Paper Trading Client for Polymarket

This module provides a simulated trading environment that mimics the real PolymarketClient
but doesn't execute actual trades. It's used for:
- Testing trading strategies without risking real money
- Demonstrating the bot to potential investors
- Validating algorithm performance before going live

The client maintains virtual positions, balances, and orders while using real market data
from the Polymarket API for accurate simulation.
"""

import os
import json
import time
import uuid
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from poly_data.polymarket_client import PolymarketClient

load_dotenv()


class PaperTradingClient:
    """
    A wrapper around PolymarketClient that simulates trading without executing real orders.

    This class maintains the same interface as PolymarketClient but all order operations
    are simulated. Market data queries still use the real API for accurate simulation.

    State is persisted to disk so the bot can be stopped and resumed without losing
    virtual positions and balances.
    """

    def __init__(self, pk='default'):
        """
        Initialize the paper trading client.

        Args:
            pk (str): Private key identifier (not used in paper trading but kept for compatibility)
        """
        print("=" * 60)
        print("🧪 PAPER TRADING MODE ENABLED")
        print("=" * 60)
        print("All orders are simulated - no real trades will be executed")
        print("Market data is real-time from Polymarket API")
        print("-" * 60)

        # Initialize real client for market data queries
        self.real_client = PolymarketClient(pk)

        # Copy necessary attributes from real client
        self.client = self.real_client.client
        self.browser_wallet = self.real_client.browser_wallet
        self.web3 = self.real_client.web3
        self.addresses = self.real_client.addresses

        # Paper trading state directory
        self.state_dir = "paper_trading"
        os.makedirs(self.state_dir, exist_ok=True)

        self.state_file = os.path.join(self.state_dir, "state.json")
        self.trades_file = os.path.join(self.state_dir, "trades.csv")

        # Load or initialize paper trading state
        self.state = self._load_state()

        print(f"💰 Virtual Balance: ${self.state['usdc_balance']:,.2f} USDC")
        print(f"📊 Active Positions: {len(self.state['positions'])}")
        print(f"📝 Open Orders: {len(self.state['orders'])}")
        print(f"📈 Total Trades: {len(self.state['trade_history'])}")
        print("=" * 60)

    def _load_state(self):
        """Load paper trading state from disk or create new state."""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                print(f"📂 Loaded existing paper trading state from {self.state_file}")
                return state
        else:
            # Initialize new paper trading state
            initial_balance = float(os.getenv("PAPER_TRADING_INITIAL_BALANCE", 10000))
            state = {
                "usdc_balance": initial_balance,
                "initial_balance": initial_balance,
                "positions": {},  # {token_id: {"size": float, "avgPrice": float, "side": "YES/NO"}}
                "orders": {},  # {order_id: {...}}
                "trade_history": [],
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            self._save_state()
            print(f"🆕 Created new paper trading state with ${initial_balance:,.2f} initial balance")
            return state

    def _save_state(self):
        """Save paper trading state to disk."""
        self.state["last_updated"] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _log_trade(self, trade_data):
        """Log a simulated trade to CSV for analysis."""
        trade_data["timestamp"] = datetime.now().isoformat()

        # Append to CSV
        df = pd.DataFrame([trade_data])
        if os.path.exists(self.trades_file):
            df.to_csv(self.trades_file, mode='a', header=False, index=False)
        else:
            df.to_csv(self.trades_file, mode='w', header=True, index=False)

    def _simulate_order_fill(self, order_id):
        """
        Simulate order fill based on current market conditions.

        In a more sophisticated version, this would check if the market price
        has crossed the order price. For now, we simulate immediate fills
        for simplicity during the MVP phase.

        Args:
            order_id (str): Order ID to potentially fill
        """
        if order_id not in self.state["orders"]:
            return

        order = self.state["orders"][order_id]

        # For MVP: simulate partial fills over time
        # In production, this would match against real order book trades
        if order["status"] == "OPEN":
            # Simulate gradual fills (20% of size per check)
            fill_amount = min(order["size"], order["original_size"] * 0.2)

            if fill_amount > 0:
                self._execute_fill(order_id, fill_amount, order["price"])

    def _execute_fill(self, order_id, size, price):
        """
        Execute a simulated order fill and update positions/balances.

        Args:
            order_id (str): Order ID being filled
            size (float): Amount filled
            price (float): Fill price
        """
        order = self.state["orders"][order_id]
        token_id = order["token_id"]
        side = order["side"]

        # Update order
        order["size"] -= size
        order["size_matched"] += size

        if order["size"] < 0.01:  # Fully filled
            order["status"] = "MATCHED"
            order["filled_at"] = datetime.now().isoformat()

        # Update balance
        cost = size * price if side == "BUY" else 0
        revenue = size * price if side == "SELL" else 0

        if side == "BUY":
            self.state["usdc_balance"] -= cost
        else:
            self.state["usdc_balance"] += revenue

        # Update position
        if token_id not in self.state["positions"]:
            self.state["positions"][token_id] = {
                "size": 0,
                "avgPrice": 0,
                "asset_id": token_id
            }

        pos = self.state["positions"][token_id]

        if side == "BUY":
            # Update average price on buys
            total_cost = pos["size"] * pos["avgPrice"] + size * price
            pos["size"] += size
            pos["avgPrice"] = total_cost / pos["size"] if pos["size"] > 0 else price
        else:  # SELL
            pos["size"] -= size
            # avgPrice stays the same on sells

        # Remove position if closed
        if abs(pos["size"]) < 0.01:
            del self.state["positions"][token_id]

        # Log trade
        self._log_trade({
            "order_id": order_id,
            "token_id": token_id,
            "side": side,
            "size": size,
            "price": price,
            "cost": cost,
            "revenue": revenue,
            "balance": self.state["usdc_balance"]
        })

        # Add to trade history
        self.state["trade_history"].append({
            "order_id": order_id,
            "token_id": token_id,
            "side": side,
            "size": size,
            "price": price,
            "timestamp": datetime.now().isoformat()
        })

        self._save_state()

        print(f"✅ PAPER TRADE: {side} {size:.2f} @ ${price:.4f} | Balance: ${self.state['usdc_balance']:,.2f}")

    # ==================== ORDER MANAGEMENT (SIMULATED) ====================

    def create_order(self, marketId, action, price, size, neg_risk=False):
        """
        Simulate creating an order.

        Args:
            marketId (str): Token ID
            action (str): "BUY" or "SELL"
            price (float): Order price (0-1 range)
            size (float): Order size in USDC
            neg_risk (bool): Negative risk market flag

        Returns:
            dict: Simulated order response
        """
        order_id = str(uuid.uuid4())

        # Validate balance for buy orders
        if action == "BUY":
            required = size * price
            if required > self.state["usdc_balance"]:
                print(f"❌ PAPER TRADE REJECTED: Insufficient balance (need ${required:.2f}, have ${self.state['usdc_balance']:.2f})")
                return {"error": "Insufficient balance"}

        # Validate position for sell orders
        if action == "SELL":
            pos_size = self.state["positions"].get(marketId, {}).get("size", 0)
            if pos_size < size:
                print(f"❌ PAPER TRADE REJECTED: Insufficient position (need {size:.2f}, have {pos_size:.2f})")
                return {"error": "Insufficient position"}

        order = {
            "order_id": order_id,
            "token_id": marketId,
            "side": action,
            "price": price,
            "size": size,
            "original_size": size,
            "size_matched": 0,
            "status": "OPEN",
            "created_at": datetime.now().isoformat(),
            "neg_risk": neg_risk
        }

        self.state["orders"][order_id] = order
        self._save_state()

        print(f"📝 PAPER ORDER: {action} {size:.2f} @ ${price:.4f} [{order_id[:8]}...]")

        return {
            "success": True,
            "orderID": order_id,
            "status": "OPEN"
        }

    def cancel_all_asset(self, asset_id):
        """Cancel all orders for a specific asset."""
        cancelled = []
        for order_id, order in list(self.state["orders"].items()):
            if order["token_id"] == str(asset_id) and order["status"] == "OPEN":
                order["status"] = "CANCELLED"
                cancelled.append(order_id)

        if cancelled:
            print(f"🚫 PAPER CANCEL: {len(cancelled)} orders for asset {asset_id}")

        self._save_state()

    def cancel_all_market(self, marketId):
        """Cancel all orders in a specific market."""
        self.cancel_all_asset(marketId)

    def merge_positions(self, amount_to_merge, condition_id, is_neg_risk_market):
        """
        Simulate merging positions to recover collateral.

        Args:
            amount_to_merge (int): Raw amount to merge
            condition_id (str): Market condition ID
            is_neg_risk_market (bool): Negative risk market flag

        Returns:
            str: Simulated transaction hash
        """
        usdc_recovered = amount_to_merge / 1e6
        self.state["usdc_balance"] += usdc_recovered
        self._save_state()

        print(f"🔄 PAPER MERGE: Recovered ${usdc_recovered:.2f} USDC | Balance: ${self.state['usdc_balance']:,.2f}")

        # Log merge as a trade
        self._log_trade({
            "order_id": "MERGE",
            "token_id": condition_id,
            "side": "MERGE",
            "size": usdc_recovered,
            "price": 1.0,
            "cost": 0,
            "revenue": usdc_recovered,
            "balance": self.state["usdc_balance"]
        })

        return f"0xPAPER{uuid.uuid4().hex[:40]}"

    # ==================== BALANCE QUERIES (SIMULATED) ====================

    def get_usdc_balance(self):
        """Get simulated USDC balance."""
        return self.state["usdc_balance"]

    def get_pos_balance(self):
        """Get total value of all simulated positions."""
        total_value = 0
        for token_id, pos in self.state["positions"].items():
            # Estimate position value at average price
            total_value += pos["size"] * pos["avgPrice"]
        return total_value

    def get_total_balance(self):
        """Get combined simulated balance."""
        return self.get_usdc_balance() + self.get_pos_balance()

    # ==================== POSITION QUERIES (SIMULATED) ====================

    def get_all_positions(self):
        """Get all simulated positions as DataFrame."""
        if not self.state["positions"]:
            return pd.DataFrame()

        positions = []
        for token_id, pos in self.state["positions"].items():
            positions.append({
                "asset_id": token_id,
                "size": pos["size"],
                "avgPrice": pos["avgPrice"]
            })

        return pd.DataFrame(positions)

    def get_raw_position(self, tokenId):
        """Get raw position size (in 1e6 units)."""
        pos = self.state["positions"].get(str(tokenId), {})
        return int(pos.get("size", 0) * 1e6)

    def get_position(self, tokenId):
        """Get position for a specific token."""
        raw = self.get_raw_position(tokenId)
        shares = raw / 1e6
        if shares < 1:
            shares = 0
        return raw, shares

    # ==================== ORDER QUERIES (SIMULATED) ====================

    def get_all_orders(self):
        """Get all open simulated orders as DataFrame."""
        open_orders = [
            order for order in self.state["orders"].values()
            if order["status"] == "OPEN"
        ]

        if not open_orders:
            return pd.DataFrame()

        df = pd.DataFrame(open_orders)

        # Ensure columns match real client output
        if not df.empty:
            df['original_size'] = df['original_size'].astype(float)
            df['size_matched'] = df['size_matched'].astype(float)
            df['price'] = df['price'].astype(float)

        return df

    def get_market_orders(self, market):
        """Get orders for a specific market."""
        market_orders = [
            order for order in self.state["orders"].values()
            if order["token_id"] == market and order["status"] == "OPEN"
        ]

        if not market_orders:
            return pd.DataFrame()

        df = pd.DataFrame(market_orders)

        if not df.empty:
            df['original_size'] = df['original_size'].astype(float)
            df['size_matched'] = df['size_matched'].astype(float)
            df['price'] = df['price'].astype(float)

        return df

    # ==================== MARKET DATA (REAL API) ====================

    def get_order_book(self, market):
        """Get real order book data (not simulated)."""
        return self.real_client.get_order_book(market)

    # ==================== REPORTING ====================

    def get_performance_report(self):
        """Generate a performance report for paper trading."""
        initial = self.state["initial_balance"]
        current = self.get_total_balance()
        pnl = current - initial
        pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

        total_trades = len(self.state["trade_history"])

        # Calculate win rate (simplified)
        wins = sum(1 for t in self.state["trade_history"] if t["side"] == "SELL")
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        report = {
            "initial_balance": initial,
            "current_balance": current,
            "pnl": pnl,
            "pnl_percent": pnl_pct,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "active_positions": len(self.state["positions"]),
            "open_orders": len([o for o in self.state["orders"].values() if o["status"] == "OPEN"]),
            "created_at": self.state["created_at"],
            "last_updated": self.state["last_updated"]
        }

        return report

    def print_performance_report(self):
        """Print a formatted performance report."""
        report = self.get_performance_report()

        print("\n" + "=" * 60)
        print("📊 PAPER TRADING PERFORMANCE REPORT")
        print("=" * 60)
        print(f"Initial Balance:     ${report['initial_balance']:>12,.2f}")
        print(f"Current Balance:     ${report['current_balance']:>12,.2f}")
        print(f"P&L:                 ${report['pnl']:>12,.2f} ({report['pnl_percent']:+.2f}%)")
        print("-" * 60)
        print(f"Total Trades:        {report['total_trades']:>12}")
        print(f"Win Rate:            {report['win_rate']:>12.1f}%")
        print(f"Active Positions:    {report['active_positions']:>12}")
        print(f"Open Orders:         {report['open_orders']:>12}")
        print("-" * 60)
        print(f"Session Start:       {report['created_at']}")
        print(f"Last Update:         {report['last_updated']}")
        print("=" * 60 + "\n")
