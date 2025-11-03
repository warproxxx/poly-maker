"""
Portfolio Optimization for Polymarket Market Making

Implements:
1. Kelly Criterion: Optimal position sizing based on edge and odds
2. Correlation Analysis: Avoid overexposure to correlated markets
3. Portfolio Risk Management: VaR, CVaR, concentration limits
4. Capital Allocation: Optimize across multiple markets
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class MarketOpportunity:
    """Represents a market making opportunity."""
    market_id: str
    question: str
    expected_daily_return: float  # in USDC
    volatility: float  # annualized
    capital_required: float  # in USDC
    sharpe_ratio: float
    correlation_key: str  # e.g., "US_POLITICS", "CRYPTO", "SPORTS"

    @property
    def expected_annual_return(self) -> float:
        return self.expected_daily_return * 365

    @property
    def return_pct(self) -> float:
        if self.capital_required == 0:
            return 0
        return (self.expected_daily_return / self.capital_required) * 100


class KellyCalculator:
    """
    Calculate optimal position sizes using Kelly Criterion.

    Kelly Criterion: f = (p*b - q) / b
    where:
        f = fraction of capital to bet
        p = probability of winning
        b = odds (how much you win per dollar bet)
        q = probability of losing (1-p)

    For market making, we adapt this to:
        f = edge / variance
    """

    def __init__(self, kelly_fraction: float = 0.25):
        """
        Initialize Kelly calculator.

        Args:
            kelly_fraction: Fraction of Kelly to use (0.25 = quarter-Kelly, safer)
        """
        self.kelly_fraction = kelly_fraction

    def calculate_kelly_size(
        self,
        expected_return: float,
        variance: float,
        max_size: float = 1.0
    ) -> float:
        """
        Calculate optimal Kelly position size.

        Args:
            expected_return: Expected return (as decimal, e.g., 0.05 = 5%)
            variance: Variance of returns
            max_size: Maximum allowed fraction (0-1)

        Returns:
            Optimal position size as fraction of capital (0-1)
        """
        if variance <= 0:
            return 0.0

        # Kelly formula for trading: f = edge / variance
        kelly_size = expected_return / variance

        # Apply fractional Kelly (more conservative)
        kelly_size = kelly_size * self.kelly_fraction

        # Clamp to reasonable bounds
        kelly_size = max(0.0, min(kelly_size, max_size))

        return kelly_size

    def calculate_kelly_sizes_portfolio(
        self,
        opportunities: List[MarketOpportunity],
        total_capital: float,
        correlation_matrix: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        Calculate Kelly sizes for a portfolio of opportunities.

        When markets are correlated, we need to adjust Kelly sizes.

        Args:
            opportunities: List of market opportunities
            total_capital: Total capital available
            correlation_matrix: Optional correlation matrix between markets

        Returns:
            Dictionary mapping market_id to capital allocation
        """
        if len(opportunities) == 0:
            return {}

        allocations = {}

        # If no correlation matrix, assume independence
        if correlation_matrix is None:
            for opp in opportunities:
                # Calculate variance from volatility
                # variance = (volatility * capital)^2
                variance = (opp.volatility * opp.capital_required) ** 2

                # Expected return in dollars
                expected_return = opp.expected_daily_return

                # Kelly size as fraction of TOTAL capital
                kelly_size = self.calculate_kelly_size(
                    expected_return / total_capital,
                    variance / (total_capital ** 2),
                    max_size=0.25  # Max 25% in any one market
                )

                allocations[opp.market_id] = kelly_size * total_capital
        else:
            # With correlations, use portfolio optimization
            # This is more complex - for now, use a simplified approach
            # that penalizes correlated markets

            for i, opp in enumerate(opportunities):
                variance = (opp.volatility * opp.capital_required) ** 2
                expected_return = opp.expected_daily_return

                # Base Kelly size
                kelly_size = self.calculate_kelly_size(
                    expected_return / total_capital,
                    variance / (total_capital ** 2),
                    max_size=0.25
                )

                # Adjust for correlations (reduce size if highly correlated with existing positions)
                # This is a simplified approach - proper implementation would use
                # multi-variate Kelly criterion
                if i > 0:
                    avg_correlation = np.mean(np.abs(correlation_matrix[i, :i]))
                    kelly_size *= (1 - avg_correlation * 0.5)  # Reduce by up to 50%

                allocations[opp.market_id] = kelly_size * total_capital

        # Normalize if total allocation > capital
        total_allocated = sum(allocations.values())
        if total_allocated > total_capital:
            scale_factor = total_capital / total_allocated
            allocations = {k: v * scale_factor for k, v in allocations.items()}

        return allocations


class CorrelationAnalyzer:
    """
    Analyze correlations between markets to avoid overexposure.
    """

    def __init__(self):
        """Initialize correlation analyzer."""
        self.correlation_cache = {}

    def calculate_correlation(
        self,
        price_history_1: pd.DataFrame,
        price_history_2: pd.DataFrame,
        hours: int = 24
    ) -> float:
        """
        Calculate correlation between two price series.

        Args:
            price_history_1: DataFrame with columns ['t', 'p']
            price_history_2: DataFrame with columns ['t', 'p']
            hours: Time window for correlation

        Returns:
            Correlation coefficient (-1 to 1)
        """
        if len(price_history_1) < 10 or len(price_history_2) < 10:
            return 0.0

        # Filter to time window
        end_time = min(price_history_1['t'].max(), price_history_2['t'].max())
        start_time = end_time - pd.Timedelta(hours=hours)

        df1 = price_history_1[price_history_1['t'] >= start_time].copy()
        df2 = price_history_2[price_history_2['t'] >= start_time].copy()

        # Merge on timestamp (find common timestamps)
        merged = pd.merge(df1, df2, on='t', suffixes=('_1', '_2'))

        if len(merged) < 10:
            return 0.0

        # Calculate returns
        merged['ret_1'] = np.log(merged['p_1'] / merged['p_1'].shift(1))
        merged['ret_2'] = np.log(merged['p_2'] / merged['p_2'].shift(1))

        merged = merged.dropna()

        if len(merged) < 10:
            return 0.0

        # Calculate correlation
        correlation = merged['ret_1'].corr(merged['ret_2'])

        return correlation if np.isfinite(correlation) else 0.0

    def build_correlation_matrix(
        self,
        markets: List[Dict],
        price_histories: Dict[str, pd.DataFrame]
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Build correlation matrix for a list of markets.

        Args:
            markets: List of market dictionaries with 'token1' key
            price_histories: Dictionary mapping token_id to price history DataFrame

        Returns:
            (correlation_matrix, market_ids)
        """
        n = len(markets)
        corr_matrix = np.eye(n)  # Start with identity matrix

        market_ids = [m.get('token1', m.get('market_id', str(i))) for i, m in enumerate(markets)]

        for i in range(n):
            for j in range(i + 1, n):
                token1_i = markets[i].get('token1')
                token1_j = markets[j].get('token1')

                if token1_i in price_histories and token1_j in price_histories:
                    corr = self.calculate_correlation(
                        price_histories[token1_i],
                        price_histories[token1_j],
                        hours=24
                    )
                    corr_matrix[i, j] = corr
                    corr_matrix[j, i] = corr

        return corr_matrix, market_ids

    def group_markets_by_category(self, markets: List[Dict]) -> Dict[str, List[str]]:
        """
        Group markets by category to detect potential correlations.

        Categories based on question content:
        - US Politics
        - Crypto
        - Sports
        - Economics
        - etc.

        Args:
            markets: List of market dictionaries with 'question' key

        Returns:
            Dictionary mapping category to list of market_ids
        """
        categories = {
            'US_POLITICS': [],
            'CRYPTO': [],
            'SPORTS': [],
            'ECONOMICS': [],
            'TECH': [],
            'INTERNATIONAL': [],
            'OTHER': []
        }

        politics_keywords = ['trump', 'biden', 'election', 'congress', 'senate', 'president', 'democrat', 'republican']
        crypto_keywords = ['bitcoin', 'btc', 'eth', 'ethereum', 'crypto', 'blockchain']
        sports_keywords = ['nfl', 'nba', 'mlb', 'nhl', 'soccer', 'football', 'basketball']
        econ_keywords = ['gdp', 'inflation', 'fed', 'economy', 'recession', 'unemployment']
        tech_keywords = ['apple', 'google', 'meta', 'amazon', 'tesla', 'ai', 'tech']

        for market in markets:
            question_lower = market.get('question', '').lower()
            market_id = market.get('token1', market.get('market_id', ''))

            categorized = False
            for keyword in politics_keywords:
                if keyword in question_lower:
                    categories['US_POLITICS'].append(market_id)
                    categorized = True
                    break

            if not categorized:
                for keyword in crypto_keywords:
                    if keyword in question_lower:
                        categories['CRYPTO'].append(market_id)
                        categorized = True
                        break

            if not categorized:
                for keyword in sports_keywords:
                    if keyword in question_lower:
                        categories['SPORTS'].append(market_id)
                        categorized = True
                        break

            if not categorized:
                for keyword in econ_keywords:
                    if keyword in question_lower:
                        categories['ECONOMICS'].append(market_id)
                        categorized = True
                        break

            if not categorized:
                for keyword in tech_keywords:
                    if keyword in question_lower:
                        categories['TECH'].append(market_id)
                        categorized = True
                        break

            if not categorized:
                categories['OTHER'].append(market_id)

        return categories

    def detect_overexposure(
        self,
        current_positions: Dict[str, float],
        markets: List[Dict],
        max_category_exposure: float = 0.40
    ) -> Dict[str, any]:
        """
        Detect if portfolio is overexposed to any category.

        Args:
            current_positions: Dictionary mapping market_id to position value (USDC)
            markets: List of markets
            max_category_exposure: Maximum allowed exposure to any category (0-1)

        Returns:
            Dictionary with overexposure warnings
        """
        categories = self.group_markets_by_category(markets)

        total_exposure = sum(current_positions.values())

        if total_exposure == 0:
            return {'is_overexposed': False, 'warnings': []}

        category_exposures = {}
        for category, market_ids in categories.items():
            category_exposure = sum(current_positions.get(mid, 0) for mid in market_ids)
            category_exposures[category] = {
                'absolute': category_exposure,
                'percentage': category_exposure / total_exposure
            }

        warnings = []
        is_overexposed = False

        for category, exposure in category_exposures.items():
            if exposure['percentage'] > max_category_exposure:
                warnings.append(
                    f"Overexposed to {category}: {exposure['percentage']*100:.1f}% "
                    f"(limit: {max_category_exposure*100:.0f}%)"
                )
                is_overexposed = True

        return {
            'is_overexposed': is_overexposed,
            'warnings': warnings,
            'category_exposures': category_exposures
        }


class PortfolioOptimizer:
    """
    Optimize capital allocation across multiple markets.
    """

    def __init__(
        self,
        total_capital: float,
        kelly_fraction: float = 0.25,
        max_positions: int = 20,
        max_category_exposure: float = 0.40
    ):
        """
        Initialize portfolio optimizer.

        Args:
            total_capital: Total capital available
            kelly_fraction: Fraction of Kelly to use
            max_positions: Maximum number of concurrent positions
            max_category_exposure: Maximum exposure to any category
        """
        self.total_capital = total_capital
        self.kelly_calc = KellyCalculator(kelly_fraction)
        self.corr_analyzer = CorrelationAnalyzer()
        self.max_positions = max_positions
        self.max_category_exposure = max_category_exposure

    def optimize_allocations(
        self,
        opportunities: List[MarketOpportunity],
        current_positions: Dict[str, float],
        price_histories: Optional[Dict[str, pd.DataFrame]] = None
    ) -> Dict[str, float]:
        """
        Optimize capital allocation across opportunities.

        Args:
            opportunities: List of market opportunities
            current_positions: Current positions (market_id -> capital deployed)
            price_histories: Optional price histories for correlation analysis

        Returns:
            Dictionary mapping market_id to recommended capital allocation
        """
        # Filter to top opportunities by Sharpe ratio
        sorted_opps = sorted(opportunities, key=lambda x: x.sharpe_ratio, reverse=True)
        top_opps = sorted_opps[:self.max_positions]

        # Calculate correlation matrix if possible
        correlation_matrix = None
        # if price_histories is not None:
        #     # This would require matching opportunities to price histories
        #     # Skipping for now to keep it simple
        #     pass

        # Calculate Kelly allocations
        allocations = self.kelly_calc.calculate_kelly_sizes_portfolio(
            top_opps,
            self.total_capital,
            correlation_matrix
        )

        return allocations

    def rebalance_portfolio(
        self,
        current_positions: Dict[str, float],
        target_allocations: Dict[str, float],
        rebalance_threshold: float = 0.20
    ) -> Dict[str, Tuple[str, float]]:
        """
        Generate rebalancing trades.

        Args:
            current_positions: Current positions
            target_allocations: Target allocations
            rebalance_threshold: Only rebalance if difference > threshold (0-1)

        Returns:
            Dictionary mapping market_id to (action, amount)
            action: 'increase', 'decrease', 'close'
        """
        rebalances = {}

        # Check each target allocation
        for market_id, target in target_allocations.items():
            current = current_positions.get(market_id, 0)

            diff = target - current
            diff_pct = abs(diff) / target if target > 0 else 0

            if diff_pct > rebalance_threshold:
                if diff > 0:
                    rebalances[market_id] = ('increase', diff)
                else:
                    rebalances[market_id] = ('decrease', abs(diff))

        # Check for positions to close (not in target allocations)
        for market_id, current in current_positions.items():
            if market_id not in target_allocations and current > 0:
                rebalances[market_id] = ('close', current)

        return rebalances


def calculate_portfolio_var(
    positions: Dict[str, float],
    volatilities: Dict[str, float],
    correlation_matrix: Optional[np.ndarray] = None,
    confidence_level: float = 0.95
) -> float:
    """
    Calculate Portfolio Value at Risk (VaR).

    Args:
        positions: Market positions (market_id -> capital)
        volatilities: Volatilities for each market
        correlation_matrix: Optional correlation matrix
        confidence_level: Confidence level (e.g., 0.95 = 95%)

    Returns:
        VaR in USDC
    """
    if len(positions) == 0:
        return 0.0

    # Convert to arrays
    market_ids = list(positions.keys())
    position_values = np.array([positions[mid] for mid in market_ids])
    vols = np.array([volatilities.get(mid, 0.10) for mid in market_ids])

    if correlation_matrix is None:
        # Assume independence
        portfolio_variance = np.sum((position_values * vols) ** 2)
    else:
        # Use correlation matrix
        weighted_vols = position_values * vols
        portfolio_variance = weighted_vols @ correlation_matrix @ weighted_vols

    portfolio_std = np.sqrt(portfolio_variance)

    # VaR = portfolio_std * z_score
    # For 95% confidence: z = 1.645 (one-tailed)
    # For 99% confidence: z = 2.326
    if confidence_level == 0.95:
        z_score = 1.645
    elif confidence_level == 0.99:
        z_score = 2.326
    else:
        # Approximate
        z_score = 1.645

    var = portfolio_std * z_score

    return var
