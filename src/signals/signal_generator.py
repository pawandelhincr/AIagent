import pandas as pd

from src.analysis.fvg_detector import FVGDetector
from src.models import FVGType, Segment, SignalType, TradeSignal
from src.risk.risk_manager import RiskManager


class SignalGenerator:
    """
    Generate BUY/SELL signals when price interacts with Fair Value Gaps.

    Logic:
    - Bullish FVG + price in zone → BUY (expect bounce up)
    - Bearish FVG + price in zone → SELL (expect rejection down)
    - Stop loss placed beyond FVG boundary
    - Targets calculated via risk-reward ratios
    """

    def __init__(self, fvg_detector: FVGDetector, risk_manager: RiskManager):
        self.fvg = fvg_detector
        self.risk = risk_manager

    def analyze(
        self,
        df: pd.DataFrame,
        symbol_key: str,
        symbol_name: str,
        lot_size: int,
        segment: Segment = Segment.CASH,
        timeframe: str = "15m",
    ) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        fvgs = self.fvg.detect(df)
        current_price = float(df["close"].iloc[-1])

        for fvg in fvgs:
            if not self.fvg.price_in_fvg(current_price, fvg):
                continue

            signal = self._generate_from_fvg(
                fvg=fvg,
                current_price=current_price,
                symbol_key=symbol_key,
                symbol_name=symbol_name,
                lot_size=lot_size,
                segment=segment,
                timeframe=timeframe,
                df=df,
            )
            if signal:
                signals.append(signal)

        return sorted(signals, key=lambda s: s.confidence, reverse=True)

    def _generate_from_fvg(
        self,
        fvg,
        current_price: float,
        symbol_key: str,
        symbol_name: str,
        lot_size: int,
        segment: Segment,
        timeframe: str,
        df: pd.DataFrame,
    ) -> TradeSignal | None:
        buffer_pct = 0.05  # SL buffer beyond FVG

        if fvg.fvg_type == FVGType.BULLISH:
            signal_type = SignalType.BUY
            entry = fvg.midpoint
            stop_loss = fvg.bottom * (1 - buffer_pct / 100)
            notes = (
                f"Bullish FVG detected. Price retracing into gap zone "
                f"({fvg.bottom:.2f} - {fvg.top:.2f}). Expect bounce."
            )
        else:
            signal_type = SignalType.SELL
            entry = fvg.midpoint
            stop_loss = fvg.top * (1 + buffer_pct / 100)
            notes = (
                f"Bearish FVG detected. Price retracing into gap zone "
                f"({fvg.bottom:.2f} - {fvg.top:.2f}). Expect rejection."
            )

        confidence = self._calculate_confidence(fvg, df, current_price)

        return self.risk.build_signal(
            symbol=symbol_key,
            symbol_name=symbol_name,
            segment=segment,
            signal_type=signal_type,
            entry=entry,
            stop_loss=stop_loss,
            fvg=fvg,
            lot_size=lot_size,
            timeframe=timeframe,
            confidence=confidence,
            notes=notes,
        )

    def _calculate_confidence(self, fvg, df: pd.DataFrame, price: float) -> float:
        score = 50.0

        # Larger gap = stronger imbalance
        if fvg.gap_pct > 0.15:
            score += 15
        elif fvg.gap_pct > 0.08:
            score += 10
        else:
            score += 5

        # Fresh FVG (recent)
        age = len(df) - 1 - fvg.bar_index
        if age <= 10:
            score += 20
        elif age <= 25:
            score += 10

        # Price at midpoint of FVG (ideal entry)
        zone_range = fvg.top - fvg.bottom
        if zone_range > 0:
            position_in_zone = abs(price - fvg.midpoint) / (zone_range / 2)
            if position_in_zone < 0.3:
                score += 15

        # Trend alignment (simple: compare with 20-period SMA)
        if len(df) >= 20:
            sma20 = df["close"].rolling(20).mean().iloc[-1]
            if fvg.fvg_type == FVGType.BULLISH and price > sma20:
                score += 10
            elif fvg.fvg_type == FVGType.BEARISH and price < sma20:
                score += 10

        return min(score, 100.0)

    def get_fvg_zones(
        self,
        df: pd.DataFrame,
        symbol_key: str,
    ) -> list[dict]:
        """Return all active FVG zones for charting / display."""
        fvgs = self.fvg.detect(df)
        current_price = float(df["close"].iloc[-1])

        return [
            {
                "symbol": symbol_key,
                "type": f.fvg_type.value,
                "top": round(f.top, 2),
                "bottom": round(f.bottom, 2),
                "midpoint": round(f.midpoint, 2),
                "gap_pct": round(f.gap_pct, 4),
                "formed_at": f.formed_at.isoformat(),
                "is_active": f.is_active,
                "distance_from_price": round(
                    min(abs(current_price - f.bottom), abs(current_price - f.top)), 2
                ),
            }
            for f in fvgs
        ]
