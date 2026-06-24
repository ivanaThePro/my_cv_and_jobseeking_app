#!/usr/bin/env python
"""Run enabled Apify actors from config/apify_sources.json and print dataset stats.

Usage (from project root):
  python jobsearch/scripts/run_apify_scrapers.py

Requires APIFY_TOKEN in .env. This uses Apify credits (Indeed runs = one billing unit per search).
After a successful run, you can copy dataset IDs from Apify Console into APIFY_DATASET_IDS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobsearch"))

import jobsearch_lib as lib  # noqa: E402


def main() -> None:
    lib.load_env_files()
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        print("Missing APIFY_TOKEN in .env")
        sys.exit(1)

    print("Running enabled Apify actors (see config/apify_sources.json)...")
    print("This may take several minutes and will use Apify credits.\n")

    jobs, meta = lib.fetch_apify_via_configured_actors(token)
    print(f"Merged in-region jobs: {len(jobs)}\n")
    for row in meta:
        print(f"  {row.get('source')}: raw={row.get('raw_count')} in_region={row.get('count')} status={row.get('status')}")
        if row.get("error"):
            print(f"    error: {row['error']}")
    print(
        "\nTip: In Apify Console → run → Storage → Dataset, copy IDs into .env:\n"
        "  APIFY_DATASET_IDS=indeed:YOUR_ID,linkedin:YOUR_ID\n"
        "Then set APIFY_AUTO_RUN=false for faster refreshes that only read saved datasets."
    )


if __name__ == "__main__":
    main()
