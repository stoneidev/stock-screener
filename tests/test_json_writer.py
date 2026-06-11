import json

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
