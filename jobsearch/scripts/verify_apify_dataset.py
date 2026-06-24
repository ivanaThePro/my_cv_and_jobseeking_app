#!/usr/bin/env python
"""Check whether APIFY_DATASET_ID contains Germany / target-region jobs."""
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
    ds = os.getenv("APIFY_DATASET_ID", "").strip()
    if not token or not ds:
        print("Set APIFY_TOKEN and APIFY_DATASET_ID in .env")
        sys.exit(1)

    result = lib.verify_apify_dataset(token, ds)
    print(f"Dataset: {result['dataset_id']}")
    print(f"Raw rows: {result['raw_count']}")
    print(f"In target region (sample): {result['in_target_region']} / {result['sample_size']}")
    print(f"OK for Germany pipeline: {result['ok_for_germany']}")
    print("Sample locations:")
    for loc in result["sample_locations"]:
        print(f"  - {loc}")
    if not result["ok_for_germany"]:
        print("\nThis dataset looks US/global. Comment out APIFY_DATASET_ID — free sources will still work.")
        sys.exit(2)


if __name__ == "__main__":
    main()
