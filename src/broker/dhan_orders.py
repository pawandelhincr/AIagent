"""Execute FVG signals on Dhan with SL and targets."""

from __future__ import annotations

import uuid
from typing import Any

from src.broker.dhan_client import DhanClient
from src.broker.dhan_instruments import DhanInstrumentResolver
from src.models import Segment, SignalType, TradeSignal


class DhanOrderExecutor:
    """
    Place trades on Dhan based on FVG signals.

    Cash segment  -> Index Futures (INTRADAY) via Super Order
    Options segment -> ATM CE/PE via Super Order
    """

    def __init__(self, dhan_client: DhanClient | None = None, product_type: str = "INTRADAY"):
        self.client = dhan_client or DhanClient()
        self.product_type = product_type  # INTRADAY or MARGIN

    def _resolve_instrument(
        self,
        signal: TradeSignal,
        spot_price: float,
    ) -> dict[str, Any]:
        if signal.segment == Segment.OPTIONS:
            opt_type = "CE" if signal.signal_type == SignalType.BUY else "PE"
            return DhanInstrumentResolver.get_atm_option(
                signal.symbol, spot_price, opt_type, self.client
            )
        return DhanInstrumentResolver.get_nearest_future(signal.symbol)

    def execute_signal(
        self,
        signal: TradeSignal,
        spot_price: float,
        dry_run: bool = True,
        use_super_order: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a trade signal on Dhan.

        dry_run=True  -> preview only, no order placed
        dry_run=False -> live order (requires Static IP whitelist on Dhan)
        """
        instrument = self._resolve_instrument(signal, spot_price)
        qty = signal.position_size
        if signal.segment == Segment.CASH:
            lot = instrument["lot_size"]
            qty = max(lot, (qty // lot) * lot)

        txn = self.client.dhan.BUY if signal.signal_type == SignalType.BUY else self.client.dhan.SELL
        exchange = instrument["exchange_segment"]
        tag = f"fvg-{signal.symbol}-{uuid.uuid4().hex[:8]}"

        target1 = signal.targets[0].price if signal.targets else signal.entry_price
        preview = {
            "dry_run": dry_run,
            "symbol": signal.symbol,
            "segment": signal.segment.value,
            "signal": signal.signal_type.value,
            "instrument": instrument,
            "quantity": qty,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target": target1,
            "correlation_id": tag,
            "product_type": self.product_type,
        }

        if dry_run:
            preview["message"] = "Preview only. Set dry_run=false to place live order."
            return preview

        dhan = self.client.dhan
        try:
            if use_super_order:
                resp = dhan.place_super_order(
                    security_id=instrument["security_id"],
                    exchange_segment=exchange,
                    transaction_type=txn,
                    quantity=qty,
                    order_type=dhan.MARKET,
                    product_type=dhan.INTRA if self.product_type == "INTRADAY" else dhan.MARGIN,
                    price=0,
                    targetPrice=round(target1, 2),
                    stopLossPrice=round(signal.stop_loss, 2),
                    trailingJump=0,
                    tag=tag,
                )
            else:
                resp = dhan.place_order(
                    security_id=instrument["security_id"],
                    exchange_segment=exchange,
                    transaction_type=txn,
                    quantity=qty,
                    order_type=dhan.MARKET,
                    product_type=dhan.INTRA if self.product_type == "INTRADAY" else dhan.MARGIN,
                    price=0,
                    tag=tag,
                )
            preview["order_response"] = resp
            preview["status"] = "placed"
        except Exception as e:
            preview["status"] = "failed"
            preview["error"] = str(e)

        return preview

    def get_positions(self) -> dict:
        return self.client.dhan.get_positions()

    def get_funds(self) -> dict:
        return self.client.dhan.get_fund_limits()

    def get_orders(self) -> dict:
        return self.client.dhan.get_order_list()

    def cancel_order(self, order_id: str) -> dict:
        return self.client.dhan.cancel_order(order_id)
