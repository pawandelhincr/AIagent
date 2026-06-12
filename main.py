"""
Indian Market FVG Trading Agent - CLI Entry Point

Usage:
  python main.py scan                    # Scan all symbols
  python main.py scan nifty              # Scan Nifty only
  python main.py signal sensex           # Get best Sensex signal
  python main.py fvg nifty               # Show FVG zones
  python main.py server                  # Start API server for app integration
"""

import argparse
import json
import sys

from src.agent.trading_agent import TradingAgent
from src.models import Segment


def print_json(data: dict):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Indian Market FVG Trading Agent")
    sub = parser.add_subparsers(dest="command")

    scan_p = sub.add_parser("scan", help="Scan for FVG signals")
    scan_p.add_argument("symbol", nargs="?", help="Symbol: nifty, sensex, banknifty")
    scan_p.add_argument("--segment", choices=["cash", "options"], default="cash")
    scan_p.add_argument("--timeframe", choices=["5m", "15m", "1h", "1d"], default=None)

    sig_p = sub.add_parser("signal", help="Get best signal")
    sig_p.add_argument("symbol", help="Symbol: nifty, sensex, banknifty")
    sig_p.add_argument("--segment", choices=["cash", "options"], default="cash")
    sig_p.add_argument("--timeframe", choices=["5m", "15m", "1h", "1d"], default=None)

    fvg_p = sub.add_parser("fvg", help="Show FVG zones")
    fvg_p.add_argument("symbol", help="Symbol: nifty, sensex, banknifty")
    fvg_p.add_argument("--timeframe", choices=["5m", "15m", "1h", "1d"], default=None)

    sub.add_parser("server", help="Start REST API server")
    sub.add_parser("config", help="Show configuration")

    dhan_p = sub.add_parser("dhan", help="Dhan broker commands")
    dhan_sub = dhan_p.add_subparsers(dest="dhan_command")
    dhan_sub.add_parser("status", help="Check Dhan connection")
    dhan_sub.add_parser("portfolio", help="Show funds, positions, orders")
    dhan_sub.add_parser("sync", help="Sync capital from Dhan balance")

    exec_p = dhan_sub.add_parser("execute", help="Execute FVG signal on Dhan")
    exec_p.add_argument("symbol", help="Symbol: nifty, sensex, banknifty")
    exec_p.add_argument("--segment", choices=["cash", "options"], default="cash")
    exec_p.add_argument("--live", action="store_true", help="Place live order (default: preview)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "server":
        from src.api.server import run_server
        run_server()
        return

    if args.command == "dhan":
        agent = TradingAgent()
        if args.dhan_command == "status":
            print_json(agent.dhan_status())
        elif args.dhan_command == "portfolio":
            print_json(agent.dhan_portfolio())
        elif args.dhan_command == "sync":
            print_json(agent.sync_capital_from_dhan())
        elif args.dhan_command == "execute":
            print_json(agent.execute_on_dhan(
                args.symbol.lower(),
                Segment(args.segment),
                dry_run=not args.live,
            ))
        else:
            dhan_p.print_help()
        return

    agent = TradingAgent()
    segment = Segment(getattr(args, "segment", "cash"))

    if args.command == "config":
        print_json(agent.get_config_summary())
    elif args.command == "scan":
        if args.symbol:
            print_json(agent.scan_symbol(args.symbol.lower(), segment, args.timeframe))
        else:
            print_json(agent.scan_all(segment=segment, timeframe=args.timeframe))
    elif args.command == "signal":
        print_json(agent.get_signal(args.symbol.lower(), segment, args.timeframe))
    elif args.command == "fvg":
        result = agent.scan_symbol(args.symbol.lower(), Segment.CASH, args.timeframe)
        print_json({
            "symbol": args.symbol,
            "current_price": result["current_price"],
            "fvg_zones": result["fvg_zones"],
        })


if __name__ == "__main__":
    main()


# ==========================================================
# Langfuse & Env Configuration (Main Function se PEHLE)
# ==========================================================
from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()
# Naye SDK ke mutabik 'Langfuse' class ka 'L' capital hota hai
langfuse_client = Langfuse() 

# ==========================================================
# Aapka Application Entry Point
# ==========================================================
if __name__ == "__main__":
    print("Starting Langfuse Tracing for AIagent...")
    
    # 1. Pehle trace create karein (Sahi syntax ke sath)
    trace = langfuse_client.trace(
        name="market-analysis",
        metadata={
            "project_name": "AIagent",   # <-- Comma fix ho gaya
            "environment": "production"
    }
)

# Aapka LLM call aur baki logic yahan aayega...
langfuse.flush()
langfuse_client.flush()
    print("Scan complete. Traces pushed to Langfuse dashboard.")
