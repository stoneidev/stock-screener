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
