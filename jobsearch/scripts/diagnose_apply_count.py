"""Count jobs at each funnel stage (cache → prefilter → scored → apply list)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobsearch"))
import jobsearch_lib as lib  # noqa: E402

lib.load_env_files()


def merged_scored():
    lookup = {}
    out = ROOT / "jobsearch" / "output"
    for run in sorted(out.iterdir()):
        if not run.is_dir():
            continue
        for folder in run.iterdir():
            mf = folder / "match.json"
            if not mf.exists():
                continue
            data = json.loads(mf.read_text(encoding="utf-8"))
            meta = data.get("metadata") or data
            url = (meta.get("apply_url") or "").strip()
            key = url or f"{meta.get('company', '')}|{meta.get('title', '')}".lower()
            lookup[key] = {
                "match": data.get("match") or {},
                "apply_url": url,
            }
    return lookup


def main():
    cached = lib.load_cached_jobs()
    profile = lib.load_profile()
    filtered, stats = lib.prefilter_jobs_for_candidate(cached, profile)
    scored = merged_scored()

    direct = sum(
        1
        for j in cached
        if lib.is_direct_apply_url(
            (j.get("applyUrl") or j.get("url") or j.get("link") or "").strip()
        )
    )

    apply_strict = apply_broad = review_ok = 0
    for j in cached:
        title = j.get("title") or ""
        company = j.get("company") or ""
        url = (j.get("applyUrl") or j.get("url") or j.get("link") or "").strip()
        key = url or f"{company}|{title}".lower()
        row = scored.get(key)
        if not row:
            continue
        m = row["match"]
        if lib.is_apply_list_job(m, url):
            apply_strict += 1
        if lib.is_broad_opportunity(m):
            apply_broad += 1
        if m.get("recommendation") == "review":
            review_ok += 1

    print("MATCH_MODE:", lib.MATCH_MODE)
    print("cache:", len(cached), "direct_apply_urls:", direct)
    print("prefilter kept:", len(filtered), "stats:", stats)
    print("merged scored keys:", len(scored))
    print("apply_list (strict fn):", apply_strict)
    print("broad_opportunity:", apply_broad)
    print("recommendation=review:", review_ok)


if __name__ == "__main__":
    main()
