"""Top3 buy-signal trade simulation.

Policy (fixed, per design spec):
- Each scan day, enter the valid top_n BUY signals at the NEXT trading day's open.
- Stop-loss and target are absolute price levels taken from the report.
- Hold until daily low <= stop (stop wins on same-day tie) or high >= target.
- A ticker already held is not re-entered while its position is open.
- Position size = a FIXED dollar amount per trade (position_size, default $200).
  No leverage, no equal-split of a notional account — each signal simply buys
  position_size worth of shares.
- "Invested capital" = sum of cost basis of every position that was entered.
  Returns are reported relative to invested capital, and as absolute PnL ($).
"""

from typing import Callable, List

import pandas as pd

from src.simulation.price_provider import next_trading_day_open, bars_after


def _valid_buys(buys: List[dict], top_n: int) -> List[dict]:
    valid = [b for b in buys if b.get("stop_loss") is not None and b.get("target") is not None]
    valid.sort(key=lambda b: (b.get("rank") if b.get("rank") is not None else 1e9))
    return valid[:top_n]


def run_simulation(
    scans: List[dict],
    price_fn: Callable[[str], pd.DataFrame],
    position_size: float = 200.0,
    top_n: int = 3,
) -> dict:
    scans = sorted(scans, key=lambda s: s["scan_date"])

    open_positions = {}   # ticker -> dict
    trades = []
    price_cache = {}

    def prices(ticker):
        if ticker not in price_cache:
            price_cache[ticker] = price_fn(ticker)
        return price_cache[ticker]

    for scan in scans:
        for buy in _valid_buys(scan.get("buys", []), top_n):
            ticker = buy["ticker"]
            if ticker in open_positions:
                continue
            df = prices(ticker)
            if df is None or df.empty:
                continue
            entry_day, entry_px = next_trading_day_open(df, scan["scan_date"])
            if entry_day is None or not entry_px:
                continue
            shares = position_size / entry_px
            open_positions[ticker] = {
                "ticker": ticker, "signal_date": scan["scan_date"],
                "entry_date": str(entry_day.date()),
                "entry_price": entry_px, "shares": shares,
                "cost_basis": position_size,
                "stop_loss": buy["stop_loss"], "target": buy["target"],
                "score": buy.get("score"),
            }

    # Resolve each open position against its post-entry bars.
    last_close = {}
    for ticker, pos in list(open_positions.items()):
        df = prices(ticker)
        future = bars_after(df, pos["entry_date"])
        exited = False
        for ts, row in future.iterrows():
            low, high, close = float(row["Low"]), float(row["High"]), float(row["Close"])
            if low != low or high != high or close != close:  # skip NaN bars (partial day)
                continue
            last_close[ticker] = (str(ts.date()), close)
            if low <= pos["stop_loss"]:                # stop wins on tie
                _record_exit(trades, pos, ts, pos["stop_loss"], "stop")
                exited = True
                break
            if high >= pos["target"]:
                _record_exit(trades, pos, ts, pos["target"], "target")
                exited = True
                break
        if exited:
            del open_positions[ticker]

    # Mark remaining open positions to last close.
    open_list = []
    for ticker, pos in open_positions.items():
        marked = last_close.get(ticker, (pos["entry_date"], pos["entry_price"]))
        mark_date, mark = marked
        unreal = (mark - pos["entry_price"]) * pos["shares"]
        unreal_pct = (mark / pos["entry_price"] - 1) * 100
        open_list.append({
            **pos, "status": "open", "mark_date": mark_date, "mark_price": mark,
            "unrealized_pnl": unreal, "unrealized_pnl_pct": unreal_pct,
        })

    invested = sum(t["cost_basis"] for t in trades) + sum(p["cost_basis"] for p in open_list)
    equity_curve = _build_equity_curve(trades, open_list, invested)
    summary = _build_summary(trades, open_list, invested, equity_curve)
    return {
        "trades": trades,
        "open_positions": open_list,
        "equity_curve": equity_curve,
        "summary": summary,
    }


def _record_exit(trades, pos, ts, exit_price, reason):
    pnl = (exit_price - pos["entry_price"]) * pos["shares"]
    pnl_pct = (exit_price / pos["entry_price"] - 1) * 100
    trades.append({
        "ticker": pos["ticker"], "signal_date": pos["signal_date"],
        "entry_date": pos["entry_date"], "entry_price": pos["entry_price"],
        "exit_date": str(ts.date()), "exit_price": exit_price,
        "shares": pos["shares"], "cost_basis": pos["cost_basis"],
        "pnl": pnl, "pnl_pct": pnl_pct,
        "exit_reason": reason, "status": "closed",
        "stop_loss": pos["stop_loss"], "target": pos["target"],
        "score": pos.get("score"),
    })


def _build_equity_curve(trades, open_list, invested):
    # Cumulative PnL over time: realized accrues on each exit_date, with the
    # open-position unrealized PnL added as a final point. "equity" is the
    # running PnL relative to the capital invested so far.
    by_date = {}
    for t in trades:
        by_date.setdefault(t["exit_date"], 0.0)
        by_date[t["exit_date"]] += t["pnl"]
    base = invested if invested else 1.0
    curve, running = [], 0.0
    for date in sorted(by_date):
        running += by_date[date]
        curve.append({
            "date": date, "realized": running, "unrealized": 0.0,
            "pnl": running, "return_pct": running / base * 100,
        })
    unreal_total = sum(p["unrealized_pnl"] for p in open_list)
    if curve:
        last = curve[-1]
        total = running + unreal_total
        curve.append({
            "date": last["date"], "realized": running, "unrealized": unreal_total,
            "pnl": total, "return_pct": total / base * 100,
        })
    elif open_list:
        curve.append({
            "date": open_list[0]["entry_date"], "realized": 0.0,
            "unrealized": unreal_total, "pnl": unreal_total,
            "return_pct": unreal_total / base * 100,
        })
    return curve


def _build_summary(trades, open_list, invested, equity_curve):
    wins = [t for t in trades if t["pnl"] > 0]
    realized = sum(t["pnl"] for t in trades)
    unreal = sum(p["unrealized_pnl"] for p in open_list)
    total_pnl = realized + unreal
    base = invested if invested else 1.0
    # Max drawdown of the cumulative-PnL curve, relative to invested capital.
    peak, mdd = 0.0, 0.0
    for point in equity_curve:
        peak = max(peak, point["pnl"])
        mdd = min(mdd, (point["pnl"] - peak) / base * 100)
    return {
        "invested_capital": invested,
        "realized_pnl": realized,
        "unrealized_pnl": unreal,
        "total_pnl": total_pnl,
        "total_return_pct": total_pnl / base * 100,
        "num_trades": len(trades),
        "num_open": len(open_list),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "avg_pnl": (realized / len(trades)) if trades else 0.0,
        "max_drawdown_pct": mdd,
    }
