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
