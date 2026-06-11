"""Market data from Dhan API."""

from datetime import datetime, timedelta

import pandas as pd

from src.broker.dhan_client import DhanClient
from src.broker.dhan_instruments import DhanInstrumentResolver

TIMEFRAME_TO_INTERVAL = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "25m": 25,
    "1h": 60,
    "60m": 60,
}


class DhanMarketDataFetcher:
    """Fetch OHLCV candles from Dhan historical API."""

    def __init__(self, symbols_config: dict, dhan_client: DhanClient | None = None):
        self.symbols = symbols_config
        self.dhan_client = dhan_client or DhanClient()

    def get_symbol_info(self, symbol_key: str) -> dict:
        if symbol_key not in self.symbols:
            raise ValueError(f"Unknown symbol: {symbol_key}. Available: {list(self.symbols.keys())}")
        info = dict(self.symbols[symbol_key])
        idx = DhanInstrumentResolver.get_index_config(symbol_key)
        info["dhan_security_id"] = idx["security_id"]
        info["dhan_exchange_segment"] = idx["segment"]
        info["dhan_instrument"] = idx["instrument"]
        return info

    def fetch_ohlcv(
        self,
        symbol_key: str,
        timeframe: str = "15m",
        bars: int = 200,
    ) -> pd.DataFrame:
        if not self.dhan_client.is_configured:
            raise RuntimeError("Dhan credentials required for live data. Set .env file.")

        idx = DhanInstrumentResolver.get_index_config(symbol_key)
        interval = TIMEFRAME_TO_INTERVAL.get(timeframe, 15)

        to_date = datetime.now()
        days_back = max(5, (bars * interval) // (60 * 6) + 2)
        from_date = to_date - timedelta(days=days_back)

        resp = self.dhan_client.dhan.intraday_minute_data(
            security_id=idx["security_id"],
            exchange_segment=idx["segment"],
            instrument_type=idx["instrument"],
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M:%S"),
            interval=interval,
        )

        if not resp or resp.get("status") == "failure":
            raise RuntimeError(f"Dhan data error for {symbol_key}: {resp}")

        data = resp.get("data", resp)
        if not data or not data.get("open"):
            raise RuntimeError(f"No candle data returned for {symbol_key}")

        df = pd.DataFrame({
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data.get("volume", [0] * len(data["open"])),
        })
        df.index = pd.to_datetime(data["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata")
        df = df.dropna()

        if len(df) > bars:
            df = df.iloc[-bars:]

        return df

    def get_current_price(self, symbol_key: str) -> float:
        df = self.fetch_ohlcv(symbol_key, timeframe="5m", bars=3)
        return float(df["close"].iloc[-1])
