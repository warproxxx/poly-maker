"""
Market Regime Detection for Polymarket Markets

Classifies markets into different regimes to inform trading strategy:
1. Mean-Reverting: Ideal for market making (high autocorrelation, low drift)
2. Trending: Dangerous for market making (strong directional movement)
3. Event-Driven: High risk (sudden spikes, news-driven)
4. Stable: Low volatility, predictable (good for MM)

Uses multiple indicators:
- Hurst Exponent: <0.5 = mean-reverting, >0.5 = trending
- Autocorrelation: Measures price predictability
- Volatility Regime: Low/Medium/High
- Drift Detection: Tests for persistent directional bias
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from enum import Enum


class MarketRegime(Enum):
    """Market regime classifications."""
    MEAN_REVERTING = "mean_reverting"  # Best for market making
    TRENDING = "trending"  # Avoid market making
    EVENT_DRIVEN = "event_driven"  # High risk, avoid or use wide spreads
    STABLE = "stable"  # Very good for market making
    VOLATILE = "volatile"  # Risky but potentially profitable
    UNKNOWN = "unknown"  # Not enough data


class RegimeDetector:
    """
    Detect market regimes to optimize trading strategy.
    """

    def __init__(self):
        """Initialize regime detector."""
        pass

    def calculate_hurst_exponent(self, prices: pd.Series, max_lag: int = 20) -> float:
        """
        Calculate Hurst Exponent using R/S analysis.

        H < 0.5: Mean-reverting (good for market making)
        H = 0.5: Random walk (neutral)
        H > 0.5: Trending (bad for market making)

        Args:
            prices: Price series
            max_lag: Maximum lag for R/S calculation

        Returns:
            Hurst exponent (0-1)
        """
        if len(prices) < max_lag * 2:
            return 0.5  # Not enough data, assume random walk

        prices = np.array(prices)

        lags = range(2, max_lag)
        tau = []
        rs_values = []

        for lag in lags:
            # Split into chunks
            chunks = [prices[i:i+lag] for i in range(0, len(prices), lag) if len(prices[i:i+lag]) == lag]

            if len(chunks) == 0:
                continue

            rs_chunk = []
            for chunk in chunks:
                # Mean
                mean = np.mean(chunk)

                # Mean-adjusted series
                Y = np.cumsum(chunk - mean)

                # Range
                R = np.max(Y) - np.min(Y)

                # Standard deviation
                S = np.std(chunk)

                # R/S ratio
                if S > 0:
                    rs_chunk.append(R / S)

            if len(rs_chunk) > 0:
                tau.append(lag)
                rs_values.append(np.mean(rs_chunk))

        if len(tau) < 2:
            return 0.5

        # Linear regression in log-log space
        # log(R/S) = H * log(tau) + const
        log_tau = np.log(tau)
        log_rs = np.log(rs_values)

        # Remove any infinities or NaNs
        valid = np.isfinite(log_tau) & np.isfinite(log_rs)
        if np.sum(valid) < 2:
            return 0.5

        log_tau = log_tau[valid]
        log_rs = log_rs[valid]

        # Fit line
        coefficients = np.polyfit(log_tau, log_rs, 1)
        hurst = coefficients[0]

        # Clamp to valid range
        hurst = max(0.0, min(1.0, hurst))

        return hurst

    def calculate_autocorrelation(self, returns: pd.Series, lag: int = 1) -> float:
        """
        Calculate autocorrelation of returns.

        High positive autocorrelation = trending
        High negative autocorrelation = mean-reverting

        Args:
            returns: Return series
            lag: Lag for autocorrelation

        Returns:
            Autocorrelation coefficient (-1 to 1)
        """
        if len(returns) < lag + 10:
            return 0.0

        # Remove NaNs
        returns_clean = returns.dropna()

        if len(returns_clean) < lag + 10:
            return 0.0

        # Calculate autocorrelation
        autocorr = returns_clean.autocorr(lag=lag)

        return autocorr if np.isfinite(autocorr) else 0.0

    def detect_drift(self, prices: pd.Series, window: int = 50) -> Tuple[float, float]:
        """
        Detect if there's a persistent drift (trend) in prices.

        Uses linear regression to find slope and significance.

        Args:
            prices: Price series
            window: Window for drift detection

        Returns:
            (drift_per_period, p_value)
        """
        if len(prices) < window:
            return 0.0, 1.0

        # Use last 'window' prices
        recent_prices = prices.iloc[-window:].values
        x = np.arange(len(recent_prices))

        # Linear regression
        coefficients = np.polyfit(x, recent_prices, 1)
        slope = coefficients[0]

        # Calculate R-squared to assess significance
        fitted = np.polyval(coefficients, x)
        residuals = recent_prices - fitted
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((recent_prices - np.mean(recent_prices)) ** 2)

        if ss_tot == 0:
            r_squared = 0
        else:
            r_squared = 1 - (ss_res / ss_tot)

        # Convert R-squared to rough p-value estimate
        # (proper p-value would require t-test, but this is faster)
        p_value = 1 - r_squared

        return slope, p_value

    def classify_volatility_regime(
        self,
        volatility_1hour: float,
        volatility_24hour: float,
        volatility_7day: float
    ) -> str:
        """
        Classify volatility regime.

        Args:
            volatility_1hour: 1-hour annualized volatility
            volatility_24hour: 24-hour annualized volatility
            volatility_7day: 7-day annualized volatility

        Returns:
            Volatility regime: 'low', 'medium', 'high', 'explosive'
        """
        # Average volatility
        avg_vol = (volatility_1hour + volatility_24hour + volatility_7day) / 3

        # Also check if short-term vol >> long-term vol (event-driven)
        vol_ratio = volatility_1hour / volatility_7day if volatility_7day > 0 else 1

        if avg_vol < 0.5:
            return 'low'
        elif avg_vol < 2.0:
            if vol_ratio > 3:
                return 'explosive'  # Short-term spike
            return 'medium'
        elif avg_vol < 5.0:
            return 'high'
        else:
            return 'explosive'

    def detect_regime(
        self,
        price_history: pd.DataFrame,
        volatility_1hour: float,
        volatility_24hour: float,
        volatility_7day: float
    ) -> Dict[str, any]:
        """
        Detect the market regime using multiple indicators.

        Args:
            price_history: DataFrame with columns ['t', 'p']
            volatility_1hour: 1-hour annualized volatility
            volatility_24hour: 24-hour annualized volatility
            volatility_7day: 7-day annualized volatility

        Returns:
            Dictionary with regime classification and confidence
        """
        if len(price_history) < 50:
            return {
                'regime': MarketRegime.UNKNOWN,
                'confidence': 0.0,
                'hurst_exponent': 0.5,
                'autocorrelation_lag1': 0.0,
                'drift': 0.0,
                'volatility_regime': 'unknown',
                'is_good_for_mm': False,
                'recommended_strategy': 'avoid'
            }

        # Calculate indicators
        prices = price_history['p']

        # Hurst exponent
        hurst = self.calculate_hurst_exponent(prices)

        # Calculate returns for autocorrelation
        price_history_copy = price_history.copy()
        price_history_copy['returns'] = np.log(price_history_copy['p'] / price_history_copy['p'].shift(1))
        returns = price_history_copy['returns'].dropna()

        # Autocorrelation
        autocorr_lag1 = self.calculate_autocorrelation(returns, lag=1)
        autocorr_lag5 = self.calculate_autocorrelation(returns, lag=5)

        # Drift
        drift, drift_pvalue = self.detect_drift(prices, window=100)

        # Volatility regime
        vol_regime = self.classify_volatility_regime(
            volatility_1hour,
            volatility_24hour,
            volatility_7day
        )

        # Classify regime
        regime = self._classify_regime(
            hurst, autocorr_lag1, autocorr_lag5, drift, drift_pvalue, vol_regime
        )

        # Determine if good for market making
        is_good_for_mm = regime['regime'] in [
            MarketRegime.MEAN_REVERTING,
            MarketRegime.STABLE
        ]

        # Recommend strategy
        strategy = self._recommend_strategy(regime['regime'], vol_regime)

        return {
            'regime': regime['regime'],
            'confidence': regime['confidence'],
            'hurst_exponent': hurst,
            'autocorrelation_lag1': autocorr_lag1,
            'autocorrelation_lag5': autocorr_lag5,
            'drift': drift,
            'drift_pvalue': drift_pvalue,
            'volatility_regime': vol_regime,
            'is_good_for_mm': is_good_for_mm,
            'recommended_strategy': strategy,
            'signals': regime['signals']
        }

    def _classify_regime(
        self,
        hurst: float,
        autocorr_lag1: float,
        autocorr_lag5: float,
        drift: float,
        drift_pvalue: float,
        vol_regime: str
    ) -> Dict[str, any]:
        """
        Classify regime based on indicators.

        Returns:
            Dictionary with regime and confidence
        """
        signals = []
        confidence_scores = []

        # Signal 1: Hurst Exponent
        if hurst < 0.4:
            signals.append("strong_mean_reversion")
            confidence_scores.append(0.4 - hurst)
        elif hurst < 0.5:
            signals.append("weak_mean_reversion")
            confidence_scores.append(0.5 - hurst)
        elif hurst > 0.6:
            signals.append("strong_trending")
            confidence_scores.append(hurst - 0.6)
        elif hurst > 0.5:
            signals.append("weak_trending")
            confidence_scores.append(hurst - 0.5)

        # Signal 2: Autocorrelation
        if autocorr_lag1 < -0.2:
            signals.append("negative_autocorr_mean_reversion")
            confidence_scores.append(abs(autocorr_lag1))
        elif autocorr_lag1 > 0.2:
            signals.append("positive_autocorr_trending")
            confidence_scores.append(autocorr_lag1)

        # Signal 3: Drift
        if drift_pvalue < 0.05:  # Significant drift
            if abs(drift) > 0.001:
                signals.append("significant_drift_trending")
                confidence_scores.append(1 - drift_pvalue)

        # Signal 4: Volatility
        if vol_regime == 'explosive':
            signals.append("explosive_volatility_event_driven")
            confidence_scores.append(0.9)
        elif vol_regime == 'low':
            signals.append("low_volatility_stable")
            confidence_scores.append(0.7)

        # Determine regime
        if vol_regime == 'explosive':
            regime = MarketRegime.EVENT_DRIVEN
        elif vol_regime == 'low' and hurst < 0.5:
            regime = MarketRegime.STABLE
        elif hurst < 0.45 or autocorr_lag1 < -0.15:
            regime = MarketRegime.MEAN_REVERTING
        elif hurst > 0.55 or (autocorr_lag1 > 0.2 and drift_pvalue < 0.1):
            regime = MarketRegime.TRENDING
        elif vol_regime in ['high', 'explosive']:
            regime = MarketRegime.VOLATILE
        else:
            regime = MarketRegime.STABLE

        # Calculate confidence
        if len(confidence_scores) > 0:
            confidence = np.mean(confidence_scores)
        else:
            confidence = 0.3  # Low confidence if no strong signals

        return {
            'regime': regime,
            'confidence': min(confidence, 0.95),
            'signals': signals
        }

    def _recommend_strategy(self, regime: MarketRegime, vol_regime: str) -> str:
        """
        Recommend trading strategy based on regime.

        Returns:
            Strategy recommendation
        """
        if regime == MarketRegime.MEAN_REVERTING:
            return "aggressive_mm_tight_spreads"
        elif regime == MarketRegime.STABLE:
            return "conservative_mm_moderate_spreads"
        elif regime == MarketRegime.TRENDING:
            if vol_regime == 'low':
                return "conservative_mm_wide_spreads"
            else:
                return "avoid_or_directional_only"
        elif regime == MarketRegime.EVENT_DRIVEN:
            return "avoid_or_very_wide_spreads"
        elif regime == MarketRegime.VOLATILE:
            return "reduce_size_wide_spreads"
        else:
            return "cautious_wait_for_clarity"


def classify_market_for_discovery(
    volatility_1hour: float,
    volatility_24hour: float,
    volatility_7day: float,
    price_history: Optional[pd.DataFrame] = None
) -> Dict[str, any]:
    """
    Quick regime classification for market discovery.

    Args:
        volatility_1hour: 1-hour volatility
        volatility_24hour: 24-hour volatility
        volatility_7day: 7-day volatility
        price_history: Optional price history for full analysis

    Returns:
        Regime classification
    """
    detector = RegimeDetector()

    if price_history is not None and len(price_history) >= 50:
        return detector.detect_regime(
            price_history,
            volatility_1hour,
            volatility_24hour,
            volatility_7day
        )
    else:
        # Simple classification based on volatility only
        vol_regime = detector.classify_volatility_regime(
            volatility_1hour,
            volatility_24hour,
            volatility_7day
        )

        if vol_regime == 'low':
            regime = MarketRegime.STABLE
            is_good = True
            strategy = "conservative_mm_moderate_spreads"
        elif vol_regime == 'medium':
            regime = MarketRegime.STABLE
            is_good = True
            strategy = "conservative_mm_moderate_spreads"
        elif vol_regime == 'explosive':
            regime = MarketRegime.EVENT_DRIVEN
            is_good = False
            strategy = "avoid_or_very_wide_spreads"
        else:
            regime = MarketRegime.VOLATILE
            is_good = False
            strategy = "reduce_size_wide_spreads"

        return {
            'regime': regime,
            'confidence': 0.5,
            'volatility_regime': vol_regime,
            'is_good_for_mm': is_good,
            'recommended_strategy': strategy,
            'hurst_exponent': None,
            'autocorrelation_lag1': None,
            'drift': None
        }
