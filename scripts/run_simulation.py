#!/usr/bin/env python3
"""Run the Top3 trade simulation over all committed scan JSON files.

Reads data/daily_scans/scan_*.json, fetches prices via yfinance, and writes
trades/equity/open-positions/summary JSON to data/simulation/.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.simulation.engine import run_simulation
from src.simulation.price_provider import get_history

SCAN_DIR = Path("data/daily_scans")
OUT_DIR = Path("data/simulation")


def load_scans():
    scans = []
    for path in sorted(SCAN_DIR.glob("scan_*.json")):
        data = json.loads(path.read_text())
        if data.get("scan_date"):
            scans.append(data)
    return scans


def main():
    parser = argparse.ArgumentParser(description="Top3 trade simulation")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    scans = load_scans()
    if not scans:
        print("No scan JSON found in data/daily_scans/ — nothing to simulate.")
        return

    start = min(s["scan_date"] for s in scans)
    start_dt = (datetime.fromisoformat(start) - timedelta(days=5)).strftime("%Y-%m-%d")
    print(f"Simulating {len(scans)} scan days from {start} (price history from {start_dt})")

    def price_fn(ticker):
        try:
            return get_history(ticker, start=start_dt)
        except Exception as exc:  # network/delisting/etc.
            print(f"  ⚠ price fetch failed for {ticker}: {exc}")
            import pandas as pd
            return pd.DataFrame()

    result = run_simulation(
        scans, price_fn,
        initial_capital=args.initial_capital, top_n=args.top_n,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "trades.json").write_text(json.dumps(result["trades"], indent=2))
    (OUT_DIR / "equity_curve.json").write_text(json.dumps(result["equity_curve"], indent=2))
    (OUT_DIR / "open_positions.json").write_text(json.dumps(result["open_positions"], indent=2))
    (OUT_DIR / "summary.json").write_text(json.dumps(result["summary"], indent=2))

    s = result["summary"]
    print(f"✓ Trades: {s['num_trades']} | Open: {s['num_open']} | "
          f"Win rate: {s['win_rate']:.1f}% | Return: {s['total_return_pct']:.2f}% | "
          f"MDD: {s['max_drawdown_pct']:.2f}%")


if __name__ == "__main__":
    main()
