from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.broker.dhan_client import DhanClient
from src.broker.dhan_data import DhanMarketDataFetcher

TIMEFRAME_MAP = {
    "1m": ("1m", "7d"),
    "5m": ("5m", "60d"),
    "15m": ("15m", "60d"),
    "1h": ("1h", "730d"),
    "1d": ("1d", "2y"),
}


class YahooMarketDataFetcher:
    """Fetch OHLCV data for Indian indices via Yahoo Finance."""

    def __init__(self, symbols_config: dict):
        self.symbols = symbols_config

    def get_symbol_info(self, symbol_key: str) -> dict:
        if symbol_key not in self.symbols:
            raise ValueError(f"Unknown symbol: {symbol_key}. Available: {list(self.symbols.keys())}")
        return self.symbols[symbol_key]

    def fetch_ohlcv(
        self,
        symbol_key: str,
        timeframe: str = "15m",
        bars: int = 200,
    ) -> pd.DataFrame:
        info = self.get_symbol_info(symbol_key)
        yahoo_symbol = info["yahoo_symbol"]

        interval, period = TIMEFRAME_MAP.get(timeframe, ("15m", "60d"))

        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise RuntimeError(f"No data returned for {symbol_key} ({yahoo_symbol})")

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df.index = pd.to_datetime(df.index)

        if len(df) > bars:
            df = df.iloc[-bars:]

        return df

    def get_current_price(self, symbol_key: str) -> float:
        df = self.fetch_ohlcv(symbol_key, timeframe="1m", bars=5)
        return float(df["close"].iloc[-1])


class MarketDataFetcher:
    """
    Unified market data: Dhan (live) when credentials set, else Yahoo Finance fallback.
    """

    def __init__(self, symbols_config: dict, data_source: str = "auto"):
        self.symbols = symbols_config
        self.data_source = data_source
        self.dhan_client = DhanClient()
        self._yahoo = YahooMarketDataFetcher(symbols_config)
        self._dhan: DhanMarketDataFetcher | None = None

    @property
    def active_source(self) -> str:
        if self.data_source == "yahoo":
            return "yahoo"
        if self.data_source == "dhan":
            return "dhan"
        return "dhan" if self.dhan_client.is_configured else "yahoo"

    def _get_fetcher(self):
        if self.active_source == "dhan":
            if self._dhan is None:
                self._dhan = DhanMarketDataFetcher(self.symbols, self.dhan_client)
            return self._dhan
        return self._yahoo

    def get_symbol_info(self, symbol_key: str) -> dict:
        return self._get_fetcher().get_symbol_info(symbol_key)

    def fetch_ohlcv(self, symbol_key: str, timeframe: str = "15m", bars: int = 200) -> pd.DataFrame:
        return self._get_fetcher().fetch_ohlcv(symbol_key, timeframe, bars)

    def get_current_price(self, symbol_key: str) -> float:
        return self._get_fetcher().get_current_price(symbol_key)

    def fetch_all_symbols(
        self,
        symbol_keys: list[str],
        timeframe: str = "15m",
        bars: int = 200,
    ) -> dict[str, pd.DataFrame]:
        result = {}
        for key in symbol_keys:
            try:
                result[key] = self.fetch_ohlcv(key, timeframe, bars)
            except Exception as e:
                print(f"Warning: Failed to fetch {key}: {e}")
        return result

    @staticmethod
    def is_market_open() -> bool:
        """Check if Indian market is likely open (Mon-Fri 9:15-15:30 IST)."""
        now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close
