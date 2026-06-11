import pandas as pd

from src.simulation.engine import run_simulation


def make_prices(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {"Open": [r[1] for r in rows], "High": [r[2] for r in rows],
         "Low": [r[3] for r in rows], "Close": [r[4] for r in rows]},
        index=idx,
    )


def test_target_hit_produces_profit():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "AAA", "score": 100, "stop_loss": 9.0, "target": 12.0}],
    }]
    prices = {"AAA": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 10.5, 9.8, 10.2),   # entry open = 10
        ("2026-06-05", 10.5, 12.5, 10.4, 12.1),  # high >= target 12 -> exit at 12
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    trades = result["trades"]
    assert len(trades) == 1
    t = trades[0]
    assert t["entry_price"] == 10
    assert t["exit_price"] == 12.0
    assert t["exit_reason"] == "target"
    assert t["pnl"] > 0


def test_stop_hit_produces_loss():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "BBB", "score": 100, "stop_loss": 9.0, "target": 20.0}],
    }]
    prices = {"BBB": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 10.2, 9.9, 10),     # entry open = 10
        ("2026-06-05", 9.5, 9.6, 8.5, 8.7),    # low <= stop 9 -> exit at 9
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    t = result["trades"][0]
    assert t["exit_price"] == 9.0
    assert t["exit_reason"] == "stop"
    assert t["pnl"] < 0


def test_same_day_stop_wins_over_target():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "CCC", "score": 100, "stop_loss": 9.0, "target": 11.0}],
    }]
    prices = {"CCC": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 10, 10, 10),         # entry open = 10
        ("2026-06-05", 10, 11.5, 8.5, 9.0),     # both stop and target touched -> stop wins
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    assert result["trades"][0]["exit_reason"] == "stop"


def test_unfilled_position_stays_open():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "DDD", "score": 100, "stop_loss": 5.0, "target": 50.0}],
    }]
    prices = {"DDD": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 11, 9, 10),          # entry, never hits stop/target
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    assert result["trades"] == []
    assert len(result["open_positions"]) == 1
    assert result["open_positions"][0]["ticker"] == "DDD"


def test_top_n_limits_entries_and_skips_invalid():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [
            {"rank": 1, "ticker": "A1", "score": 100, "stop_loss": 9.0, "target": 12.0},
            {"rank": 2, "ticker": "A2", "score": 99, "stop_loss": None, "target": None},  # invalid -> skipped
            {"rank": 3, "ticker": "A3", "score": 98, "stop_loss": 9.0, "target": 12.0},
            {"rank": 4, "ticker": "A4", "score": 97, "stop_loss": 9.0, "target": 12.0},
        ],
    }]
    bars = make_prices([("2026-06-03", 10, 10, 10, 10), ("2026-06-04", 10, 10, 10, 10)])
    result = run_simulation(scans, lambda t: bars, initial_capital=99000, top_n=3)
    entered = {p["ticker"] for p in result["open_positions"]}
    assert entered == {"A1", "A3", "A4"}  # A2 skipped, top_n filled from valid signals


def test_nan_bar_is_skipped_and_does_not_poison_equity():
    # yfinance can return a partial (NaN) bar for the current day; it must not
    # trigger an exit nor produce NaN equity for an open position.
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "EEE", "score": 100, "stop_loss": 5.0, "target": 50.0}],
    }]
    prices = {"EEE": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 11, 9, 10.2),                    # entry open = 10
        ("2026-06-05", 10, 11, 9, 10.5),                    # last valid close
        ("2026-06-08", float("nan"), float("nan"), float("nan"), float("nan")),  # partial day
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    pos = result["open_positions"][0]
    assert pos["mark_price"] == 10.5          # last valid close, not NaN
    assert pos["unrealized_pnl"] == pos["unrealized_pnl"]  # not NaN
    assert result["summary"]["total_return_pct"] == result["summary"]["total_return_pct"]


def test_summary_fields_present():
    scans = [{
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "AAA", "score": 100, "stop_loss": 9.0, "target": 12.0}],
    }]
    prices = {"AAA": make_prices([
        ("2026-06-03", 10, 10, 10, 10),
        ("2026-06-04", 10, 10, 10, 10),
        ("2026-06-05", 10.5, 12.5, 10.4, 12.1),
    ])}
    result = run_simulation(scans, lambda t: prices[t], initial_capital=99000, top_n=3)
    s = result["summary"]
    for key in ["total_return_pct", "win_rate", "num_trades", "max_drawdown_pct", "avg_pnl"]:
        assert key in s
    assert len(result["equity_curve"]) >= 1
