#!/usr/bin/env python3
"""
Test script for paper trading mode
"""

import os
import sys

# Set paper trading mode for testing
os.environ["PAPER_TRADING"] = "true"
os.environ["PAPER_TRADING_INITIAL_BALANCE"] = "5000"

print("Testing paper trading client import and initialization...\n")

try:
    from poly_data.paper_trading_client import PaperTradingClient
    print("✅ Successfully imported PaperTradingClient\n")
except Exception as e:
    print(f"❌ Failed to import PaperTradingClient: {e}")
    sys.exit(1)

try:
    print("Initializing paper trading client...")
    # Note: This will fail if PK and BROWSER_ADDRESS are not set
    # but we can catch that and provide helpful feedback
    client = PaperTradingClient()
    print("✅ Successfully initialized PaperTradingClient\n")

    # Test basic methods
    print("Testing methods...")

    balance = client.get_usdc_balance()
    print(f"✅ get_usdc_balance(): ${balance:,.2f}")

    total_balance = client.get_total_balance()
    print(f"✅ get_total_balance(): ${total_balance:,.2f}")

    positions = client.get_all_positions()
    print(f"✅ get_all_positions(): {len(positions)} positions")

    orders = client.get_all_orders()
    print(f"✅ get_all_orders(): {len(orders)} orders")

    # Test creating an order
    print("\nTesting order creation...")
    test_token = "test_token_123"
    result = client.create_order(
        marketId=test_token,
        action="BUY",
        price=0.50,
        size=10.0,
        neg_risk=False
    )

    if "success" in result or "orderID" in result:
        print(f"✅ create_order() succeeded: {result.get('orderID', 'N/A')[:8]}...")
    else:
        print(f"⚠️  create_order() returned: {result}")

    # Test getting orders after creation
    orders = client.get_all_orders()
    print(f"✅ get_all_orders() after order: {len(orders)} orders")

    # Test cancelling
    print("\nTesting order cancellation...")
    client.cancel_all_asset(test_token)
    print("✅ cancel_all_asset() succeeded")

    # Test performance report
    print("\nTesting performance report...")
    report = client.get_performance_report()
    print(f"✅ get_performance_report(): P&L = ${report['pnl']:.2f}")

    print("\nPrinting full report:")
    client.print_performance_report()

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nPaper trading mode is ready to use!")
    print("Set PAPER_TRADING=true in your .env file and run: python main.py")
    print("=" * 60 + "\n")

except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
