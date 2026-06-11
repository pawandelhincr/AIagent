"""Resolve Dhan security IDs for indices, futures and options."""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime
from typing import Any

INSTRUMENT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

# Index security IDs for chart data (IDX_I segment)
INDEX_IDS = {
    "nifty": {"security_id": "13", "exchange": "NSE", "segment": "IDX_I", "instrument": "INDEX"},
    "banknifty": {"security_id": "25", "exchange": "NSE", "segment": "IDX_I", "instrument": "INDEX"},
    "sensex": {"security_id": "51", "exchange": "BSE", "segment": "IDX_I", "instrument": "INDEX"},
}

FNO_EXCHANGE = {
    "nifty": "NSE_FNO",
    "banknifty": "NSE_FNO",
    "sensex": "BSE_FNO",
}


class DhanInstrumentResolver:
    """Find tradable security IDs from Dhan instrument master."""

    _cache: list[dict[str, str]] | None = None

    @classmethod
    def _load_master(cls) -> list[dict[str, str]]:
        if cls._cache is not None:
            return cls._cache
        raw = urllib.request.urlopen(INSTRUMENT_CSV_URL, timeout=60).read()
        text = raw.decode("utf-8", errors="ignore")
        cls._cache = list(csv.DictReader(io.StringIO(text)))
        return cls._cache

    @classmethod
    def get_index_config(cls, symbol_key: str) -> dict[str, str]:
        if symbol_key not in INDEX_IDS:
            raise ValueError(f"No Dhan index mapping for: {symbol_key}")
        return INDEX_IDS[symbol_key]

    @classmethod
    def get_nearest_future(cls, symbol_key: str) -> dict[str, Any]:
        """Nearest index future for cash-segment (intraday) trading."""
        underlying = INDEX_IDS.get(symbol_key)
        if not underlying:
            raise ValueError(f"Unknown symbol: {symbol_key}")

        uid = underlying["security_id"]
        exchange = underlying["exchange"]
        today = datetime.now().date()

        candidates = []
        for row in cls._load_master():
            if row.get("EXCH_ID") != exchange:
                continue
            if row.get("SEGMENT") != "D":
                continue
            if row.get("INSTRUMENT") != "FUTIDX":
                continue
            if row.get("UNDERLYING_SECURITY_ID") != uid:
                continue
            expiry_str = row.get("SM_EXPIRY_DATE", "")
            if not expiry_str:
                continue
            try:
                expiry = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if expiry >= today:
                sid = row.get("SECURITY_ID") or row.get("SEM_SMST_SECURITY_ID", "")
                candidates.append({
                    "security_id": str(sid),
                    "symbol_name": row.get("SYMBOL_NAME", ""),
                    "display_name": row.get("DISPLAY_NAME", ""),
                    "expiry": expiry_str[:10],
                    "lot_size": int(float(row.get("LOT_SIZE", 1))),
                    "exchange_segment": FNO_EXCHANGE[symbol_key],
                    "instrument": "FUTIDX",
                })

        if not candidates:
            raise RuntimeError(f"No active future found for {symbol_key}")

        candidates.sort(key=lambda x: x["expiry"])
        return candidates[0]

    @classmethod
    def get_atm_option(
        cls,
        symbol_key: str,
        spot_price: float,
        option_type: str,
        dhan_client=None,
    ) -> dict[str, Any]:
        """
        Get ATM option contract via Dhan option chain API.
        option_type: CE or PE
        """
        if dhan_client is None:
            from src.broker.dhan_client import DhanClient
            dhan_client = DhanClient()

        idx = cls.get_index_config(symbol_key)
        under_seg = "IDX_I"

        expiries_resp = dhan_client.dhan.expiry_list(idx["security_id"], under_seg)
        if not expiries_resp or not expiries_resp.get("data"):
            raise RuntimeError(f"Could not fetch expiries for {symbol_key}")

        expiry_list = expiries_resp["data"]
        nearest_expiry = expiry_list[0] if isinstance(expiry_list, list) else expiry_list

        chain_resp = dhan_client.dhan.option_chain(
            int(idx["security_id"]),
            under_seg,
            nearest_expiry,
        )
        if not chain_resp or not chain_resp.get("data"):
            raise RuntimeError(f"Could not fetch option chain for {symbol_key}")

        options = chain_resp["data"]
        if isinstance(options, dict):
            options = options.get("oc", options.get("data", []))

        best = None
        best_dist = float("inf")
        opt_type = option_type.upper()

        for item in options:
            if isinstance(item, dict):
                ce_pe = item.get("ce") if opt_type == "CE" else item.get("pe")
                strike = item.get("strikePrice") or item.get("strike")
                if ce_pe and strike is not None:
                    dist = abs(float(strike) - spot_price)
                    if dist < best_dist and ce_pe.get("security_id"):
                        best_dist = dist
                        best = {
                            "security_id": str(ce_pe["security_id"]),
                            "strike": float(strike),
                            "option_type": opt_type,
                            "expiry": nearest_expiry,
                            "lot_size": ce_pe.get("lot_size") or INDEX_IDS[symbol_key].get("lot_size", 25),
                            "exchange_segment": FNO_EXCHANGE[symbol_key],
                            "instrument": "OPTIDX",
                            "display_name": ce_pe.get("trading_symbol", f"{symbol_key} {strike} {opt_type}"),
                        }

        if not best:
            raise RuntimeError(f"No ATM {opt_type} option found for {symbol_key}")

        return best
