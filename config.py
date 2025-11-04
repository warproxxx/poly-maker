"""
Centralized Configuration for Polymarket Liquidity Bot

All configuration values in one place. Override via environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional


# ============================================================================
# ENVIRONMENT VARIABLES (Secrets & Deployment-Specific)
# ============================================================================

# Polymarket Authentication
PRIVATE_KEY = os.getenv('PK', '')
BROWSER_ADDRESS = os.getenv('BROWSER_ADDRESS', '')

# Google Sheets
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL', '')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')

# Feature Flags
USE_DYNAMIC_SPREADS = os.getenv('USE_DYNAMIC_SPREADS', 'true').lower() == 'true'
USE_KELLY_SIZING = os.getenv('USE_KELLY_SIZING', 'false').lower() == 'true'
DRY_RUN_MODE = os.getenv('DRY_RUN_MODE', 'false').lower() == 'true'


# ============================================================================
# UPDATE INTERVALS (seconds)
# ============================================================================

UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '5'))
MARKET_UPDATE_CYCLES = int(os.getenv('MARKET_UPDATE_CYCLES', '6'))  # 6 cycles = 30s
STALE_TRADE_TIMEOUT = int(os.getenv('STALE_TRADE_TIMEOUT', '15'))
WEBSOCKET_RECONNECT_DELAY = int(os.getenv('WEBSOCKET_RECONNECT_DELAY', '1'))
MARKET_DISCOVERY_INTERVAL = int(os.getenv('MARKET_DISCOVERY_INTERVAL', '3600'))
STATS_UPDATE_INTERVAL = int(os.getenv('STATS_UPDATE_INTERVAL', '10800'))
API_RETRY_DELAY = int(os.getenv('API_RETRY_DELAY', '1'))


# ============================================================================
# TRADING PARAMETERS
# ============================================================================

# Order Management
PRICE_CHANGE_THRESHOLD = float(os.getenv('PRICE_CHANGE_THRESHOLD', '0.005'))  # 0.5 cents
SIZE_CHANGE_THRESHOLD = float(os.getenv('SIZE_CHANGE_THRESHOLD', '0.10'))  # 10%
MIN_TRADEABLE_PRICE = float(os.getenv('MIN_TRADEABLE_PRICE', '0.10'))
MAX_TRADEABLE_PRICE = float(os.getenv('MAX_TRADEABLE_PRICE', '0.90'))

# Position Management
MIN_MERGE_SIZE = float(os.getenv('MIN_MERGE_SIZE', '20'))
ABSOLUTE_MAX_POSITION = int(os.getenv('ABSOLUTE_MAX_POSITION', '250'))


# ============================================================================
# DYNAMIC SPREAD PARAMETERS
# ============================================================================

@dataclass
class DynamicSpreadConfig:
    """Configuration for dynamic spread adjustment."""
    base_spread_bps: float = float(os.getenv('BASE_SPREAD_BPS', '20'))
    min_spread_ticks: int = int(os.getenv('MIN_SPREAD_TICKS', '2'))
    max_spread_pct: float = float(os.getenv('MAX_SPREAD_PCT', '0.10'))

    # Volatility multipliers
    vol_low_threshold: float = 0.5
    vol_medium_threshold: float = 1.0
    vol_high_threshold: float = 2.0
    vol_max_multiplier: float = 5.0

    # Inventory management
    inventory_penalty_factor: float = float(os.getenv('INVENTORY_PENALTY_FACTOR', '0.01'))
    inventory_skew_threshold: float = 0.5  # Start skewing at 50% of max
    inventory_max_skew: float = 0.5  # Max 50% spread adjustment


DYNAMIC_SPREAD = DynamicSpreadConfig()


# ============================================================================
# RISK METRICS PARAMETERS
# ============================================================================

@dataclass
class RiskMetricsConfig:
    """Configuration for risk-adjusted metrics calculation."""
    risk_free_rate_annual: float = float(os.getenv('RISK_FREE_RATE_ANNUAL', '0.05'))
    gas_cost_per_trade: float = float(os.getenv('GAS_COST_PER_TRADE', '0.01'))
    slippage_bps: float = float(os.getenv('SLIPPAGE_BPS', '2.0'))

    # Fill probability parameters
    fill_prob_base: float = 0.9
    fill_prob_decay: float = 0.5


RISK_METRICS = RiskMetricsConfig()


# ============================================================================
# PORTFOLIO OPTIMIZATION PARAMETERS
# ============================================================================

@dataclass
class PortfolioConfig:
    """Configuration for portfolio optimization."""
    kelly_fraction: float = float(os.getenv('KELLY_FRACTION', '0.25'))  # Quarter-Kelly
    max_positions: int = int(os.getenv('MAX_POSITIONS', '20'))
    max_category_exposure: float = float(os.getenv('MAX_CATEGORY_EXPOSURE', '0.40'))
    max_single_position: float = float(os.getenv('MAX_SINGLE_POSITION', '0.25'))  # 25% of capital
    rebalance_threshold: float = float(os.getenv('REBALANCE_THRESHOLD', '0.20'))  # Rebalance at 20% drift


PORTFOLIO = PortfolioConfig()


# ============================================================================
# MARKET DISCOVERY PARAMETERS
# ============================================================================

@dataclass
class MarketDiscoveryConfig:
    """Configuration for market discovery and ranking."""
    maker_reward_threshold: float = float(os.getenv('MAKER_REWARD_THRESHOLD', '0.75'))
    volatility_filter_threshold: float = float(os.getenv('VOLATILITY_FILTER_THRESHOLD', '20'))
    min_sharpe_ratio: float = float(os.getenv('MIN_SHARPE_RATIO', '0.5'))

    # Ranking weights
    weight_rewards: float = 0.25
    weight_sharpe: float = 0.30
    weight_profit: float = 0.25
    weight_volatility: float = 0.15
    weight_proximity: float = 0.05
    weight_regime: float = 0.20

    # Max workers for parallel processing
    max_workers: int = int(os.getenv('MAX_WORKERS', '5'))
    max_workers_volatility: int = int(os.getenv('MAX_WORKERS_VOLATILITY', '3'))


MARKET_DISCOVERY = MarketDiscoveryConfig()


# ============================================================================
# REGIME DETECTION PARAMETERS
# ============================================================================

@dataclass
class RegimeDetectionConfig:
    """Configuration for market regime detection."""
    hurst_max_lag: int = 20
    hurst_min_samples: int = 50

    # Regime thresholds
    hurst_mean_reverting_threshold: float = 0.45
    hurst_trending_threshold: float = 0.55
    autocorr_threshold: float = 0.15

    # Volatility classification
    vol_low: float = 0.5
    vol_medium: float = 2.0
    vol_high: float = 5.0


REGIME_DETECTION = RegimeDetectionConfig()


# ============================================================================
# LOGGING & MONITORING
# ============================================================================

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'logs/trading.log')

ENABLE_PERFORMANCE_METRICS = os.getenv('ENABLE_PERFORMANCE_METRICS', 'true').lower() == 'true'
ENABLE_SPREAD_COMPARISON_LOGGING = os.getenv('ENABLE_SPREAD_COMPARISON_LOGGING', 'true').lower() == 'true'


# ============================================================================
# VALIDATION
# ============================================================================

def validate_config():
    """Validate critical configuration values."""
    errors = []
    warnings = []

    # Required fields (only warn, don't fail - might be set later)
    if not PRIVATE_KEY:
        warnings.append("PRIVATE_KEY (PK) not set in environment - required for trading")

    if not BROWSER_ADDRESS:
        warnings.append("BROWSER_ADDRESS not set in environment - required for trading")

    # Value range validation
    if not (0 <= PORTFOLIO.kelly_fraction <= 1):
        errors.append(f"KELLY_FRACTION must be between 0 and 1, got {PORTFOLIO.kelly_fraction}")

    if not (0 <= PORTFOLIO.max_category_exposure <= 1):
        errors.append(f"MAX_CATEGORY_EXPOSURE must be between 0 and 1, got {PORTFOLIO.max_category_exposure}")

    if not (0 < DYNAMIC_SPREAD.base_spread_bps < 1000):
        errors.append(f"BASE_SPREAD_BPS must be between 0 and 1000, got {DYNAMIC_SPREAD.base_spread_bps}")

    if UPDATE_INTERVAL <= 0:
        errors.append(f"UPDATE_INTERVAL must be positive, got {UPDATE_INTERVAL}")

    if PRICE_CHANGE_THRESHOLD < 0:
        errors.append(f"PRICE_CHANGE_THRESHOLD must be non-negative, got {PRICE_CHANGE_THRESHOLD}")

    # Print warnings
    if warnings:
        print("\n⚠ Configuration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    # Raise errors
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    if not warnings and not errors:
        print("✓ Configuration validated successfully")


# Validate on import (only if not in test mode)
if os.getenv('SKIP_CONFIG_VALIDATION', '').lower() != 'true':
    try:
        validate_config()
    except ValueError as e:
        print(f"\n❌ {e}\n")
        raise


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_config():
    """Print current configuration (without secrets)."""
    print("\n" + "="*70)
    print(" " * 15 + "POLYMARKET LIQUIDITY BOT CONFIGURATION")
    print("="*70)

    print("\n[Feature Flags]")
    print(f"  USE_DYNAMIC_SPREADS:           {USE_DYNAMIC_SPREADS}")
    print(f"  USE_KELLY_SIZING:              {USE_KELLY_SIZING}")
    print(f"  DRY_RUN_MODE:                  {DRY_RUN_MODE}")

    print("\n[Update Intervals]")
    print(f"  UPDATE_INTERVAL:               {UPDATE_INTERVAL}s")
    print(f"  MARKET_UPDATE_INTERVAL:        {UPDATE_INTERVAL * MARKET_UPDATE_CYCLES}s")
    print(f"  MARKET_DISCOVERY_INTERVAL:     {MARKET_DISCOVERY_INTERVAL}s ({MARKET_DISCOVERY_INTERVAL/3600:.1f}h)")
    print(f"  STATS_UPDATE_INTERVAL:         {STATS_UPDATE_INTERVAL}s ({STATS_UPDATE_INTERVAL/3600:.1f}h)")
    print(f"  STALE_TRADE_TIMEOUT:           {STALE_TRADE_TIMEOUT}s")

    print("\n[Trading Parameters]")
    print(f"  PRICE_CHANGE_THRESHOLD:        ${PRICE_CHANGE_THRESHOLD:.4f}")
    print(f"  SIZE_CHANGE_THRESHOLD:         {SIZE_CHANGE_THRESHOLD*100:.0f}%")
    print(f"  MIN_TRADEABLE_PRICE:           ${MIN_TRADEABLE_PRICE:.2f}")
    print(f"  MAX_TRADEABLE_PRICE:           ${MAX_TRADEABLE_PRICE:.2f}")
    print(f"  MIN_MERGE_SIZE:                {MIN_MERGE_SIZE}")
    print(f"  ABSOLUTE_MAX_POSITION:         {ABSOLUTE_MAX_POSITION}")

    print("\n[Dynamic Spreads]")
    print(f"  Base Spread:                   {DYNAMIC_SPREAD.base_spread_bps} bps ({DYNAMIC_SPREAD.base_spread_bps/100:.2f}%)")
    print(f"  Min Spread:                    {DYNAMIC_SPREAD.min_spread_ticks} ticks")
    print(f"  Max Spread:                    {DYNAMIC_SPREAD.max_spread_pct * 100:.1f}%")
    print(f"  Inventory Penalty Factor:      {DYNAMIC_SPREAD.inventory_penalty_factor}")

    print("\n[Risk Metrics]")
    print(f"  Risk-Free Rate (Annual):       {RISK_METRICS.risk_free_rate_annual * 100:.1f}%")
    print(f"  Gas Cost Per Trade:            ${RISK_METRICS.gas_cost_per_trade:.2f}")
    print(f"  Slippage:                      {RISK_METRICS.slippage_bps} bps")

    print("\n[Portfolio Optimization]")
    print(f"  Kelly Fraction:                {PORTFOLIO.kelly_fraction} (quarter-Kelly)")
    print(f"  Max Positions:                 {PORTFOLIO.max_positions}")
    print(f"  Max Category Exposure:         {PORTFOLIO.max_category_exposure * 100:.0f}%")
    print(f"  Max Single Position:           {PORTFOLIO.max_single_position * 100:.0f}%")

    print("\n[Market Discovery]")
    print(f"  Min Maker Reward:              ${MARKET_DISCOVERY.maker_reward_threshold:.2f}")
    print(f"  Max Volatility Sum:            {MARKET_DISCOVERY.volatility_filter_threshold}")
    print(f"  Min Sharpe Ratio:              {MARKET_DISCOVERY.min_sharpe_ratio}")
    print(f"  Ranking Weights:")
    print(f"    - Rewards:                   {MARKET_DISCOVERY.weight_rewards*100:.0f}%")
    print(f"    - Sharpe:                    {MARKET_DISCOVERY.weight_sharpe*100:.0f}%")
    print(f"    - Profit:                    {MARKET_DISCOVERY.weight_profit*100:.0f}%")
    print(f"    - Volatility (penalty):      {MARKET_DISCOVERY.weight_volatility*100:.0f}%")
    print(f"    - Regime:                    {MARKET_DISCOVERY.weight_regime*100:.0f}%")

    print("\n[Logging]")
    print(f"  LOG_LEVEL:                     {LOG_LEVEL}")
    print(f"  LOG_TO_FILE:                   {LOG_TO_FILE}")
    print(f"  PERFORMANCE_METRICS:           {ENABLE_PERFORMANCE_METRICS}")
    print(f"  SPREAD_COMPARISON_LOGGING:     {ENABLE_SPREAD_COMPARISON_LOGGING}")

    print("="*70 + "\n")


if __name__ == "__main__":
    print_config()
