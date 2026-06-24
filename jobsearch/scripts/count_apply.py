import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobsearch_lib as lib  # noqa: E402

jobs = lib.load_cached_jobs()
print("cache", len(jobs))

lookup: dict[str, dict] = {}
for run in sorted((Path(__file__).parents[1] / "output").iterdir(), key=lambda p: p.name):
    if not run.is_dir():
        continue
    for folder in run.iterdir():
        if not folder.is_dir():
            continue
        mf = folder / "match.json"
        if not mf.exists():
            continue
        meta = json.loads(mf.read_text(encoding="utf-8"))
        key = (meta.get("apply_url") or "").strip() or f"{meta.get('company')}|{meta.get('title')}".lower()
        lookup[key] = meta

print("total scored (merged runs)", len(lookup))
apply = review = 0
ready = 0
for meta in lookup.values():
    m = meta.get("match") or {}
    rec = m.get("recommendation")
    sc = int(m.get("match_score") or 0)
    if rec == "apply":
        apply += 1
    if rec == "review":
        review += 1
    url = meta.get("apply_url") or ""
    if lib.is_apply_list_job(m, url):
        ready += 1
print("apply rec", apply, "review", review, "apply-ready urls", ready)
