# GitHub Pages Dashboard + Top3 Trade Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the daily stock-screener's artifact-only text reports into a browsable GitHub Pages dashboard, and simulate trading the daily Top3 BUY signals (report stop/target, hold-until-hit) to track day-by-day returns, all auto-committed and deployed.

**Architecture:** A shared text-report parser converts scan `.txt` into structured JSON committed to the repo. A simulation engine reads those JSON files, enters the daily Top3 at next-trading-day open, and exits at the report's stop-loss/target using yfinance daily highs/lows, writing trades/equity/summary JSON. A build-less static site (`docs/site/`) fetches those JSON files. GitHub Actions backfills history from existing artifacts, then runs scan→json→simulation→commit→Pages-deploy daily.

**Tech Stack:** Python 3.11, pandas, yfinance, pytest + pytest-mock (all already in `requirements.txt`); vanilla HTML/JS + Chart.js (CDN) for the site; GitHub Actions + `actions/deploy-pages`; `gh` CLI for artifact backfill.

---

## Background facts (verified against the repo)

- Scanner entry point: `run_optimized_scan.py`. `save_report()` is at line 43; it's
  called at line 416 inside `main()`. It currently writes only
  `data/daily_scans/optimized_scan_<timestamp>.txt` and `latest_optimized_scan.txt`.
- `buy_signals` items (passed to `save_report`) are dicts with keys:
  `ticker, score, phase, entry_quality, stop_loss, breakout_price, risk_reward_ratio`,
  and `details` (containing `risk_amount`, `reward_amount`, `rs_slope`, `volume_ratio`,
  `vcp_data`), plus `reasons` (list). Some keys may be absent.
- `sell_signals` items: `ticker, score, severity, phase, breakdown_level, details, reasons`.
- Text report format (verified from a real artifact):
  - Header line `Scan Date: YYYY-MM-DD` (trust this, NOT the artifact label).
  - BUY block: `<emoji> BUY #N: TICKER | Score: S/125`, then `Phase: P`,
    `<emoji> Entry Quality: Q`, `Stop Loss: $X`,
    `<emoji> Risk/Reward: R:1 (Risk $A, Reward $B)`, optional `Breakout: $X`,
    optional `<emoji> RS: r`, optional `<emoji> Volume: vx`, then `Key Reasons:` bullets.
    **Some BUY blocks have no `Breakout:` line** (e.g. TEO) — target must be derived.
  - SELL block: `<emoji> SELL #N: TICKER | Score: S/110`, `Phase: P | <emoji> Severity: SEV`,
    optional `Breakdown: $X`, `<emoji> RS: r`, `Sell Reasons:` bullets.
- Available non-expired artifacts: 7, named `screening-results-2026-06-02` ..
  `screening-results-2026-06-10`. The simulation starts from the earliest scan present.
- Tests live in `tests/`, run with `pytest`. `.gitignore` already allows
  `data/daily_scans/**`; `data/simulation/` needs an allow-rule.

**Price-level convention (used everywhere):** stop-loss and target are absolute prices
taken from the report.
- `stop_loss` = reported `Stop Loss`.
- `target` = `breakout + reward_amount` when `Breakout:` present, else
  `stop_loss + risk_amount + reward_amount`.
These are fixed levels regardless of the simulated entry price (which is next-day open).

---

## File Structure

- Create `src/simulation/__init__.py` — package marker.
- Create `src/simulation/report_parser.py` — txt → dict; shared by live scan & backfill.
- Create `src/simulation/json_writer.py` — build the scan-JSON dict from in-memory
  signals (live path) and write scan/latest/index files.
- Create `src/simulation/price_provider.py` — yfinance daily bars + disk cache + next-trading-day helpers.
- Create `src/simulation/engine.py` — the Top3 hold-until-hit simulation.
- Create `scripts/run_simulation.py` — CLI: read scan JSON → run engine → write outputs.
- Create `scripts/backfill_scans.py` — download artifacts via `gh`, parse, emit scan JSON.
- Modify `run_optimized_scan.py` — call `json_writer` inside `save_report()`.
- Create `docs/site/index.html`, `docs/site/app.js`, `docs/site/style.css` — dashboard.
- Modify `.github/workflows/daily_screening_git_storage.yml` — add sim step + commit JSON.
- Create `.github/workflows/pages.yml` — build & deploy the site.
- Modify `.gitignore` — allow `data/simulation/**`.
- Tests: `tests/test_report_parser.py`, `tests/test_price_provider.py`,
  `tests/test_simulation_engine.py`, `tests/test_json_writer.py`.
- Test fixture: `tests/fixtures/sample_scan.txt`.

---

## Task 1: Text-report parser

**Files:**
- Create: `src/simulation/__init__.py`
- Create: `src/simulation/report_parser.py`
- Create: `tests/fixtures/sample_scan.txt`
- Test: `tests/test_report_parser.py`

- [ ] **Step 1: Create the package marker**

Create `src/simulation/__init__.py` with a single line:

```python
"""Trade simulation package for the daily Top3 screener signals."""
```

- [ ] **Step 2: Create the test fixture**

Create `tests/fixtures/sample_scan.txt` with exactly this content (covers: a BUY with
Breakout, a BUY without Breakout, and a SELL):

```
================================================================================
OPTIMIZED FULL MARKET SCAN - ALL US STOCKS
Scan Date: 2026-06-03
Generated: 2026-06-03 00:03:12
================================================================================

SCANNING STATISTICS
--------------------------------------------------------------------------------
Total Universe: 3,785 stocks
Analyzed: 1,631 stocks
🟢 Buy Signals: 2
🔴 Sell Signals: 1

============================================================
🟢 TOP BUY SIGNALS (Score >= 70) - 2 Total
============================================================

################################################################################
⭐ BUY #1: D | Score: 113.0/125
################################################################################
Phase: 2
🟢 Entry Quality: Good
Stop Loss: $64.23
🟢 Risk/Reward: 8.9:1 (Risk $2.24, Reward $19.94)
Breakout: $64.96
🟡 RS: 0.351
🟡 Volume: 1.8x

Key Reasons:
  • Good Stage 2: 5.8% above 50 SMA
  • SMAs rising strongly

################################################################################
⭐ BUY #2: TEO | Score: 112.8/125
################################################################################
Phase: 2
🟢 Entry Quality: Good
Stop Loss: $12.47
🟢 Risk/Reward: 3.0:1 (Risk $1.39, Reward $4.16)
🟢 RS: 0.881

Key Reasons:
  • Strong Stage 2: 15.4% above 50 SMA

============================================================
🔴 TOP SELL SIGNALS (Score >= 60) - 1 Total
============================================================

################################################################################
🚨 SELL #1: AII | Score: 100/110
################################################################################
Phase: 4 | 🚨 Severity: CRITICAL
Breakdown: $18.51
🔴 RS: -0.774

Sell Reasons:
  • In Phase 4 (Downtrend)
  • Broke below 50 SMA by 9.5%

================================================================================
END OF SCAN
================================================================================
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_report_parser.py`:

```python
from pathlib import Path

from src.simulation.report_parser import parse_report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_scan.txt"


def _parsed():
    return parse_report(FIXTURE.read_text())


def test_scan_date_from_header():
    assert _parsed()["scan_date"] == "2026-06-03"


def test_counts():
    p = _parsed()
    assert len(p["buys"]) == 2
    assert len(p["sells"]) == 1


def test_buy_with_breakout():
    buy = _parsed()["buys"][0]
    assert buy["rank"] == 1
    assert buy["ticker"] == "D"
    assert buy["score"] == 113.0
    assert buy["phase"] == 2
    assert buy["entry_quality"] == "Good"
    assert buy["stop_loss"] == 64.23
    assert buy["breakout"] == 64.96
    assert buy["risk_amount"] == 2.24
    assert buy["reward_amount"] == 19.94
    assert buy["rr_ratio"] == 8.9
    assert buy["rs_slope"] == 0.351
    assert buy["volume_ratio"] == 1.8
    # target = breakout + reward
    assert abs(buy["target"] - (64.96 + 19.94)) < 1e-6
    assert buy["reasons"][0].startswith("Good Stage 2")


def test_buy_without_breakout_derives_target():
    buy = _parsed()["buys"][1]
    assert buy["ticker"] == "TEO"
    assert buy["breakout"] is None
    # target = stop_loss + risk + reward = 12.47 + 1.39 + 4.16
    assert abs(buy["target"] - (12.47 + 1.39 + 4.16)) < 1e-6


def test_sell_block():
    sell = _parsed()["sells"][0]
    assert sell["ticker"] == "AII"
    assert sell["score"] == 100.0
    assert sell["phase"] == 4
    assert sell["severity"] == "CRITICAL"
    assert sell["breakdown_level"] == 18.51
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_report_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.simulation.report_parser'`

- [ ] **Step 5: Implement the parser**

Create `src/simulation/report_parser.py`:

```python
"""Parse the screener's text report into a structured dict.

Shared by the live scan JSON writer and the artifact backfill script so both
produce identical JSON.
"""

import re
from typing import Optional


def _money(text: str) -> Optional[float]:
    m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", text)
    return float(m.group(1)) if m else None


def _first_float(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def _parse_buy_block(block: str) -> Optional[dict]:
    header = re.search(r"BUY #(\d+):\s*(\S+)\s*\|\s*Score:\s*([0-9.]+)", block)
    if not header:
        return None
    rank, ticker, score = int(header.group(1)), header.group(2), float(header.group(3))

    phase = _first_float(r"Phase:\s*(\d+)", block)
    stop_loss = _money(_grab_line("Stop Loss:", block) or "")
    breakout = _money(_grab_line("Breakout:", block) or "")

    rr = re.search(
        r"Risk/Reward:\s*([0-9.]+):1\s*\(Risk \$([0-9.]+),\s*Reward \$([0-9.]+)\)",
        block,
    )
    rr_ratio = float(rr.group(1)) if rr else None
    risk_amount = float(rr.group(2)) if rr else None
    reward_amount = float(rr.group(3)) if rr else None

    eq = _grab_line("Entry Quality:", block)
    entry_quality = eq.split("Entry Quality:")[-1].strip() if eq else None

    rs_slope = _first_float(r"RS:\s*(-?[0-9.]+)", block)
    volume_ratio = _first_float(r"Volume:\s*([0-9.]+)x", block)

    target = None
    if breakout is not None and reward_amount is not None:
        target = breakout + reward_amount
    elif stop_loss is not None and risk_amount is not None and reward_amount is not None:
        target = stop_loss + risk_amount + reward_amount

    reasons = _parse_reasons(block)

    return {
        "rank": rank, "ticker": ticker, "score": score,
        "phase": int(phase) if phase is not None else None,
        "entry_quality": entry_quality,
        "stop_loss": stop_loss, "breakout": breakout,
        "risk_amount": risk_amount, "reward_amount": reward_amount,
        "rr_ratio": rr_ratio, "target": target,
        "rs_slope": rs_slope, "volume_ratio": volume_ratio,
        "reasons": reasons,
    }


def _parse_sell_block(block: str) -> Optional[dict]:
    header = re.search(r"SELL #(\d+):\s*(\S+)\s*\|\s*Score:\s*([0-9.]+)", block)
    if not header:
        return None
    sev = re.search(r"Severity:\s*([A-Z]+)", block)
    phase = _first_float(r"Phase:\s*(\d+)", block)
    return {
        "rank": int(header.group(1)), "ticker": header.group(2),
        "score": float(header.group(3)),
        "phase": int(phase) if phase is not None else None,
        "severity": sev.group(1) if sev else None,
        "breakdown_level": _money(_grab_line("Breakdown:", block) or ""),
    }


def _grab_line(label: str, block: str) -> Optional[str]:
    for line in block.splitlines():
        if label in line:
            return line
    return None


def _parse_reasons(block: str) -> list:
    reasons, collecting = [], False
    for line in block.splitlines():
        if "Key Reasons:" in line or "Sell Reasons:" in line:
            collecting = True
            continue
        if collecting:
            stripped = line.strip()
            if stripped.startswith("•"):
                reasons.append(stripped.lstrip("• ").strip())
            elif stripped == "" or stripped.startswith("#") or stripped.startswith("="):
                break
    return reasons


def parse_report(text: str) -> dict:
    """Parse a full scan report text into {scan_date, buys, sells}."""
    date_m = re.search(r"Scan Date:\s*(\d{4}-\d{2}-\d{2})", text)
    scan_date = date_m.group(1) if date_m else None

    # Blocks are delimited by lines of '#'. Each signal block follows a '#'*N line.
    blocks = re.split(r"\n#{10,}\n", text)
    buys, sells = [], []
    for block in blocks:
        if "BUY #" in block:
            parsed = _parse_buy_block(block)
            if parsed:
                buys.append(parsed)
        elif "SELL #" in block:
            parsed = _parse_sell_block(block)
            if parsed:
                sells.append(parsed)

    buys.sort(key=lambda b: b["rank"])
    sells.sort(key=lambda s: s["rank"])
    return {"scan_date": scan_date, "buys": buys, "sells": sells}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_report_parser.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
cd /Users/jngkim/stock-screener
git add src/simulation/__init__.py src/simulation/report_parser.py tests/test_report_parser.py tests/fixtures/sample_scan.txt
git commit -m "feat(sim): add scan text-report parser with tests"
```

---

## Task 2: JSON writer (scan/latest/index)

**Files:**
- Create: `src/simulation/json_writer.py`
- Test: `tests/test_json_writer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_json_writer.py`:

```python
import json
from pathlib import Path

from src.simulation.json_writer import write_scan_json, rebuild_index


def test_write_scan_json_and_index(tmp_path):
    parsed = {
        "scan_date": "2026-06-03",
        "buys": [{"rank": 1, "ticker": "D", "score": 113.0, "stop_loss": 64.23, "target": 84.9}],
        "sells": [{"rank": 1, "ticker": "AII", "score": 100.0}],
    }
    out = tmp_path / "daily_scans"
    path = write_scan_json(parsed, output_dir=out)

    assert path == out / "scan_2026-06-03.json"
    saved = json.loads(path.read_text())
    assert saved["scan_date"] == "2026-06-03"
    assert saved["counts"] == {"buy": 1, "sell": 1}
    assert (out / "latest.json").exists()

    rebuild_index(output_dir=out)
    index = json.loads((out / "index.json").read_text())
    assert index["dates"] == ["2026-06-03"]
    assert index["latest"] == "2026-06-03"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_json_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.simulation.json_writer'`

- [ ] **Step 3: Implement the JSON writer**

Create `src/simulation/json_writer.py`:

```python
"""Write structured scan JSON, the latest pointer, and the date index."""

import json
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]
DEFAULT_DIR = Path("data/daily_scans")


def _enrich(parsed: dict) -> dict:
    return {
        "scan_date": parsed.get("scan_date"),
        "generated_at": parsed.get("generated_at"),
        "market": parsed.get("market", {}),
        "counts": {"buy": len(parsed.get("buys", [])), "sell": len(parsed.get("sells", []))},
        "buys": parsed.get("buys", []),
        "sells": parsed.get("sells", []),
    }


def write_scan_json(parsed: dict, output_dir: PathLike = DEFAULT_DIR) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = _enrich(parsed)
    date = data["scan_date"]
    if not date:
        raise ValueError("parsed report has no scan_date")
    path = out / f"scan_{date}.json"
    path.write_text(json.dumps(data, indent=2))
    (out / "latest.json").write_text(json.dumps(data, indent=2))
    return path


def rebuild_index(output_dir: PathLike = DEFAULT_DIR) -> Path:
    out = Path(output_dir)
    dates = sorted(
        p.name[len("scan_"):-len(".json")]
        for p in out.glob("scan_*.json")
    )
    index = {"dates": dates, "latest": dates[-1] if dates else None}
    path = out / "index.json"
    path.write_text(json.dumps(index, indent=2))
    return path
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_json_writer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jngkim/stock-screener
git add src/simulation/json_writer.py tests/test_json_writer.py
git commit -m "feat(sim): add scan JSON writer and date index"
```

---

## Task 3: Wire JSON output into the live scanner

**Files:**
- Modify: `run_optimized_scan.py` (inside `save_report`, ends at line ~275; called at line 416)

- [ ] **Step 1: Add imports and a helper that converts in-memory signals to parser-shaped dicts**

At the top of `run_optimized_scan.py`, after the existing `from pathlib import Path`
(line 23), add:

```python
import json as _json
from src.simulation.json_writer import write_scan_json, rebuild_index
```

- [ ] **Step 2: Build the parsed dict and write JSON at the end of `save_report`**

In `run_optimized_scan.py`, `save_report()` currently ends by writing
`latest_optimized_scan.txt` (around line 273-275). Immediately after that block,
before the function returns, add:

```python
    # --- Structured JSON output (for Pages + simulation) ---
    def _buy_to_json(rank, s):
        details = s.get('details', {}) or {}
        breakout = s.get('breakout_price')
        reward = details.get('reward_amount')
        risk = details.get('risk_amount')
        stop = s.get('stop_loss')
        if breakout is not None and reward is not None:
            target = breakout + reward
        elif stop is not None and risk is not None and reward is not None:
            target = stop + risk + reward
        else:
            target = None
        return {
            "rank": rank, "ticker": s.get('ticker'), "score": s.get('score'),
            "phase": s.get('phase'), "entry_quality": s.get('entry_quality'),
            "stop_loss": stop, "breakout": breakout,
            "risk_amount": risk, "reward_amount": reward,
            "rr_ratio": s.get('risk_reward_ratio'), "target": target,
            "rs_slope": details.get('rs_slope'), "volume_ratio": details.get('volume_ratio'),
            "reasons": list(s.get('reasons', []))[:7],
        }

    def _sell_to_json(rank, s):
        return {
            "rank": rank, "ticker": s.get('ticker'), "score": s.get('score'),
            "phase": s.get('phase'), "severity": s.get('severity'),
            "breakdown_level": s.get('breakdown_level'),
        }

    parsed = {
        "scan_date": date_str,
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "market": {
            "spy_phase": spy_analysis.get('phase') if isinstance(spy_analysis, dict) else None,
        },
        "buys": [_buy_to_json(i, s) for i, s in enumerate(buy_signals, 1)],
        "sells": [_sell_to_json(i, s) for i, s in enumerate(sell_signals, 1)],
    }
    write_scan_json(parsed, output_dir=output_dir)
    rebuild_index(output_dir=output_dir)
```

Note: `date_str` and `output_dir` already exist in `save_report`'s scope.

- [ ] **Step 3: Smoke-test imports (no live scan)**

Run: `cd /Users/jngkim/stock-screener && python -c "import run_optimized_scan; print('import ok')"`
Expected: prints `import ok` with no traceback.

- [ ] **Step 4: Commit**

```bash
cd /Users/jngkim/stock-screener
git add run_optimized_scan.py
git commit -m "feat(scan): emit structured scan JSON + index alongside text report"
```

---

## Task 4: Price provider (yfinance + cache + trading-day helpers)

**Files:**
- Create: `src/simulation/price_provider.py`
- Test: `tests/test_price_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_price_provider.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_price_provider.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: next_trading_day_open`

- [ ] **Step 3: Implement the price provider**

Create `src/simulation/price_provider.py`:

```python
"""Daily OHLC provider backed by yfinance, with on-disk caching.

Pure helpers (next_trading_day_open, bars_after) take a DataFrame so they are
unit-testable without network access.
"""

import json
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_price_provider.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/jngkim/stock-screener
git add src/simulation/price_provider.py tests/test_price_provider.py
git commit -m "feat(sim): add yfinance price provider with cache and trading-day helpers"
```

---

## Task 5: Simulation engine

**Files:**
- Create: `src/simulation/engine.py`
- Test: `tests/test_simulation_engine.py`

The engine takes a list of scan dicts (already parsed) and a `price_fn(ticker) -> DataFrame`
callable (so tests inject synthetic prices, no network). It enters each day's valid Top3 at
the next-trading-day open, holds until daily `low <= stop` (stop wins on same-day tie) or
`high >= target`, and reports trades, equity curve, and summary.

- [ ] **Step 1: Write the failing test**

Create `tests/test_simulation_engine.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_simulation_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.simulation.engine'`

- [ ] **Step 3: Implement the engine**

Create `src/simulation/engine.py`:

```python
"""Top3 buy-signal trade simulation.

Policy (fixed, per design spec):
- Each scan day, enter the valid top_n BUY signals at the NEXT trading day's open.
- Stop-loss and target are absolute price levels taken from the report.
- Hold until daily low <= stop (stop wins on same-day tie) or high >= target.
- A ticker already held is not re-entered while its position is open.
- Position size = initial_capital / top_n (fixed dollar amount per trade).
- Equity = initial_capital + cumulative realized PnL + open-position unrealized PnL.
"""

from typing import Callable, List, Optional

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
                "ticker": ticker, "entry_date": str(entry_day.date()),
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
            last_close[ticker] = (str(ts.date()), float(row["Close"]))
            low, high = float(row["Low"]), float(row["High"])
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
        mark = last_close.get(ticker, (pos["entry_date"], pos["entry_price"]))[1]
        unreal = (mark - pos["entry_price"]) * pos["shares"]
        open_list.append({**pos, "mark_price": mark, "unrealized_pnl": unreal})

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
        "ticker": pos["ticker"], "entry_date": pos["entry_date"],
        "entry_price": pos["entry_price"], "exit_date": str(ts.date()),
        "exit_price": exit_price, "shares": pos["shares"],
        "pnl": pnl, "pnl_pct": pnl_pct, "exit_reason": reason,
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_simulation_engine.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/jngkim/stock-screener
git add src/simulation/engine.py tests/test_simulation_engine.py
git commit -m "feat(sim): add Top3 hold-until-hit simulation engine with tests"
```

---

## Task 6: Simulation CLI runner

**Files:**
- Create: `scripts/run_simulation.py`

- [ ] **Step 1: Implement the runner**

Create `scripts/run_simulation.py`:

```python
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
```

- [ ] **Step 2: Verify it runs with no scan data (graceful no-op)**

Run: `cd /Users/jngkim/stock-screener && python scripts/run_simulation.py`
Expected: prints `No scan JSON found ... nothing to simulate.` (exit 0). (Real data arrives in Task 8.)

- [ ] **Step 3: Commit**

```bash
cd /Users/jngkim/stock-screener
git add scripts/run_simulation.py
git commit -m "feat(sim): add simulation CLI runner"
```

---

## Task 7: Artifact backfill script

**Files:**
- Create: `scripts/backfill_scans.py`

- [ ] **Step 1: Implement the backfill script**

Create `scripts/backfill_scans.py`:

```python
#!/usr/bin/env python3
"""Backfill structured scan JSON from existing GitHub Actions artifacts.

Uses the `gh` CLI (must be authenticated) to list non-expired
`screening-results-*` artifacts, download each, parse the contained
text report, and emit data/daily_scans/scan_<scan_date>.json. Idempotent:
skips a scan date whose JSON already exists.
"""

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.simulation.report_parser import parse_report
from src.simulation.json_writer import write_scan_json, rebuild_index

REPO = "stoneidev/stock-screener"
SCAN_DIR = Path("data/daily_scans")


def list_artifacts():
    out = subprocess.check_output(
        ["gh", "api", f"repos/{REPO}/actions/artifacts", "--paginate"],
        text=True,
    )
    data = json.loads(out)
    return [a for a in data.get("artifacts", []) if not a.get("expired")]


def download_artifact(artifact, dest: Path):
    archive_url = artifact["archive_download_url"]
    zip_path = dest / f"{artifact['id']}.zip"
    subprocess.check_call(
        ["gh", "api", archive_url], stdout=zip_path.open("wb"),
    )
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


def find_report_txt(folder: Path):
    candidates = list(folder.rglob("optimized_scan_*.txt"))
    if not candidates:
        candidates = list(folder.rglob("latest_optimized_scan.txt"))
    return candidates[0] if candidates else None


def main():
    artifacts = [a for a in list_artifacts() if a["name"].startswith("screening-results-")]
    print(f"Found {len(artifacts)} non-expired screening artifacts")
    created = 0
    for art in sorted(artifacts, key=lambda a: a["name"]):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            try:
                download_artifact(art, tmpdir)
            except Exception as exc:
                print(f"  ⚠ download failed for {art['name']}: {exc}")
                continue
            txt = find_report_txt(tmpdir)
            if not txt:
                print(f"  ⚠ no report txt in {art['name']}")
                continue
            parsed = parse_report(txt.read_text())
            if not parsed["scan_date"]:
                print(f"  ⚠ no scan_date in {art['name']}")
                continue
            target = SCAN_DIR / f"scan_{parsed['scan_date']}.json"
            if target.exists():
                print(f"  = {parsed['scan_date']} already present, skipping")
                continue
            write_scan_json(parsed, output_dir=SCAN_DIR)
            created += 1
            print(f"  ✓ {parsed['scan_date']}: {len(parsed['buys'])} buys, {len(parsed['sells'])} sells")
    rebuild_index(output_dir=SCAN_DIR)
    print(f"Backfill complete: {created} new scan files; index rebuilt.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports/parses CLI without running network calls**

Run: `cd /Users/jngkim/stock-screener && python -c "import ast,sys; ast.parse(open('scripts/backfill_scans.py').read()); print('syntax ok')"`
Expected: prints `syntax ok`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jngkim/stock-screener
git add scripts/backfill_scans.py
git commit -m "feat(sim): add GitHub artifact backfill script for historical scans"
```

---

## Task 8: Run backfill + simulation for real (data generation)

**Files:**
- Modify: `.gitignore`
- Generates: `data/daily_scans/scan_*.json`, `data/simulation/*.json`

- [ ] **Step 1: Allow simulation outputs in git**

In `.gitignore`, find the block at the end that starts with `# Data (keep cache and scan archives)`.
After the existing `!data/position_reports/**` line, add:

```
!data/simulation/
!data/simulation/*.json
```

(We intentionally do NOT un-ignore `data/simulation/price_cache/` — price CSVs stay local.)

Also add a nested ignore so the cache subfolder is excluded even though `data/simulation/` is allowed:

```
data/simulation/price_cache/
```

- [ ] **Step 2: Run the backfill**

Run: `cd /Users/jngkim/stock-screener && python scripts/backfill_scans.py`
Expected: lists the 7 artifacts and writes `data/daily_scans/scan_<date>.json` for each
(one per distinct internal scan date), plus `latest.json` and `index.json`.

Verify: `ls data/daily_scans/` shows several `scan_*.json` files and `index.json`.

- [ ] **Step 3: Run the simulation**

Run: `cd /Users/jngkim/stock-screener && python scripts/run_simulation.py`
Expected: prints a summary line (Trades/Open/Win rate/Return/MDD) and writes four files
to `data/simulation/`. (Requires network for yfinance.)

Verify: `cat data/simulation/summary.json` shows real numbers.

- [ ] **Step 4: Commit the generated data**

```bash
cd /Users/jngkim/stock-screener
git add .gitignore data/daily_scans/*.json data/simulation/*.json
git commit -m "data: backfill historical scans and initial Top3 simulation results"
```

---

## Task 9: Static dashboard site

**Files:**
- Create: `docs/site/index.html`
- Create: `docs/site/style.css`
- Create: `docs/site/app.js`

The site is built-less. At deploy time (Task 11) the workflow copies `data/daily_scans/`
and `data/simulation/` into `docs/site/data/`, so the site fetches `./data/...`.

- [ ] **Step 1: Create `docs/site/index.html`**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stock Screener — Reports & Top3 Simulation</title>
  <link rel="stylesheet" href="./style.css" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head>
<body>
  <header>
    <h1>📈 Stock Screener Dashboard</h1>
    <nav>
      <button data-tab="sim" class="active">Top3 Simulation</button>
      <button data-tab="report">Daily Report</button>
    </nav>
  </header>

  <section id="sim" class="tab active">
    <div id="summary-cards" class="cards"></div>
    <div class="chart-wrap"><canvas id="equityChart"></canvas></div>
    <h2>Open Positions</h2>
    <table id="open-table"><thead><tr>
      <th>Ticker</th><th>Entry Date</th><th>Entry</th><th>Stop</th><th>Target</th><th>Mark</th><th>Unrealized</th>
    </tr></thead><tbody></tbody></table>
    <h2>Closed Trades</h2>
    <table id="trades-table"><thead><tr>
      <th>Ticker</th><th>Entry Date</th><th>Entry</th><th>Exit Date</th><th>Exit</th><th>Reason</th><th>P&L %</th>
    </tr></thead><tbody></tbody></table>
  </section>

  <section id="report" class="tab">
    <label>Scan date:
      <select id="date-select"></select>
    </label>
    <div id="market-line"></div>
    <h2>🟢 Top BUY Signals</h2>
    <div id="buy-cards" class="cards"></div>
    <h2>🔴 Top SELL Signals</h2>
    <div id="sell-cards" class="cards"></div>
  </section>

  <footer>Generated by stock-screener · data refreshed daily via GitHub Actions</footer>
  <script src="./app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `docs/site/style.css`**

```css
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #0f1419; color: #e6e6e6; }
header { padding: 1rem 1.5rem; background: #161b22; border-bottom: 1px solid #30363d; }
h1 { margin: 0 0 .5rem; font-size: 1.3rem; }
nav button { background: #21262d; color: #e6e6e6; border: 1px solid #30363d; padding: .4rem .9rem; margin-right: .5rem; border-radius: 6px; cursor: pointer; }
nav button.active { background: #238636; border-color: #238636; }
.tab { display: none; padding: 1.5rem; }
.tab.active { display: block; }
.cards { display: flex; flex-wrap: wrap; gap: 1rem; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; min-width: 180px; flex: 1 1 200px; }
.card .big { font-size: 1.6rem; font-weight: 700; }
.pos { color: #3fb950; } .neg { color: #f85149; }
.chart-wrap { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; font-size: .9rem; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #30363d; }
th { color: #8b949e; font-weight: 600; }
select { background: #21262d; color: #e6e6e6; border: 1px solid #30363d; border-radius: 6px; padding: .3rem; }
#market-line { margin: .8rem 0; color: #8b949e; }
footer { padding: 1rem 1.5rem; color: #8b949e; border-top: 1px solid #30363d; font-size: .85rem; }
```

- [ ] **Step 3: Create `docs/site/app.js`**

```javascript
const $ = (sel) => document.querySelector(sel);
const fmtPct = (v) => (v == null ? "—" : `${v.toFixed(2)}%`);
const fmtUsd = (v) => (v == null ? "—" : `$${Number(v).toFixed(2)}`);
const cls = (v) => (v >= 0 ? "pos" : "neg");

async function getJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch ${path}: ${res.status}`);
  return res.json();
}

// --- Tabs ---
document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
  });
});

// --- Simulation tab ---
async function loadSimulation() {
  let summary, equity, open, trades;
  try {
    [summary, equity, open, trades] = await Promise.all([
      getJSON("./data/simulation/summary.json"),
      getJSON("./data/simulation/equity_curve.json"),
      getJSON("./data/simulation/open_positions.json"),
      getJSON("./data/simulation/trades.json"),
    ]);
  } catch (e) {
    $("#summary-cards").innerHTML = `<div class="card">No simulation data yet.</div>`;
    return;
  }

  $("#summary-cards").innerHTML = [
    ["Total Return", fmtPct(summary.total_return_pct), summary.total_return_pct],
    ["Win Rate", fmtPct(summary.win_rate), summary.win_rate],
    ["Trades", summary.num_trades, 0],
    ["Open", summary.num_open, 0],
    ["Max Drawdown", fmtPct(summary.max_drawdown_pct), summary.max_drawdown_pct],
  ].map(([label, val, signed]) =>
    `<div class="card"><div>${label}</div><div class="big ${typeof signed === "number" && signed !== 0 ? cls(signed) : ""}">${val}</div></div>`
  ).join("");

  new Chart($("#equityChart"), {
    type: "line",
    data: {
      labels: equity.map((p) => p.date),
      datasets: [{ label: "Equity", data: equity.map((p) => p.equity),
        borderColor: "#3fb950", backgroundColor: "rgba(63,185,80,.15)", fill: true, tension: .2 }],
    },
    options: { scales: { x: { ticks: { color: "#8b949e" } }, y: { ticks: { color: "#8b949e" } } },
      plugins: { legend: { labels: { color: "#e6e6e6" } } } },
  });

  $("#open-table tbody").innerHTML = open.map((p) =>
    `<tr><td>${p.ticker}</td><td>${p.entry_date}</td><td>${fmtUsd(p.entry_price)}</td>
     <td>${fmtUsd(p.stop_loss)}</td><td>${fmtUsd(p.target)}</td><td>${fmtUsd(p.mark_price)}</td>
     <td class="${cls(p.unrealized_pnl)}">${fmtUsd(p.unrealized_pnl)}</td></tr>`
  ).join("") || `<tr><td colspan="7">No open positions.</td></tr>`;

  $("#trades-table tbody").innerHTML = trades.map((t) =>
    `<tr><td>${t.ticker}</td><td>${t.entry_date}</td><td>${fmtUsd(t.entry_price)}</td>
     <td>${t.exit_date}</td><td>${fmtUsd(t.exit_price)}</td><td>${t.exit_reason}</td>
     <td class="${cls(t.pnl_pct)}">${fmtPct(t.pnl_pct)}</td></tr>`
  ).join("") || `<tr><td colspan="7">No closed trades.</td></tr>`;
}

// --- Report tab ---
async function loadReportIndex() {
  let index;
  try { index = await getJSON("./data/daily_scans/index.json"); }
  catch (e) { $("#market-line").textContent = "No scan data yet."; return; }
  const sel = $("#date-select");
  sel.innerHTML = index.dates.slice().reverse()
    .map((d) => `<option value="${d}">${d}</option>`).join("");
  sel.addEventListener("change", () => loadReport(sel.value));
  if (index.dates.length) loadReport(index.latest);
}

async function loadReport(date) {
  const scan = await getJSON(`./data/daily_scans/scan_${date}.json`);
  $("#market-line").textContent =
    `Buys: ${scan.counts.buy} · Sells: ${scan.counts.sell}` +
    (scan.market && scan.market.spy_phase != null ? ` · SPY Phase ${scan.market.spy_phase}` : "");

  $("#buy-cards").innerHTML = scan.buys.slice(0, 12).map((b) =>
    `<div class="card"><div class="big">#${b.rank} ${b.ticker}</div>
     <div>Score: ${b.score}</div><div>Phase ${b.phase ?? "—"} · ${b.entry_quality ?? ""}</div>
     <div>Stop ${fmtUsd(b.stop_loss)} → Target ${fmtUsd(b.target)}</div>
     <div>${(b.reasons || []).slice(0, 3).map((r) => "• " + r).join("<br/>")}</div></div>`
  ).join("") || `<div class="card">No buy signals.</div>`;

  $("#sell-cards").innerHTML = scan.sells.slice(0, 12).map((s) =>
    `<div class="card"><div class="big">#${s.rank} ${s.ticker}</div>
     <div>Score: ${s.score}</div><div>Phase ${s.phase ?? "—"} · ${s.severity ?? ""}</div>
     <div>Breakdown ${fmtUsd(s.breakdown_level)}</div></div>`
  ).join("") || `<div class="card">No sell signals.</div>`;
}

loadSimulation();
loadReportIndex();
```

- [ ] **Step 4: Smoke-test the site locally against backfilled data**

```bash
cd /Users/jngkim/stock-screener
mkdir -p docs/site/data
cp -r data/daily_scans docs/site/data/
cp -r data/simulation docs/site/data/ 2>/dev/null; rm -rf docs/site/data/simulation/price_cache
python -m http.server 8765 --directory docs/site &
sleep 1; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/index.html
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/data/daily_scans/index.json
kill %1
rm -rf docs/site/data
```

Expected: both curl calls print `200`. (The temporary `docs/site/data` copy is removed; it is
recreated by the deploy workflow.)

- [ ] **Step 5: Commit**

```bash
cd /Users/jngkim/stock-screener
git add docs/site/index.html docs/site/style.css docs/site/app.js
git commit -m "feat(site): add static dashboard for reports and Top3 simulation"
```

---

## Task 10: Wire simulation + JSON commit into the daily workflow

**Files:**
- Modify: `.github/workflows/daily_screening_git_storage.yml`

- [ ] **Step 1: Add a simulation step after the screening run**

In `.github/workflows/daily_screening_git_storage.yml`, the step
`- name: Run optimized stock screening` ends with the `python run_optimized_scan.py ...`
command. Immediately AFTER that step (before `- name: Show fundamental refresh stats`),
insert:

```yaml
      - name: Run Top3 trade simulation
        run: |
          python scripts/run_simulation.py
```

- [ ] **Step 2: Commit scan + simulation JSON in the existing commit step**

In the same file, the step `- name: Commit updated fundamental cache` contains
`git add data/fundamentals_cache/`. Change that line to also stage the JSON outputs:

```yaml
          git add data/fundamentals_cache/ data/daily_scans/*.json data/simulation/*.json
```

And update the commit message line in that step to reflect the broader content:

```yaml
            git commit -m "chore: update scan JSON, simulation, and fundamental cache - ${{ steps.date.outputs.date }}"
```

- [ ] **Step 3: Validate workflow YAML**

Run: `cd /Users/jngkim/stock-screener && python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_screening_git_storage.yml')); print('yaml ok')"`
Expected: prints `yaml ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/jngkim/stock-screener
git add .github/workflows/daily_screening_git_storage.yml
git commit -m "ci: run Top3 simulation and commit scan/sim JSON in daily workflow"
```

---

## Task 11: Pages deploy workflow

**Files:**
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Create the deploy workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy Dashboard to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'docs/site/**'
      - 'data/daily_scans/*.json'
      - 'data/simulation/*.json'
      - '.github/workflows/pages.yml'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Assemble site (copy data into site)
        run: |
          mkdir -p docs/site/data/daily_scans docs/site/data/simulation
          cp data/daily_scans/*.json docs/site/data/daily_scans/ 2>/dev/null || true
          cp data/simulation/*.json docs/site/data/simulation/ 2>/dev/null || true

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs/site

      - name: Deploy
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Validate workflow YAML**

Run: `cd /Users/jngkim/stock-screener && python -c "import yaml; yaml.safe_load(open('.github/workflows/pages.yml')); print('yaml ok')"`
Expected: prints `yaml ok`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jngkim/stock-screener
git add .github/workflows/pages.yml
git commit -m "ci: add GitHub Pages deploy workflow for dashboard"
```

---

## Task 12: Full test sweep + README note

**Files:**
- Modify: `README.md` (append a short section)

- [ ] **Step 1: Run the whole simulation test suite**

Run: `cd /Users/jngkim/stock-screener && python -m pytest tests/test_report_parser.py tests/test_json_writer.py tests/test_price_provider.py tests/test_simulation_engine.py -v`
Expected: all PASS.

- [ ] **Step 2: Append usage docs to README**

Add this section near the end of `README.md` (before the license/footer if present):

```markdown
## 📊 Dashboard & Top3 Simulation

The daily scan now also emits machine-readable JSON (`data/daily_scans/scan_*.json`)
and runs a Top3 buy-signal trade simulation.

- **Simulation policy:** each scan day, enter the top 3 BUY signals at the next
  trading day's open; exit at the report's stop-loss or target (stop wins on a
  same-day tie); hold until hit. Prices come from yfinance daily bars.
- **Run locally:**
  ```bash
  python scripts/backfill_scans.py     # one-time: rebuild history from GH artifacts
  python scripts/run_simulation.py     # compute trades / equity / summary
  ```
- **Dashboard:** static site in `docs/site/`, auto-deployed to GitHub Pages by
  `.github/workflows/pages.yml`. Enable Pages (Settings → Pages → Source: GitHub Actions).
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jngkim/stock-screener
git add README.md
git commit -m "docs: document dashboard and Top3 simulation usage"
```

---

## Post-implementation manual steps (outside the plan, for the repo owner)

1. **Enable GitHub Pages:** repo Settings → Pages → Source = "GitHub Actions".
2. **Push the branch and open a PR** (or push to main if that's the workflow).
3. After the first Pages deploy, the dashboard URL appears in the `pages.yml` run summary.

---

## Self-Review Notes

- **Spec coverage:** Component 1 (JSON output + backfill) → Tasks 1,2,3,7,8.
  Component 2 (simulation engine) → Tasks 4,5,6,8. Component 3 (Pages) → Task 9.
  Component 4 (workflows) → Tasks 10,11. Start-from-earliest-scan → handled by
  `run_simulation.py` (`min scan_date`) and backfill of all artifacts. ✓
- **Policy fidelity:** report stop/target used as-is (parser + engine), next-day-open
  entry, hold-until-hit, no re-entry while open, stop-wins-on-tie — all covered with tests. ✓
- **Type consistency:** parsed buy dict keys (`stop_loss`, `target`, `rank`, `ticker`,
  `score`) are identical across `report_parser`, `json_writer`, `engine`, and `app.js`. ✓
- **Known limitation (logged, not hidden):** only 7 non-expired artifacts exist, so the
  simulation history starts ~2026-06-03; earlier data is unrecoverable. Stated in spec/README.
```
