"""
Dynamic Spread Adjustment for Market Making

Automatically adjusts spreads based on:
1. Market volatility (wider spreads in volatile markets)
2. Inventory position (skew spreads to reduce inventory)
3. Market regime (tighter in mean-reverting, wider in trending)
4. Order book depth (compete more aggressively with deep books)
5. Time to market close (widen as uncertainty increases)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime, timezone
from poly_data.regime_detector import MarketRegime


class DynamicSpreadCalculator:
    """
    Calculate optimal bid-ask spreads based on market conditions.
    """

    def __init__(
        self,
        base_spread_bps: float = 20,  # 20 bps = 0.20% base spread
        min_spread_ticks: int = 2,  # Minimum 2 ticks
        max_spread_pct: float = 0.10  # Maximum 10% spread
    ):
        """
        Initialize dynamic spread calculator.

        Args:
            base_spread_bps: Base spread in basis points
            min_spread_ticks: Minimum spread in ticks
            max_spread_pct: Maximum spread as percentage of price
        """
        self.base_spread_bps = base_spread_bps
        self.min_spread_ticks = min_spread_ticks
        self.max_spread_pct = max_spread_pct

    def calculate_spread(
        self,
        midpoint: float,
        tick_size: float,
        volatility_1hour: float,
        volatility_24hour: float,
        position: float,
        max_position: float,
        orderbook_depth_bid: float,
        orderbook_depth_ask: float,
        market_regime: MarketRegime,
        hours_to_close: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Calculate optimal bid and ask prices based on all factors.

        Returns:
            (bid_price, ask_price)
        """
        # Start with base spread
        base_spread = (self.base_spread_bps / 10000) * midpoint

        # Adjust for volatility
        spread_vol_adj = self._volatility_adjustment(
            base_spread,
            volatility_1hour,
            volatility_24hour
        )

        # Adjust for inventory
        bid_adj, ask_adj = self._inventory_adjustment(
            spread_vol_adj,
            position,
            max_position
        )

        # Adjust for market regime
        bid_adj, ask_adj = self._regime_adjustment(
            bid_adj,
            ask_adj,
            market_regime
        )

        # Adjust for orderbook depth
        bid_adj, ask_adj = self._depth_adjustment(
            bid_adj,
            ask_adj,
            orderbook_depth_bid,
            orderbook_depth_ask
        )

        # Adjust for time to close
        if hours_to_close is not None:
            bid_adj, ask_adj = self._time_adjustment(
                bid_adj,
                ask_adj,
                hours_to_close
            )

        # Calculate final prices
        bid_price = midpoint - bid_adj
        ask_price = midpoint + ask_adj

        # Enforce minimum spread
        min_spread_dollars = self.min_spread_ticks * tick_size
        if ask_price - bid_price < min_spread_dollars:
            bid_price = midpoint - min_spread_dollars / 2
            ask_price = midpoint + min_spread_dollars / 2

        # Enforce maximum spread
        max_spread_dollars = midpoint * self.max_spread_pct
        if ask_price - bid_price > max_spread_dollars:
            bid_price = midpoint - max_spread_dollars / 2
            ask_price = midpoint + max_spread_dollars / 2

        # Round to tick size
        bid_price = self._round_to_tick(bid_price, tick_size, round_down=True)
        ask_price = self._round_to_tick(ask_price, tick_size, round_down=False)

        # Ensure valid prices
        bid_price = max(0.01, min(bid_price, 0.99))
        ask_price = max(0.01, min(ask_price, 0.99))

        return bid_price, ask_price

    def _volatility_adjustment(
        self,
        base_spread: float,
        volatility_1hour: float,
        volatility_24hour: float
    ) -> float:
        """
        Adjust spread based on volatility.

        Higher volatility = wider spreads to protect against adverse selection.
        """
        # Use average of short-term and medium-term vol
        avg_vol = (volatility_1hour + volatility_24hour) / 2

        # Volatility multiplier
        # 0.5 vol = 1.0x, 1.0 vol = 1.5x, 2.0 vol = 2.5x, 5.0 vol = 5.0x
        if avg_vol < 0.5:
            vol_mult = 1.0
        elif avg_vol < 1.0:
            vol_mult = 1.0 + (avg_vol - 0.5)  # Linear from 1.0 to 1.5
        elif avg_vol < 2.0:
            vol_mult = 1.5 + (avg_vol - 1.0)  # Linear from 1.5 to 2.5
        else:
            vol_mult = min(2.5 + (avg_vol - 2.0) * 0.5, 5.0)  # Up to 5x

        return base_spread * vol_mult

    def _inventory_adjustment(
        self,
        spread: float,
        position: float,
        max_position: float
    ) -> Tuple[float, float]:
        """
        Skew spreads based on inventory to reduce position.

        If long, make bid less aggressive and ask more aggressive.
        If short, make ask less aggressive and bid more aggressive.
        """
        if max_position == 0:
            return spread, spread

        # Calculate inventory skew (-1 to 1)
        inventory_skew = position / max_position

        # Clamp to reasonable range
        inventory_skew = max(-1.0, min(1.0, inventory_skew))

        # Skew factor (how much to adjust)
        # At 50% of max position, start adjusting
        # At 100% of max position, adjust by up to 50% of spread
        if abs(inventory_skew) < 0.5:
            skew_pct = 0
        else:
            skew_pct = (abs(inventory_skew) - 0.5) * 2  # 0 to 1

        skew_amount = spread * skew_pct * 0.5  # Max 50% adjustment

        if inventory_skew > 0:
            # Long position: widen bid, tighten ask
            bid_spread = spread + skew_amount
            ask_spread = spread - skew_amount
        else:
            # Short position: tighten bid, widen ask
            bid_spread = spread - skew_amount
            ask_spread = spread + skew_amount

        # Ensure both are positive
        bid_spread = max(spread * 0.5, bid_spread)
        ask_spread = max(spread * 0.5, ask_spread)

        return bid_spread, ask_spread

    def _regime_adjustment(
        self,
        bid_spread: float,
        ask_spread: float,
        market_regime: MarketRegime
    ) -> Tuple[float, float]:
        """
        Adjust spreads based on market regime.
        """
        if market_regime == MarketRegime.MEAN_REVERTING:
            # Tighten spreads (multiply by 0.8)
            return bid_spread * 0.8, ask_spread * 0.8
        elif market_regime == MarketRegime.STABLE:
            # Keep as is
            return bid_spread, ask_spread
        elif market_regime == MarketRegime.TRENDING:
            # Widen spreads (multiply by 1.5)
            return bid_spread * 1.5, ask_spread * 1.5
        elif market_regime == MarketRegime.EVENT_DRIVEN:
            # Significantly widen spreads (multiply by 2.5)
            return bid_spread * 2.5, ask_spread * 2.5
        elif market_regime == MarketRegime.VOLATILE:
            # Widen spreads (multiply by 2.0)
            return bid_spread * 2.0, ask_spread * 2.0
        else:
            # Unknown - be cautious, widen slightly
            return bid_spread * 1.2, ask_spread * 1.2

    def _depth_adjustment(
        self,
        bid_spread: float,
        ask_spread: float,
        orderbook_depth_bid: float,
        orderbook_depth_ask: float
    ) -> Tuple[float, float]:
        """
        Adjust spreads based on orderbook depth.

        More depth = more competition = tighter spreads needed to compete.
        """
        # Normalize depth (assume typical depth is around 1000 shares)
        typical_depth = 1000

        bid_depth_factor = min(orderbook_depth_bid / typical_depth, 2.0)
        ask_depth_factor = min(orderbook_depth_ask / typical_depth, 2.0)

        # More depth = tighter spread (multiply by 0.7 to 1.0)
        bid_mult = 1.0 - (bid_depth_factor - 1.0) * 0.3 if bid_depth_factor > 1.0 else 1.0
        ask_mult = 1.0 - (ask_depth_factor - 1.0) * 0.3 if ask_depth_factor > 1.0 else 1.0

        return bid_spread * bid_mult, ask_spread * ask_mult

    def _time_adjustment(
        self,
        bid_spread: float,
        ask_spread: float,
        hours_to_close: float
    ) -> Tuple[float, float]:
        """
        Adjust spreads based on time to market close.

        As market approaches close, widen spreads due to increasing uncertainty.
        """
        if hours_to_close > 72:  # More than 3 days
            return bid_spread, ask_spread
        elif hours_to_close > 24:  # 1-3 days
            mult = 1.1
        elif hours_to_close > 6:  # 6-24 hours
            mult = 1.3
        elif hours_to_close > 1:  # 1-6 hours
            mult = 1.6
        else:  # < 1 hour
            mult = 2.0

        return bid_spread * mult, ask_spread * mult

    def _round_to_tick(self, price: float, tick_size: float, round_down: bool) -> float:
        """Round price to nearest tick."""
        if round_down:
            return np.floor(price / tick_size) * tick_size
        else:
            return np.ceil(price / tick_size) * tick_size


class InventoryManager:
    """
    Advanced inventory management for market making.
    """

    def __init__(
        self,
        max_inventory: float = 1000,
        target_inventory: float = 0,
        inventory_penalty_factor: float = 0.01
    ):
        """
        Initialize inventory manager.

        Args:
            max_inventory: Maximum allowed inventory
            target_inventory: Target inventory (usually 0 for market neutral)
            inventory_penalty_factor: Penalty per unit of inventory deviation
        """
        self.max_inventory = max_inventory
        self.target_inventory = target_inventory
        self.inventory_penalty_factor = inventory_penalty_factor

    def should_quote_bid(self, current_position: float) -> bool:
        """Should we quote a bid given current position?"""
        return current_position < self.max_inventory

    def should_quote_ask(self, current_position: float) -> bool:
        """Should we quote an ask given current position?"""
        return current_position > -self.max_inventory

    def calculate_inventory_penalty(self, position: float) -> float:
        """
        Calculate penalty for deviating from target inventory.

        This penalty is subtracted from bid/ask prices to encourage
        inventory reduction.
        """
        deviation = abs(position - self.target_inventory)
        penalty = deviation * self.inventory_penalty_factor

        return penalty

    def should_panic_exit(
        self,
        position: float,
        unrealized_pnl_pct: float,
        hours_to_close: Optional[float] = None
    ) -> bool:
        """
        Determine if we should panic exit a position.

        Reasons to panic exit:
        1. Position > 150% of max_inventory
        2. Large unrealized loss (> 10%)
        3. Close to market close with large position
        """
        # Reason 1: Excessive position
        if abs(position) > self.max_inventory * 1.5:
            return True

        # Reason 2: Large loss
        if unrealized_pnl_pct < -10:
            return True

        # Reason 3: Near close with large position
        if hours_to_close is not None and hours_to_close < 2:
            if abs(position) > self.max_inventory * 0.5:
                return True

        return False

    def calculate_target_size_adjustment(
        self,
        position: float,
        base_size: float
    ) -> Tuple[float, float]:
        """
        Adjust order sizes based on current inventory.

        Returns:
            (bid_size, ask_size)
        """
        inventory_ratio = position / self.max_inventory if self.max_inventory > 0 else 0

        if inventory_ratio > 0.7:
            # Very long, reduce bid size, increase ask size
            bid_size = base_size * 0.5
            ask_size = base_size * 1.5
        elif inventory_ratio > 0.4:
            # Moderately long, slightly reduce bid size
            bid_size = base_size * 0.8
            ask_size = base_size * 1.2
        elif inventory_ratio < -0.7:
            # Very short, increase bid size, reduce ask size
            bid_size = base_size * 1.5
            ask_size = base_size * 0.5
        elif inventory_ratio < -0.4:
            # Moderately short, slightly increase bid size
            bid_size = base_size * 1.2
            ask_size = base_size * 0.8
        else:
            # Neutral, normal sizes
            bid_size = base_size
            ask_size = base_size

        return bid_size, ask_size
