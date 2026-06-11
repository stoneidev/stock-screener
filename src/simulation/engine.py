"""Top3 buy-signal trade simulation.

Policy (fixed, per design spec):
- Each scan day, enter the valid top_n BUY signals at the NEXT trading day's open.
- Stop-loss and target are absolute price levels taken from the report.
- Hold until daily low <= stop (stop wins on same-day tie) or high >= target.
- A ticker already held is not re-entered while its position is open.
- Position size = initial_capital / top_n (fixed dollar amount per trade).
- Equity = initial_capital + cumulative realized PnL + open-position unrealized PnL.
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
    initial_capital: float = 100_000.0,
    top_n: int = 3,
) -> dict:
    scans = sorted(scans, key=lambda s: s["scan_date"])
    position_dollars = initial_capital / top_n

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
            shares = position_dollars / entry_px
            open_positions[ticker] = {
                "ticker": ticker, "signal_date": scan["scan_date"],
                "entry_date": str(entry_day.date()),
                "entry_price": entry_px, "shares": shares,
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

    equity_curve = _build_equity_curve(trades, open_list, initial_capital)
    summary = _build_summary(trades, open_list, initial_capital, equity_curve)
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
        "shares": pos["shares"], "pnl": pnl, "pnl_pct": pnl_pct,
        "exit_reason": reason, "status": "closed",
        "stop_loss": pos["stop_loss"], "target": pos["target"],
        "score": pos.get("score"),
    })


def _build_equity_curve(trades, open_list, initial_capital):
    # Realized PnL accrues on exit_date; unrealized is added as a flat final point.
    by_date = {}
    for t in trades:
        by_date.setdefault(t["exit_date"], 0.0)
        by_date[t["exit_date"]] += t["pnl"]
    curve, running = [], 0.0
    for date in sorted(by_date):
        running += by_date[date]
        equity = initial_capital + running
        curve.append({
            "date": date, "realized": running, "unrealized": 0.0,
            "equity": equity, "return_pct": (equity / initial_capital - 1) * 100,
        })
    unreal_total = sum(p["unrealized_pnl"] for p in open_list)
    if curve:
        last = curve[-1]
        equity = initial_capital + running + unreal_total
        curve.append({
            "date": last["date"], "realized": running, "unrealized": unreal_total,
            "equity": equity, "return_pct": (equity / initial_capital - 1) * 100,
        })
    elif open_list:
        equity = initial_capital + unreal_total
        curve.append({
            "date": open_list[0]["entry_date"], "realized": 0.0,
            "unrealized": unreal_total, "equity": equity,
            "return_pct": (equity / initial_capital - 1) * 100,
        })
    return curve


def _build_summary(trades, open_list, initial_capital, equity_curve):
    wins = [t for t in trades if t["pnl"] > 0]
    realized = sum(t["pnl"] for t in trades)
    unreal = sum(p["unrealized_pnl"] for p in open_list)
    equity = initial_capital + realized + unreal
    peak, mdd = initial_capital, 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        mdd = min(mdd, (point["equity"] / peak - 1) * 100)
    return {
        "initial_capital": initial_capital,
        "final_equity": equity,
        "total_return_pct": (equity / initial_capital - 1) * 100,
        "num_trades": len(trades),
        "num_open": len(open_list),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "avg_pnl": (realized / len(trades)) if trades else 0.0,
        "max_drawdown_pct": mdd,
    }
