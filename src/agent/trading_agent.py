from datetime import datetime

from src.analysis.fvg_detector import FVGDetector
from src.broker.dhan_client import DhanClient
from src.broker.dhan_orders import DhanOrderExecutor
from src.config_loader import load_config
from src.data.market_data import MarketDataFetcher
from src.models import FVGType, FairValueGap, RiskProfile, Segment, SignalType, Target, TradeSignal
from src.risk.risk_manager import RiskManager
from src.signals.signal_generator import SignalGenerator


class TradingAgent:
    """
    Main FVG Trading Agent for Indian Markets (Nifty, Sensex, Bank Nifty).

    Scans cash & options segments, detects Fair Value Gaps,
    generates BUY/SELL signals with stop loss, targets, and position sizing.
    Integrates with Dhan broker for live data and order execution.
    """

    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)

        dhan_cfg = self.config.get("dhan", {})
        data_source = dhan_cfg.get("data_source", "auto")
        self.data_fetcher = MarketDataFetcher(self.config["symbols"], data_source)

        self.dhan_client = DhanClient()
        self.dhan_executor: DhanOrderExecutor | None = None
        if dhan_cfg.get("enabled", True) and self.dhan_client.is_configured:
            self.dhan_executor = DhanOrderExecutor(
                self.dhan_client,
                product_type=dhan_cfg.get("product_type", "INTRADAY"),
            )

        self.fvg_detector = FVGDetector(
            min_gap_pct=self.config["fvg"]["min_gap_pct"],
            max_gap_age_bars=self.config["fvg"]["max_gap_age_bars"],
        )

        acct = self.config["account"]
        self.risk_profile = RiskProfile(
            capital=acct["capital"],
            risk_per_trade_pct=acct["risk_per_trade_pct"],
            max_daily_loss_pct=acct["max_daily_loss_pct"],
            max_open_trades=acct["max_open_trades"],
            max_trades_per_day=acct["max_trades_per_day"],
        )
        self.risk_manager = RiskManager(self.risk_profile, self.config["risk_reward"])
        self.signal_generator = SignalGenerator(self.fvg_detector, self.risk_manager)

        self.default_timeframe = self.config["fvg"]["timeframe"]
        self.lookback_bars = self.config["fvg"]["lookback_bars"]
        self.dhan_config = dhan_cfg

    def scan_symbol(
        self,
        symbol_key: str,
        segment: Segment = Segment.CASH,
        timeframe: str | None = None,
    ) -> dict:
        tf = timeframe or self.default_timeframe
        info = self.data_fetcher.get_symbol_info(symbol_key)

        df = self.data_fetcher.fetch_ohlcv(symbol_key, tf, self.lookback_bars)
        current_price = float(df["close"].iloc[-1])

        signals = self.signal_generator.analyze(
            df=df,
            symbol_key=symbol_key,
            symbol_name=info["name"],
            lot_size=info["lot_size"],
            segment=segment,
            timeframe=tf,
        )

        fvg_zones = self.signal_generator.get_fvg_zones(df, symbol_key)

        return {
            "symbol": symbol_key,
            "symbol_name": info["name"],
            "segment": segment.value,
            "timeframe": tf,
            "data_source": self.data_fetcher.active_source,
            "current_price": round(current_price, 2),
            "market_open": MarketDataFetcher.is_market_open(),
            "signals": [s.to_dict() for s in signals],
            "fvg_zones": fvg_zones,
            "risk_summary": self.risk_manager.get_risk_summary(),
            "dhan_connected": self.dhan_client.is_configured,
            "scanned_at": datetime.now().isoformat(),
        }

    def scan_all(
        self,
        symbols: list[str] | None = None,
        segment: Segment = Segment.CASH,
        timeframe: str | None = None,
    ) -> dict:
        if symbols is None:
            symbols = list(self.config["symbols"].keys())

        results = []
        all_signals = []

        for sym in symbols:
            try:
                result = self.scan_symbol(sym, segment, timeframe)
                results.append(result)
                all_signals.extend(result["signals"])
            except Exception as e:
                results.append({"symbol": sym, "error": str(e)})

        return {
            "scan_results": results,
            "total_signals": len(all_signals),
            "data_source": self.data_fetcher.active_source,
            "dhan_connected": self.dhan_client.is_configured,
            "risk_summary": self.risk_manager.get_risk_summary(),
            "scanned_at": datetime.now().isoformat(),
        }

    def get_signal(
        self,
        symbol_key: str,
        segment: Segment = Segment.CASH,
        timeframe: str | None = None,
    ) -> dict | None:
        result = self.scan_symbol(symbol_key, segment, timeframe)
        signals = result.get("signals", [])
        if not signals:
            return {
                "symbol": symbol_key,
                "signal": None,
                "message": "No active FVG signal at current price",
                "fvg_zones": result.get("fvg_zones", []),
                "current_price": result.get("current_price"),
            }
        return signals[0]

    def execute_on_dhan(
        self,
        symbol_key: str,
        segment: Segment = Segment.CASH,
        timeframe: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        if not self.dhan_executor:
            return {
                "status": "error",
                "message": "Dhan not connected. Add DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN to .env",
            }

        result = self.scan_symbol(symbol_key, segment, timeframe)
        signal_dicts = result.get("signals", [])
        if not signal_dicts:
            return {
                "status": "no_signal",
                "message": "No active FVG signal to execute",
                "fvg_zones": result.get("fvg_zones", []),
            }

        best = signal_dicts[0]
        signal = TradeSignal(
            symbol=best["symbol"],
            symbol_name=best["symbol_name"],
            segment=Segment(best["segment"]),
            signal_type=SignalType(best["signal"]),
            entry_price=best["entry_price"],
            stop_loss=best["stop_loss"],
            targets=[
                Target(
                    level=t["level"], price=t["price"],
                    rr_ratio=t["rr_ratio"], quantity_pct=t["quantity_pct"],
                )
                for t in best["targets"]
            ],
            fvg=FairValueGap(
                fvg_type=FVGType(best["fvg"]["type"]),
                top=best["fvg"]["top"],
                bottom=best["fvg"]["bottom"],
                midpoint=best["fvg"]["midpoint"],
                gap_size=0,
                gap_pct=best["fvg"]["gap_pct"],
                formed_at=datetime.now(),
                bar_index=0,
            ),
            risk_amount=best["risk_management"]["risk_amount_inr"],
            position_size=best["risk_management"]["position_size"],
            lot_size=best["risk_management"]["lot_size"],
            risk_reward_ratio=best["risk_management"]["risk_reward_ratio"],
            confidence=best["confidence"],
            timeframe=best["timeframe"],
            notes=best.get("notes", ""),
        )

        return self.dhan_executor.execute_signal(
            signal=signal,
            spot_price=result["current_price"],
            dry_run=dry_run,
            use_super_order=self.dhan_config.get("use_super_order", True),
        )

    def dhan_status(self) -> dict:
        if not self.dhan_client.is_configured:
            return {"connected": False, "message": "Credentials not set in .env"}
        status = self.dhan_client.test_connection()
        status["data_source"] = self.data_fetcher.active_source
        return status

    def dhan_portfolio(self) -> dict:
        if not self.dhan_executor:
            return {"error": "Dhan not connected"}
        return {
            "funds": self.dhan_executor.get_funds(),
            "positions": self.dhan_executor.get_positions(),
            "orders": self.dhan_executor.get_orders(),
        }

    def sync_capital_from_dhan(self) -> dict:
        if not self.dhan_executor:
            return {"error": "Dhan not connected"}
        funds = self.dhan_executor.get_funds()
        data = funds.get("data", funds)
        available = float(data.get("availabelBalance", data.get("availableBalance", 0)))
        if available > 0:
            self.update_capital(available)
        return {"capital_updated": available, "funds": funds}

    def update_risk_state(
        self,
        daily_pnl: float | None = None,
        open_trades: int | None = None,
        trades_today: int | None = None,
    ):
        if daily_pnl is not None:
            self.risk_profile.daily_pnl = daily_pnl
        if open_trades is not None:
            self.risk_profile.open_trades = open_trades
        if trades_today is not None:
            self.risk_profile.trades_today = trades_today

    def update_capital(self, capital: float):
        self.risk_profile.capital = capital

    def get_config_summary(self) -> dict:
        return {
            "symbols": list(self.config["symbols"].keys()),
            "default_timeframe": self.default_timeframe,
            "data_source": self.data_fetcher.active_source,
            "dhan_connected": self.dhan_client.is_configured,
            "risk": self.risk_manager.get_risk_summary(),
            "fvg_settings": self.config["fvg"],
            "dhan_settings": self.dhan_config,
        }
