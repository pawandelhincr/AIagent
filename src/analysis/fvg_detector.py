"""
Fair Value Gap (FVG) Detector for Indian Markets.

FVG is an imbalance zone where price moved quickly leaving a gap:
- Bullish FVG: Candle[i-2].high < Candle[i].low  (gap up)
- Bearish FVG: Candle[i-2].low > Candle[i].high  (gap down)

Price often retraces to fill these gaps before continuing trend.
"""

from datetime import datetime

import pandas as pd

from src.models import FVGType, FairValueGap


class FVGDetector:
    def __init__(
        self,
        min_gap_pct: float = 0.05,
        max_gap_age_bars: int = 50,
    ):
        self.min_gap_pct = min_gap_pct
        self.max_gap_age_bars = max_gap_age_bars

    def detect(self, df: pd.DataFrame) -> list[FairValueGap]:
        fvgs: list[FairValueGap] = []
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        timestamps = df.index

        for i in range(2, len(df)):
            candle1_high = highs[i - 2]
            candle1_low = lows[i - 2]
            candle3_high = highs[i]
            candle3_low = lows[i]
            ref_price = closes[i]

            # Bullish FVG: gap between candle 1 high and candle 3 low
            if candle3_low > candle1_high:
                gap_size = candle3_low - candle1_high
                gap_pct = (gap_size / ref_price) * 100
                if gap_pct >= self.min_gap_pct:
                    fvgs.append(FairValueGap(
                        fvg_type=FVGType.BULLISH,
                        top=candle3_low,
                        bottom=candle1_high,
                        midpoint=(candle3_low + candle1_high) / 2,
                        gap_size=gap_size,
                        gap_pct=gap_pct,
                        formed_at=timestamps[i],
                        bar_index=i,
                    ))

            # Bearish FVG: gap between candle 1 low and candle 3 high
            if candle1_low > candle3_high:
                gap_size = candle1_low - candle3_high
                gap_pct = (gap_size / ref_price) * 100
                if gap_pct >= self.min_gap_pct:
                    fvgs.append(FairValueGap(
                        fvg_type=FVGType.BEARISH,
                        top=candle1_low,
                        bottom=candle3_high,
                        midpoint=(candle1_low + candle3_high) / 2,
                        gap_size=gap_size,
                        gap_pct=gap_pct,
                        formed_at=timestamps[i],
                        bar_index=i,
                    ))

        return self._filter_active(fvgs, df)

    def _filter_active(self, fvgs: list[FairValueGap], df: pd.DataFrame) -> list[FairValueGap]:
        current_bar = len(df) - 1
        current_price = float(df["close"].iloc[-1])
        active: list[FairValueGap] = []

        for fvg in fvgs:
            age = current_bar - fvg.bar_index
            if age > self.max_gap_age_bars:
                continue

            filled = self._is_filled(fvg, df, fvg.bar_index)
            fvg.is_filled = filled
            fvg.is_active = not filled

            if not filled:
                active.append(fvg)

        return sorted(active, key=lambda f: f.bar_index, reverse=True)

    def _is_filled(self, fvg: FairValueGap, df: pd.DataFrame, start_idx: int) -> bool:
        """FVG is filled when price trades through the entire gap zone."""
        for i in range(start_idx + 1, len(df)):
            if fvg.fvg_type == FVGType.BULLISH:
                if df["low"].iloc[i] <= fvg.bottom:
                    return True
            else:
                if df["high"].iloc[i] >= fvg.top:
                    return True
        return False

    def price_in_fvg(self, price: float, fvg: FairValueGap, tolerance_pct: float = 0.1) -> bool:
        """Check if current price is within or near the FVG zone."""
        tolerance = fvg.midpoint * (tolerance_pct / 100)
        return (fvg.bottom - tolerance) <= price <= (fvg.top + tolerance)

    def get_nearest_fvg(
        self,
        price: float,
        fvgs: list[FairValueGap],
        fvg_type: FVGType | None = None,
    ) -> FairValueGap | None:
        candidates = [f for f in fvgs if f.is_active and (fvg_type is None or f.fvg_type == fvg_type)]
        if not candidates:
            return None

        def distance(fvg: FairValueGap) -> float:
            if fvg.bottom <= price <= fvg.top:
                return 0
            return min(abs(price - fvg.bottom), abs(price - fvg.top))

        return min(candidates, key=distance)
