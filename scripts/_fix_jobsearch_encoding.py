"""One-off: rewrite jobsearch/jobsearch.py as clean UTF-8."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "jobsearch" / "jobsearch.py"

CONTENT = '''\
"""
Job matching & application-support CLI.
Uses jobsearch_lib. Does NOT auto-submit applications.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import jobsearch_lib as lib


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing {name}. Add to environment.env")
        sys.exit(1)
    return value


def main() -> None:
    lib.load_env_files()
    parser = argparse.ArgumentParser(description="Germany-focused job matcher")
    parser.add_argument("--cv", type=Path, default=None)
    parser.add_argument("--min-score", type=int, default=50)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Score jobs from cache (same as --use-cache; writes jobsearch/output/<run>/ + data/scored_jobs.json)",
    )
    parser.add_argument(
        "--all-locations",
        action="store_true",
        help="Disable Germany filter (default: Germany + remote EU only)",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "apify", "free"],
        default="auto",
        help="Choose job source. auto=Apify if configured otherwise free sources.",
    )
    args = parser.parse_args()

    mistral_key = require_env("MISTRAL_API_KEY")
    cv_path = args.cv.resolve() if args.cv else lib.resolve_default_cv()
    cv = lib.load_cv(cv_path)
    profile = lib.load_profile()

    if args.run_pipeline:
        args.use_cache = True

    if args.refresh_cache:
        include_apify = args.source != "free"
        jobs = lib.refresh_jobs_cache(include_apify=include_apify)
        diag = lib.load_source_diagnostics()
        print(f"Cache refreshed: {len(jobs)} jobs (after region + CV filter)")
        for row in diag.get("sources") or []:
            if row.get("count", 0) or row.get("raw_count", 0):
                print(f"  - {row.get('source')}: {row.get('count', 0)} in region ({row.get('raw_count', 0)} raw)")
        if diag.get("apify_fallback_used"):
            print("  (Apify weak - free DE sources used as fallback)")
        token = os.getenv("APIFY_TOKEN", "").strip()
        ds = os.getenv("APIFY_DATASET_ID", "").strip()
        if token and ds and include_apify:
            check = lib.verify_apify_dataset(token, ds)
            print(
                f"  Apify dataset check: {check['in_target_region']}/{check['sample_size']} "
                f"in Rhine-Main/NRW sample - OK={check['ok_for_germany']}"
            )
        return

    if args.use_cache:
        jobs = lib.load_cached_jobs()
    else:
        jobs = lib.load_jobs(use_cache=False, source=args.source)

    if not args.all_locations:
        before = len(jobs)
        jobs, stats = lib.prefilter_jobs_for_candidate(jobs, profile)
        print(f"Region+CV filter: {before} -> {len(jobs)} jobs ({stats})")

    if args.max_jobs > 0:
        jobs = jobs[: args.max_jobs]

    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = SCRIPT_DIR / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"CV: {cv_path.name} ({len(cv)} chars)")
    print(f"Processing {len(jobs)} jobs -> {out_dir}\\n")

    results = []
    generated = 0

    for i, job in enumerate(jobs, 1):
        desc, about, title, company = lib.job_text_fields(job)
        if not desc:
            print(f"[{i}/{len(jobs)}] skip (no description): {title}")
            continue

        print(f"[{i}/{len(jobs)}] {title} @ {company} ...", end=" ", flush=True)
        try:
            match = lib.match_job(mistral_key, cv, job, profile)
        except Exception as exc:
            print(f"ERROR {exc}")
            continue

        score = int(match.get("match_score", 0))
        rec = match.get("recommendation", "skip")
        loc = job.get("location") or ""
        print(f"{score} -> {rec}")

        materials = None
        if not args.dry_run and lib.should_generate(match, args.min_score):
            print("    generating materials ...", end=" ", flush=True)
            try:
                materials = lib.generate_materials(mistral_key, cv, job, match, profile)
                generated += 1
                print("ok")
            except Exception as exc:
                print(f"ERROR {exc}")

        lib.write_job_output(out_dir, job, title, company, match, materials)
        results.append(
            {
                "score": score,
                "recommendation": rec,
                "qualified_to_apply": lib.is_qualified_to_apply(match),
                "company": company,
                "title": title,
                "location": loc,
            }
        )
        time.sleep(2)

    (out_dir / "summary.md").write_text(lib.build_summary_md(results, out_dir), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    apply_list = [r for r in results if r.get("qualified_to_apply")]
    (out_dir / "apply_shortlist.json").write_text(
        json.dumps(apply_list, indent=2), encoding="utf-8"
    )
    lib.SCORED_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lib.SCORED_JOBS_PATH.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "scored": len(results),
                "qualified": len(apply_list),
                "jobs": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\\nDone. Scored: {len(results)} | Generated: {generated}")
    print(f"Apply list: {len(apply_list)} qualified | scored_jobs: {lib.SCORED_JOBS_PATH}")
    print(f"Summary: {out_dir / 'summary.md'}")
    print("UI: streamlit run streamlit_app.py")


if __name__ == "__main__":
    main()
'''


def main() -> None:
    TARGET.write_text(CONTENT, encoding="utf-8", newline="\n")
    data = TARGET.read_bytes()
    if b"\x00" in data:
        raise SystemExit(f"still has null bytes: {data.count(0)}")
    print(f"wrote {TARGET} ({len(data)} bytes, nulls=0)")


if __name__ == "__main__":
    main()
