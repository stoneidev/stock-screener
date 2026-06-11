"""Daily OHLC provider backed by yfinance, with on-disk caching.

Pure helpers (next_trading_day_open, bars_after) take a DataFrame so they are
unit-testable without network access.
"""

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

CACHE_DIR = Path("data/simulation/price_cache")


def next_trading_day_open(df: pd.DataFrame, scan_date: str) -> Tuple[Optional[pd.Timestamp], Optional[float]]:
    """Return (timestamp, open price) of the first bar strictly after scan_date."""
    cutoff = pd.Timestamp(scan_date)
    future = df[df.index > cutoff]
    if future.empty:
        return None, None
    row = future.iloc[0]
    return future.index[0], float(row["Open"])


def bars_after(df: pd.DataFrame, date) -> pd.DataFrame:
    """Bars strictly after the given date (inclusive of later days)."""
    cutoff = pd.Timestamp(date)
    return df[df.index > cutoff]


def get_history(ticker: str, start: str, end: Optional[str] = None,
                cache_dir: Path = CACHE_DIR) -> pd.DataFrame:
    """Fetch daily OHLC for ticker in [start, end], caching to disk as CSV."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{ticker}_{start}_{end or 'now'}.csv"
    if cache_file.exists():
        return pd.read_csv(cache_file, index_col=0, parse_dates=True)

    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]]
    df.to_csv(cache_file)
    return df
