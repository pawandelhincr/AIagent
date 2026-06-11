from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Segment(str, Enum):
    CASH = "cash"
    OPTIONS = "options"


class FVGType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass
class FairValueGap:
    fvg_type: FVGType
    top: float
    bottom: float
    midpoint: float
    gap_size: float
    gap_pct: float
    formed_at: datetime
    bar_index: int
    is_filled: bool = False
    is_active: bool = True

    @property
    def zone(self) -> tuple[float, float]:
        return (self.bottom, self.top)


@dataclass
class Target:
    level: int
    price: float
    rr_ratio: float
    quantity_pct: float  # % of position to exit at this target


@dataclass
class TradeSignal:
    symbol: str
    symbol_name: str
    segment: Segment
    signal_type: SignalType
    entry_price: float
    stop_loss: float
    targets: list[Target]
    fvg: FairValueGap
    risk_amount: float
    position_size: int
    lot_size: int
    risk_reward_ratio: float
    confidence: float
    timeframe: str
    generated_at: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "symbol_name": self.symbol_name,
            "segment": self.segment.value,
            "signal": self.signal_type.value,
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "targets": [
                {
                    "level": t.level,
                    "price": round(t.price, 2),
                    "rr_ratio": t.rr_ratio,
                    "quantity_pct": t.quantity_pct,
                }
                for t in self.targets
            ],
            "fvg": {
                "type": self.fvg.fvg_type.value,
                "top": round(self.fvg.top, 2),
                "bottom": round(self.fvg.bottom, 2),
                "midpoint": round(self.fvg.midpoint, 2),
                "gap_pct": round(self.fvg.gap_pct, 4),
            },
            "risk_management": {
                "risk_amount_inr": round(self.risk_amount, 2),
                "position_size": self.position_size,
                "lot_size": self.lot_size,
                "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            },
            "confidence": round(self.confidence, 2),
            "timeframe": self.timeframe,
            "generated_at": self.generated_at.isoformat(),
            "notes": self.notes,
        }


@dataclass
class RiskProfile:
    capital: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_open_trades: int
    max_trades_per_day: int
    daily_pnl: float = 0.0
    open_trades: int = 0
    trades_today: int = 0

    @property
    def risk_per_trade(self) -> float:
        return self.capital * (self.risk_per_trade_pct / 100)

    @property
    def max_daily_loss(self) -> float:
        return self.capital * (self.max_daily_loss_pct / 100)

    @property
    def can_trade(self) -> bool:
        if abs(self.daily_pnl) >= self.max_daily_loss and self.daily_pnl < 0:
            return False
        if self.open_trades >= self.max_open_trades:
            return False
        if self.trades_today >= self.max_trades_per_day:
            return False
        return True

    @property
    def block_reason(self) -> Optional[str]:
        if abs(self.daily_pnl) >= self.max_daily_loss and self.daily_pnl < 0:
            return f"Daily loss limit reached ({self.max_daily_loss_pct}%)"
        if self.open_trades >= self.max_open_trades:
            return f"Max open trades reached ({self.max_open_trades})"
        if self.trades_today >= self.max_trades_per_day:
            return f"Max trades per day reached ({self.max_trades_per_day})"
        return None
