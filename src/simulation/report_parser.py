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


def parse_report(text: str) -> dict:
    """Parse a full scan report text into {scan_date, buys, sells}."""
    date_m = re.search(r"Scan Date:\s*(\d{4}-\d{2}-\d{2})", text)
    scan_date = date_m.group(1) if date_m else None

    # Split on the signal headers themselves so each block carries the header
    # line plus its body (the '####' separator lines stay inside the block).
    matches = list(re.finditer(r"^.*(?:BUY|SELL) #\d+:.*$", text, re.MULTILINE))
    buys, sells = [], []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        if "BUY #" in m.group(0):
            parsed = _parse_buy_block(block)
            if parsed:
                buys.append(parsed)
        elif "SELL #" in m.group(0):
            parsed = _parse_sell_block(block)
            if parsed:
                sells.append(parsed)

    buys.sort(key=lambda b: b["rank"])
    sells.sort(key=lambda s: s["rank"])
    return {"scan_date": scan_date, "buys": buys, "sells": sells}
