#!/bin/bash

# Paper Trading Setup Script
# This script helps you set up paper trading mode for the Polymarket bot

echo "=================================================="
echo "   Paper Trading Mode - Setup Script"
echo "=================================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your credentials:"
    echo "   - PK=your_private_key"
    echo "   - BROWSER_ADDRESS=your_wallet_address"
    echo "   - SPREADSHEET_URL=your_google_sheet_url"
    echo ""
    echo "   Paper trading still needs these for market data access."
    echo ""
else
    echo "✅ Found existing .env file"
fi

# Check if PAPER_TRADING is enabled
if grep -q "^PAPER_TRADING=true" .env 2>/dev/null; then
    echo "✅ Paper trading is already enabled in .env"
elif grep -q "^PAPER_TRADING=" .env 2>/dev/null; then
    echo "⚠️  PAPER_TRADING is set to false. Setting to true..."
    sed -i 's/^PAPER_TRADING=.*/PAPER_TRADING=true/' .env
    echo "✅ Enabled paper trading mode"
else
    echo "⚠️  Adding PAPER_TRADING configuration to .env..."
    # Add at the top of the file
    echo -e "# Paper Trading Mode\nPAPER_TRADING=true\nPAPER_TRADING_INITIAL_BALANCE=10000\n\n$(cat .env)" > .env
    echo "✅ Added paper trading configuration"
fi

echo ""
echo "=================================================="
echo "   Configuration Summary"
echo "=================================================="
echo ""

# Show current paper trading config
if [ -f .env ]; then
    echo "Paper Trading Mode:"
    grep "^PAPER_TRADING" .env | sed 's/^/  /'
    echo ""
fi

echo "Paper Trading Directory:"
if [ -d "paper_trading" ]; then
    echo "  ✅ paper_trading/ directory exists"
    if [ -f "paper_trading/state.json" ]; then
        echo "  ✅ Existing session found (will resume)"
    else
        echo "  📝 No existing session (will create new)"
    fi
else
    echo "  📝 Will be created on first run"
fi

echo ""
echo "=================================================="
echo "   Next Steps"
echo "=================================================="
echo ""
echo "1. Verify your .env file has valid credentials:"
echo "   nano .env"
echo ""
echo "2. Start the bot in paper trading mode:"
echo "   python main.py"
echo ""
echo "3. In another terminal, monitor performance:"
echo "   python view_paper_report.py"
echo ""
echo "4. Or watch continuously:"
echo "   watch -n 30 python view_paper_report.py"
echo ""
echo "=================================================="
echo "   Tips"
echo "=================================================="
echo ""
echo "• Paper trading uses REAL market data"
echo "• All orders are SIMULATED (no real money at risk)"
echo "• State is saved to paper_trading/ directory"
echo "• You can stop/restart without losing progress"
echo "• Perfect for testing strategies and demos!"
echo ""
echo "📖 Read PAPER_TRADING.md for full documentation"
echo ""
echo "=================================================="
