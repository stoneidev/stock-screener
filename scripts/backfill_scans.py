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
    with zip_path.open("wb") as fh:
        subprocess.check_call(["gh", "api", archive_url], stdout=fh)
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
