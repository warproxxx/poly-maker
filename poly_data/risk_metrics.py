"""
Risk-Adjusted Return Metrics for Polymarket Market Making

Implements:
- Sharpe Ratio: (expected_return - risk_free_rate) / volatility
- Sortino Ratio: (expected_return - risk_free_rate) / downside_volatility
- Expected Profit: expected_rewards - total_costs
- Fill Probability: likelihood of orders being filled
- Information Ratio: excess returns per unit of tracking error
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class RiskMetricsCalculator:
    """
    Calculate risk-adjusted return metrics for market making opportunities.
    """

    def __init__(
        self,
        risk_free_rate_annual: float = 0.05,  # 5% annual risk-free rate (e.g., T-bills)
        gas_cost_per_trade: float = 0.01,  # Estimated gas cost in USDC
        slippage_bps: float = 2.0  # Slippage in basis points
    ):
        """
        Initialize risk metrics calculator.

        Args:
            risk_free_rate_annual: Annual risk-free rate (as decimal, e.g., 0.05 = 5%)
            gas_cost_per_trade: Estimated gas cost per trade in USDC
            slippage_bps: Expected slippage in basis points
        """
        self.risk_free_rate_daily = (1 + risk_free_rate_annual) ** (1/365) - 1
        self.gas_cost_per_trade = gas_cost_per_trade
        self.slippage_bps = slippage_bps

    def calculate_sharpe_ratio(
        self,
        expected_daily_return: float,
        volatility_annualized: float,
        capital_deployed: float
    ) -> float:
        """
        Calculate Sharpe Ratio for a market making opportunity.

        Sharpe = (R - Rf) / σ

        Args:
            expected_daily_return: Expected daily return in USDC
            volatility_annualized: Annualized price volatility (from log returns)
            capital_deployed: Total capital deployed in USDC

        Returns:
            Sharpe ratio (annualized)
        """
        if volatility_annualized == 0 or capital_deployed == 0:
            return 0.0

        # Convert to return percentages
        daily_return_pct = expected_daily_return / capital_deployed
        annual_return = (1 + daily_return_pct) ** 365 - 1

        # Sharpe ratio (annualized)
        sharpe = (annual_return - self.risk_free_rate_daily * 365) / volatility_annualized

        return sharpe

    def calculate_sortino_ratio(
        self,
        expected_daily_return: float,
        downside_volatility_annualized: float,
        capital_deployed: float
    ) -> float:
        """
        Calculate Sortino Ratio (like Sharpe but only penalizes downside volatility).

        Sortino = (R - Rf) / σ_downside

        Args:
            expected_daily_return: Expected daily return in USDC
            downside_volatility_annualized: Annualized downside volatility
            capital_deployed: Total capital deployed in USDC

        Returns:
            Sortino ratio (annualized)
        """
        if downside_volatility_annualized == 0 or capital_deployed == 0:
            return 0.0

        daily_return_pct = expected_daily_return / capital_deployed
        annual_return = (1 + daily_return_pct) ** 365 - 1

        sortino = (annual_return - self.risk_free_rate_daily * 365) / downside_volatility_annualized

        return sortino

    def calculate_downside_volatility(
        self,
        price_history: pd.DataFrame,
        hours: int = 24
    ) -> float:
        """
        Calculate downside volatility (only negative returns).

        Args:
            price_history: DataFrame with columns ['t', 'p'] (timestamp, price)
            hours: Time window for calculation

        Returns:
            Annualized downside volatility
        """
        if len(price_history) == 0:
            return 0.0

        # Filter to time window
        end_time = price_history['t'].max()
        start_time = end_time - pd.Timedelta(hours=hours)
        window_df = price_history[price_history['t'] >= start_time].copy()

        if len(window_df) < 2:
            return 0.0

        # Calculate log returns
        window_df['log_return'] = np.log(window_df['p'] / window_df['p'].shift(1))

        # Only keep negative returns
        downside_returns = window_df[window_df['log_return'] < 0]['log_return']

        if len(downside_returns) == 0:
            return 0.0

        # Calculate downside deviation
        downside_vol = downside_returns.std()

        # Annualize (assuming 1-minute data points)
        annualized_downside_vol = downside_vol * np.sqrt(60 * 24 * 252)

        return annualized_downside_vol

    def calculate_expected_profit(
        self,
        expected_daily_reward: float,
        spread_cost: float,
        inventory_risk_cost: float,
        trade_frequency_per_day: float = 10.0
    ) -> Dict[str, float]:
        """
        Calculate expected profit after all costs.

        Expected Profit = Rewards - Spread Costs - Gas Costs - Inventory Risk

        Args:
            expected_daily_reward: Expected daily rewards in USDC
            spread_cost: Cost of spread (half-spread × volume)
            inventory_risk_cost: Cost of holding inventory (potential adverse selection)
            trade_frequency_per_day: Expected number of trades per day

        Returns:
            Dictionary with profit breakdown
        """
        # Calculate costs
        gas_cost = self.gas_cost_per_trade * trade_frequency_per_day
        total_costs = spread_cost + gas_cost + inventory_risk_cost

        # Calculate net profit
        expected_profit = expected_daily_reward - total_costs

        return {
            'expected_daily_reward': expected_daily_reward,
            'spread_cost': spread_cost,
            'gas_cost': gas_cost,
            'inventory_risk_cost': inventory_risk_cost,
            'total_costs': total_costs,
            'expected_daily_profit': expected_profit,
            'profit_margin_pct': (expected_profit / expected_daily_reward * 100) if expected_daily_reward > 0 else 0
        }

    def calculate_spread_cost(
        self,
        bid_price: float,
        ask_price: float,
        expected_volume_per_day: float
    ) -> float:
        """
        Calculate the cost of crossing the spread.

        Args:
            bid_price: Bid price
            ask_price: Ask price
            expected_volume_per_day: Expected daily volume in shares

        Returns:
            Daily spread cost in USDC
        """
        if bid_price == 0 or ask_price == 0:
            return 0.0

        spread = ask_price - bid_price
        half_spread = spread / 2

        # Assuming you capture half-spread on average
        spread_cost = half_spread * expected_volume_per_day

        return spread_cost

    def calculate_inventory_risk_cost(
        self,
        position_size: float,
        avg_price: float,
        volatility_1hour: float,
        holding_period_hours: float = 4.0
    ) -> float:
        """
        Calculate the cost of inventory risk (adverse selection).

        When you hold a position, you're exposed to price moves.
        This estimates the expected cost of that exposure.

        Args:
            position_size: Current position size in shares
            avg_price: Average entry price
            volatility_1hour: 1-hour annualized volatility
            holding_period_hours: Expected holding period in hours

        Returns:
            Expected inventory risk cost in USDC
        """
        if position_size == 0 or volatility_1hour == 0:
            return 0.0

        # Convert annualized vol to hourly vol
        hourly_vol = volatility_1hour / np.sqrt(252 * 24)

        # Expected volatility over holding period
        holding_vol = hourly_vol * np.sqrt(holding_period_hours)

        # Position value
        position_value = position_size * avg_price

        # Expected cost = position_value × volatility × risk_aversion_factor
        # Using 0.5 as risk aversion factor (conservative)
        inventory_cost = position_value * holding_vol * 0.5

        return inventory_cost

    def calculate_fill_probability(
        self,
        your_price: float,
        best_price: float,
        tick_size: float,
        orderbook_depth: float,
        is_bid: bool = True
    ) -> float:
        """
        Estimate the probability that your order will be filled.

        Args:
            your_price: Your order price
            best_price: Current best bid/ask
            tick_size: Minimum price increment
            orderbook_depth: Total size at best price
            is_bid: True if this is a bid order, False if ask

        Returns:
            Fill probability between 0 and 1
        """
        if tick_size == 0:
            return 0.0

        # Calculate how many ticks away you are from best price
        price_diff = abs(your_price - best_price)
        ticks_away = round(price_diff / tick_size)

        # If you're at or better than best price, high fill probability
        if is_bid and your_price >= best_price:
            return 0.95  # Very high but not 100% (can still be front-run)
        elif not is_bid and your_price <= best_price:
            return 0.95

        # If you're behind, probability decreases exponentially
        # Formula: P(fill) = 0.9 × exp(-0.5 × ticks_away) × (1 / log(depth + 2))
        base_prob = 0.9 * np.exp(-0.5 * ticks_away)

        # Adjust for orderbook depth (less depth = higher probability)
        depth_factor = 1 / np.log(orderbook_depth + 2)

        fill_probability = base_prob * depth_factor

        return min(max(fill_probability, 0.01), 0.95)  # Clamp between 1% and 95%

    def calculate_information_ratio(
        self,
        expected_daily_return: float,
        benchmark_return: float,
        tracking_error: float,
        capital_deployed: float
    ) -> float:
        """
        Calculate Information Ratio (active return per unit of active risk).

        IR = (Portfolio Return - Benchmark Return) / Tracking Error

        Args:
            expected_daily_return: Expected daily return in USDC
            benchmark_return: Benchmark return (e.g., average market return)
            tracking_error: Volatility of excess returns
            capital_deployed: Capital deployed in USDC

        Returns:
            Information ratio
        """
        if tracking_error == 0 or capital_deployed == 0:
            return 0.0

        daily_return_pct = expected_daily_return / capital_deployed
        benchmark_return_pct = benchmark_return / capital_deployed

        excess_return = daily_return_pct - benchmark_return_pct

        # Annualize
        annual_excess_return = excess_return * 365
        annual_tracking_error = tracking_error

        ir = annual_excess_return / annual_tracking_error

        return ir

    def calculate_comprehensive_metrics(
        self,
        expected_daily_reward: float,
        capital_deployed: float,
        bid_price: float,
        ask_price: float,
        position_size: float,
        avg_price: float,
        volatility_1hour: float,
        volatility_24hour: float,
        downside_volatility_24hour: float,
        orderbook_depth: float,
        expected_volume_per_day: float = 100.0,
        trade_frequency_per_day: float = 10.0
    ) -> Dict[str, float]:
        """
        Calculate all risk-adjusted metrics at once.

        Args:
            expected_daily_reward: Expected daily reward in USDC
            capital_deployed: Total capital deployed
            bid_price: Bid price
            ask_price: Ask price
            position_size: Current position size
            avg_price: Average entry price
            volatility_1hour: 1-hour annualized volatility
            volatility_24hour: 24-hour annualized volatility
            downside_volatility_24hour: 24-hour downside volatility
            orderbook_depth: Order book depth
            expected_volume_per_day: Expected daily volume
            trade_frequency_per_day: Expected trades per day

        Returns:
            Dictionary with all metrics
        """
        # Calculate costs
        spread_cost = self.calculate_spread_cost(bid_price, ask_price, expected_volume_per_day)
        inventory_cost = self.calculate_inventory_risk_cost(position_size, avg_price, volatility_1hour)

        # Expected profit
        profit_metrics = self.calculate_expected_profit(
            expected_daily_reward,
            spread_cost,
            inventory_cost,
            trade_frequency_per_day
        )

        # Risk-adjusted returns
        sharpe = self.calculate_sharpe_ratio(
            profit_metrics['expected_daily_profit'],
            volatility_24hour,
            capital_deployed
        )

        sortino = self.calculate_sortino_ratio(
            profit_metrics['expected_daily_profit'],
            downside_volatility_24hour,
            capital_deployed
        )

        # Fill probabilities (simplified)
        midpoint = (bid_price + ask_price) / 2
        tick_size = 0.01  # Assume 1 cent ticks
        bid_fill_prob = self.calculate_fill_probability(bid_price, midpoint, tick_size, orderbook_depth, is_bid=True)
        ask_fill_prob = self.calculate_fill_probability(ask_price, midpoint, tick_size, orderbook_depth, is_bid=False)

        # Adjusted expected profit (accounting for fill probability)
        adjusted_daily_profit = profit_metrics['expected_daily_profit'] * (bid_fill_prob + ask_fill_prob) / 2

        return {
            **profit_metrics,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'bid_fill_probability': bid_fill_prob,
            'ask_fill_probability': ask_fill_prob,
            'adjusted_daily_profit': adjusted_daily_profit,
            'expected_annual_profit': adjusted_daily_profit * 365,
            'expected_roi_annual': (adjusted_daily_profit * 365 / capital_deployed * 100) if capital_deployed > 0 else 0
        }


def calculate_metrics_for_market(
    expected_daily_reward: float,
    capital_to_deploy: float,
    best_bid: float,
    best_ask: float,
    volatility_1hour: float,
    volatility_24hour: float,
    downside_volatility_24hour: float,
    min_size: float,
    orderbook_bid_depth: float,
    orderbook_ask_depth: float
) -> Dict[str, float]:
    """
    Convenience function to calculate all metrics for a market during discovery.

    Args:
        expected_daily_reward: Expected daily reward
        capital_to_deploy: How much capital you plan to deploy
        best_bid: Best bid price
        best_ask: Best ask price
        volatility_1hour: 1-hour volatility
        volatility_24hour: 24-hour volatility
        downside_volatility_24hour: 24-hour downside volatility
        min_size: Minimum order size
        orderbook_bid_depth: Bid side depth
        orderbook_ask_depth: Ask side depth

    Returns:
        Dictionary with all metrics
    """
    calc = RiskMetricsCalculator()

    # Assume we deploy capital equally on both sides
    bid_capital = capital_to_deploy / 2
    ask_capital = capital_to_deploy / 2

    # Estimate position sizes
    position_size = bid_capital / best_bid if best_bid > 0 else min_size
    avg_price = (best_bid + best_ask) / 2

    metrics = calc.calculate_comprehensive_metrics(
        expected_daily_reward=expected_daily_reward,
        capital_deployed=capital_to_deploy,
        bid_price=best_bid,
        ask_price=best_ask,
        position_size=position_size,
        avg_price=avg_price,
        volatility_1hour=volatility_1hour,
        volatility_24hour=volatility_24hour,
        downside_volatility_24hour=downside_volatility_24hour,
        orderbook_depth=(orderbook_bid_depth + orderbook_ask_depth) / 2,
        expected_volume_per_day=position_size * 2,  # Assume 2x turnover
        trade_frequency_per_day=10
    )

    return metrics
