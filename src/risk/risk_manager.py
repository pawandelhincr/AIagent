import math

from src.models import FairValueGap, FVGType, RiskProfile, Segment, SignalType, Target, TradeSignal


class RiskManager:
    """Position sizing and trade validation based on risk rules."""

    def __init__(self, risk_profile: RiskProfile, rr_config: dict):
        self.profile = risk_profile
        self.min_rr = rr_config.get("min_rr_ratio", 2.0)
        self.target1_rr = rr_config.get("target1_rr", 1.5)
        self.target2_rr = rr_config.get("target2_rr", 2.5)
        self.target3_rr = rr_config.get("target3_rr", 4.0)

    def calculate_position_size(
        self,
        entry: float,
        stop_loss: float,
        lot_size: int,
    ) -> tuple[int, float]:
        """
        Calculate position size based on fixed fractional risk.
        Returns (quantity_in_lots, risk_amount_inr).
        """
        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit == 0:
            return 0, 0.0

        risk_amount = self.profile.risk_per_trade
        raw_qty = risk_amount / risk_per_unit
        lots = max(1, math.floor(raw_qty / lot_size))
        quantity = lots * lot_size
        actual_risk = quantity * risk_per_unit

        return quantity, actual_risk

    def calculate_targets(
        self,
        entry: float,
        stop_loss: float,
        signal_type: SignalType,
    ) -> list[Target]:
        risk = abs(entry - stop_loss)
        direction = 1 if signal_type == SignalType.BUY else -1

        targets = [
            Target(
                level=1,
                price=entry + direction * risk * self.target1_rr,
                rr_ratio=self.target1_rr,
                quantity_pct=40.0,
            ),
            Target(
                level=2,
                price=entry + direction * risk * self.target2_rr,
                rr_ratio=self.target2_rr,
                quantity_pct=35.0,
            ),
            Target(
                level=3,
                price=entry + direction * risk * self.target3_rr,
                rr_ratio=self.target3_rr,
                quantity_pct=25.0,
            ),
        ]
        return targets

    def validate_trade(
        self,
        entry: float,
        stop_loss: float,
        signal_type: SignalType,
    ) -> tuple[bool, str]:
        if not self.profile.can_trade:
            return False, self.profile.block_reason or "Trading blocked"

        risk = abs(entry - stop_loss)
        if risk == 0:
            return False, "Invalid stop loss (zero risk distance)"

        targets = self.calculate_targets(entry, stop_loss, signal_type)
        max_reward = abs(targets[-1].price - entry)
        rr_ratio = max_reward / risk

        if rr_ratio < self.min_rr:
            return False, f"R:R ratio {rr_ratio:.2f} below minimum {self.min_rr}"

        risk_pct_of_entry = (risk / entry) * 100
        if risk_pct_of_entry > 2.0:
            return False, f"Stop loss too wide ({risk_pct_of_entry:.2f}% of entry)"

        return True, "OK"

    def build_signal(
        self,
        symbol: str,
        symbol_name: str,
        segment: Segment,
        signal_type: SignalType,
        entry: float,
        stop_loss: float,
        fvg: FairValueGap,
        lot_size: int,
        timeframe: str,
        confidence: float,
        notes: str = "",
    ) -> TradeSignal | None:
        valid, reason = self.validate_trade(entry, stop_loss, signal_type)
        if not valid:
            return None

        quantity, risk_amount = self.calculate_position_size(entry, stop_loss, lot_size)
        targets = self.calculate_targets(entry, stop_loss, signal_type)
        risk = abs(entry - stop_loss)
        max_reward = abs(targets[-1].price - entry)
        rr_ratio = max_reward / risk

        return TradeSignal(
            symbol=symbol,
            symbol_name=symbol_name,
            segment=segment,
            signal_type=signal_type,
            entry_price=entry,
            stop_loss=stop_loss,
            targets=targets,
            fvg=fvg,
            risk_amount=risk_amount,
            position_size=quantity,
            lot_size=lot_size,
            risk_reward_ratio=rr_ratio,
            confidence=confidence,
            timeframe=timeframe,
            notes=notes,
        )

    def get_risk_summary(self) -> dict:
        return {
            "capital": self.profile.capital,
            "risk_per_trade_inr": round(self.profile.risk_per_trade, 2),
            "risk_per_trade_pct": self.profile.risk_per_trade_pct,
            "max_daily_loss_inr": round(self.profile.max_daily_loss, 2),
            "max_daily_loss_pct": self.profile.max_daily_loss_pct,
            "daily_pnl": round(self.profile.daily_pnl, 2),
            "open_trades": self.profile.open_trades,
            "trades_today": self.profile.trades_today,
            "can_trade": self.profile.can_trade,
            "block_reason": self.profile.block_reason,
        }
