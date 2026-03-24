from tweet_engine.models import Position, SimulatedFill


class ConservativeFillSimulator:
    def __init__(self, default_slippage_bps: float = 0.0):
        self.default_slippage_bps = default_slippage_bps

    def execute_signal(self, signal, state):
        quote = state.get_quote(signal.condition_id)
        if quote is None:
            fill = SimulatedFill(
                timestamp=signal.timestamp,
                strategy_name=signal.strategy_name,
                condition_id=signal.condition_id,
                side=signal.side,
                size=0,
                price=0,
                status="rejected",
                signal_id=signal.signal_id,
                reason="missing_quote",
            )
            state.fills.append(fill)
            return fill

        if signal.side == "BUY":
            visible_size = max(quote.ask_size, 0)
            price = quote.ask * (1 + self.default_slippage_bps / 10000)
            if signal.limit_price < price or visible_size <= 0:
                fill_size = 0
                status = "rejected"
            else:
                fill_size = min(signal.size, visible_size)
                status = "filled" if fill_size > 0 else "rejected"
        else:
            visible_size = max(quote.bid_size, 0)
            price = quote.bid * (1 - self.default_slippage_bps / 10000)
            if signal.limit_price > price or visible_size <= 0:
                fill_size = 0
                status = "rejected"
            else:
                fill_size = min(signal.size, visible_size)
                status = "filled" if fill_size > 0 else "rejected"

        fill = SimulatedFill(
            timestamp=signal.timestamp,
            strategy_name=signal.strategy_name,
            condition_id=signal.condition_id,
            side=signal.side,
            size=fill_size,
            price=round(price, 10) if fill_size > 0 else 0,
            status=status,
            signal_id=signal.signal_id,
            reason=signal.reason,
        )

        if fill.status == "filled":
            self._apply_fill(fill, state)

        state.fills.append(fill)
        return fill

    def _apply_fill(self, fill, state):
        position = state.get_position(fill.condition_id)

        if fill.side == "BUY":
            new_size = position.size + fill.size
            if new_size <= 0:
                position.avg_price = fill.price
            elif position.size <= 0:
                position.avg_price = fill.price
            else:
                position.avg_price = (
                    position.avg_price * position.size + fill.price * fill.size
                ) / new_size
            position.size = new_size
            return

        sell_size = fill.size
        if position.size > 0:
            closed_size = min(position.size, sell_size)
            state.realized_pnl += (fill.price - position.avg_price) * closed_size
        position.size -= sell_size
        if position.size == 0:
            position.avg_price = 0.0
        elif position.size < 0:
            position.avg_price = fill.price

