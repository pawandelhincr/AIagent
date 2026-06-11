"""
REST API for Trading App Integration.

Endpoints:
  GET  /health              - Health check
  GET  /config              - Agent configuration
  GET  /scan                - Scan all symbols
  GET  /scan/{symbol}       - Scan single symbol
  GET  /signal/{symbol}     - Best signal for symbol
  GET  /fvg/{symbol}        - Active FVG zones
  POST /risk/update         - Update risk state from trading app
  POST /risk/capital        - Update capital
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.agent.trading_agent import TradingAgent
from src.config_loader import load_config
from src.models import Segment

app = FastAPI(
    title="Indian Market FVG Trading Agent",
    description="Fair Value Gap based BUY/SELL signals for Nifty & Sensex with risk management",
    version="1.0.0",
)

agent = TradingAgent()
config = load_config()


class RiskUpdateRequest(BaseModel):
    daily_pnl: Optional[float] = None
    open_trades: Optional[int] = None
    trades_today: Optional[int] = None


class CapitalUpdateRequest(BaseModel):
    capital: float = Field(gt=0, description="Trading capital in INR")


@app.get("/health")
def health():
    return {"status": "ok", "agent": "FVG Trading Agent", "version": "1.0.0"}


@app.get("/config")
def get_config():
    return agent.get_config_summary()


@app.get("/scan")
def scan_all(
    segment: str = Query("cash", enum=["cash", "options"]),
    timeframe: Optional[str] = Query(None, enum=["5m", "15m", "1h", "1d"]),
    symbols: Optional[str] = Query(None, description="Comma-separated: nifty,sensex"),
):
    sym_list = symbols.split(",") if symbols else None
    return agent.scan_all(sym_list, Segment(segment), timeframe)


@app.get("/scan/{symbol}")
def scan_symbol(
    symbol: str,
    segment: str = Query("cash", enum=["cash", "options"]),
    timeframe: Optional[str] = Query(None, enum=["5m", "15m", "1h", "1d"]),
):
    try:
        return agent.scan_symbol(symbol.lower(), Segment(segment), timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signal/{symbol}")
def get_signal(
    symbol: str,
    segment: str = Query("cash", enum=["cash", "options"]),
    timeframe: Optional[str] = Query(None, enum=["5m", "15m", "1h", "1d"]),
):
    try:
        return agent.get_signal(symbol.lower(), Segment(segment), timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fvg/{symbol}")
def get_fvg_zones(
    symbol: str,
    timeframe: Optional[str] = Query(None, enum=["5m", "15m", "1h", "1d"]),
):
    try:
        result = agent.scan_symbol(symbol.lower(), Segment.CASH, timeframe)
        return {
            "symbol": symbol,
            "current_price": result["current_price"],
            "fvg_zones": result["fvg_zones"],
            "timeframe": result["timeframe"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/risk/update")
def update_risk(req: RiskUpdateRequest):
    agent.update_risk_state(req.daily_pnl, req.open_trades, req.trades_today)
    return {"status": "updated", "risk": agent.risk_manager.get_risk_summary()}


@app.post("/risk/capital")
def update_capital(req: CapitalUpdateRequest):
    agent.update_capital(req.capital)
    return {"status": "updated", "capital": req.capital}


# --- Dhan Broker Integration ---

@app.get("/dhan/status")
def dhan_status():
    return agent.dhan_status()


@app.get("/dhan/portfolio")
def dhan_portfolio():
    return agent.dhan_portfolio()


@app.post("/dhan/sync-capital")
def dhan_sync_capital():
    return agent.sync_capital_from_dhan()


@app.post("/dhan/execute/{symbol}")
def dhan_execute(
    symbol: str,
    segment: str = Query("cash", enum=["cash", "options"]),
    timeframe: Optional[str] = Query(None, enum=["5m", "15m", "1h", "1d"]),
    dry_run: bool = Query(True, description="True=preview only, False=live order"),
):
    try:
        return agent.execute_on_dhan(symbol.lower(), Segment(segment), timeframe, dry_run)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def run_server():
    import uvicorn
    host = config["api"]["host"]
    port = config["api"]["port"]
    uvicorn.run("src.api.server:app", host=host, port=port, reload=False)
