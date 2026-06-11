# Indian Market FVG Trading Agent

Nifty, Sensex aur Bank Nifty ke liye **Fair Value Gap (FVG)** based trading agent.  
Cash aur Options dono segments ke liye **BUY/SELL signals**, **Stop Loss**, **Targets**, aur **Risk Management** provide karta hai.

## Features

- **FVG Detection** — Bullish/Bearish Fair Value Gaps automatically detect
- **Buy/Sell Signals** — Entry, Stop Loss, 3 Targets (1.5R, 2.5R, 4R)
- **Risk Management** — Position sizing, daily loss limit, max trades
- **REST API** — Apni trading app se integrate karne ke liye
- **Nifty, Sensex, Bank Nifty** — Sab major indices support

## Quick Start

```bash
# Dependencies install karein
pip install -r requirements.txt

# Sab symbols scan karein
python main.py scan

# Sirf Nifty ka signal
python main.py signal nifty

# FVG zones dekhein
python main.py fvg sensex

# API server start (trading app integration)
python main.py server
```

API docs: `http://localhost:8000/docs`

## Configuration

`config.yaml` mein settings change karein:

| Setting | Default | Description |
|---------|---------|-------------|
| `account.capital` | 5,00,000 | Trading capital (INR) |
| `account.risk_per_trade_pct` | 1% | Har trade par max risk |
| `account.max_daily_loss_pct` | 3% | Daily loss limit |
| `fvg.timeframe` | 15m | Chart timeframe |
| `fvg.min_gap_pct` | 0.05% | Minimum FVG size |

## API Endpoints (Trading App Integration)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/scan` | Sab symbols scan |
| GET | `/scan/{symbol}` | Single symbol scan |
| GET | `/signal/{symbol}` | Best BUY/SELL signal |
| GET | `/fvg/{symbol}` | Active FVG zones |
| POST | `/risk/update` | Daily P&L, open trades update |
| POST | `/risk/capital` | Capital update |

### Example: Signal fetch karna

```bash
curl http://localhost:8000/signal/nifty?segment=cash&timeframe=15m
```

### Example Response

```json
{
  "symbol": "nifty",
  "signal": "BUY",
  "entry_price": 24150.50,
  "stop_loss": 24120.00,
  "targets": [
    {"level": 1, "price": 24196.25, "rr_ratio": 1.5, "quantity_pct": 40},
    {"level": 2, "price": 24226.75, "rr_ratio": 2.5, "quantity_pct": 35},
    {"level": 3, "price": 24272.50, "rr_ratio": 4.0, "quantity_pct": 25}
  ],
  "risk_management": {
    "risk_amount_inr": 5000,
    "position_size": 25,
    "lot_size": 25
  }
}
```

### Trading App se Risk Update

```bash
curl -X POST http://localhost:8000/risk/update \
  -H "Content-Type: application/json" \
  -d '{"daily_pnl": -8000, "open_trades": 2, "trades_today": 3}'
```

## FVG Strategy Logic

**Fair Value Gap (FVG)** ek price imbalance zone hai jahan market tezi se move karti hai:

- **Bullish FVG**: Candle 1 ka high < Candle 3 ka low → Price wapas gap mein aaye to **BUY**
- **Bearish FVG**: Candle 1 ka low > Candle 3 ka high → Price gap mein aaye to **SELL**

**Stop Loss**: FVG zone ke bahar (buffer ke saath)  
**Targets**: Risk ke multiples — 1.5R, 2.5R, 4R

## Project Structure

```
Option Trader/
├── config.yaml          # Settings
├── main.py              # CLI entry
├── requirements.txt
└── src/
    ├── agent/           # Main trading agent
    ├── analysis/        # FVG detector
    ├── api/             # REST API server
    ├── data/            # Market data fetcher
    ├── risk/            # Risk manager
    └── signals/         # Signal generator
```

## Dhan Broker Integration

### Step 1: API Token lo

1. [web.dhan.co](https://web.dhan.co) par login karo
2. **My Profile** → **Access DhanHQ APIs**
3. **Client ID** aur **Access Token** copy karo

### Step 2: `.env` file banao

```bash
copy .env.example .env
```

`.env` mein credentials daalo:

```
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
```

### Step 3: Commands

```bash
# Connection check
py main.py dhan status

# Portfolio dekho
py main.py dhan portfolio

# Capital sync (Dhan balance se risk capital update)
py main.py dhan sync

# Signal preview (order nahi lagega)
py main.py dhan execute nifty

# Live order (Static IP whitelist chahiye Dhan par)
py main.py dhan execute nifty --live
```

### Dhan API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dhan/status` | Connection check |
| GET | `/dhan/portfolio` | Funds, positions, orders |
| POST | `/dhan/sync-capital` | Capital sync from Dhan |
| POST | `/dhan/execute/{symbol}?dry_run=true` | Preview trade |
| POST | `/dhan/execute/{symbol}?dry_run=false` | Live trade |

### Segment mapping on Dhan

| Segment | Dhan par kya trade hoga |
|---------|-------------------------|
| **cash** | Index Future (nearest expiry, INTRADAY) |
| **options** | ATM CE (BUY signal) / ATM PE (SELL signal) |

Orders **Super Order** se jaate hain — entry + stop loss + target ek saath.

> **Note:** Live orders ke liye Dhan par **Static IP whitelisting** zaroori hai. Preview/dry_run bina iske chal sakta hai.

## Disclaimer

Yeh tool sirf analysis aur signal generation ke liye hai. Trading mein risk hota hai.  
Apne broker ke saath integrate karne se pehle paper trading se test karein.
