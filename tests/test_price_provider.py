import pandas as pd

from src.simulation import price_provider as pp


def _frame():
    idx = pd.to_datetime(["2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08"])
    return pd.DataFrame(
        {"Open": [10, 11, 12, 13], "High": [10.5, 11.5, 12.5, 13.5],
         "Low": [9.5, 10.5, 11.5, 12.5], "Close": [10.2, 11.2, 12.2, 13.2]},
        index=idx,
    )


def test_next_trading_day_open_skips_weekend():
    df = _frame()
    # scan on Friday 2026-06-05 -> next trading day is Monday 2026-06-08
    day, open_px = pp.next_trading_day_open(df, "2026-06-05")
    assert str(day.date()) == "2026-06-08"
    assert open_px == 13


def test_next_trading_day_open_none_when_no_future_bar():
    df = _frame()
    assert pp.next_trading_day_open(df, "2026-06-08") == (None, None)


def test_bars_after_returns_only_later_rows():
    df = _frame()
    after = pp.bars_after(df, "2026-06-04")
    assert list(after.index.strftime("%Y-%m-%d")) == ["2026-06-05", "2026-06-08"]
