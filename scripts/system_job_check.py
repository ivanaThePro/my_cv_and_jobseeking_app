"""End-to-end check: job sources, Ivana CV profile, cache, AI scoring."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cvsite.settings")

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

import django

django.setup()

JOBSEARCH_DIR = ROOT / "jobsearch"
sys.path.insert(0, str(JOBSEARCH_DIR))

import jobsearch_lib as lib  # noqa: E402


def main() -> int:
    print("=== IVANA JOB SYSTEM CHECK ===\n")

    mistral = bool(os.getenv("MISTRAL_API_KEY", "").strip())
    jooble = bool(os.getenv("JOOBLE_API_KEY", "").strip())
    apify = bool(os.getenv("APIFY_TOKEN", "").strip())

    print("API keys:")
    print(f"  MISTRAL_API_KEY (AI scoring): {'YES' if mistral else 'NO - scoring disabled'}")
    print(f"  JOOBLE_API_KEY (extra listings): {'YES' if jooble else 'not set'}")
    print(f"  APIFY_TOKEN (LinkedIn/Indeed): {'YES' if apify else 'not set'}")
    print()

    profile_path = ROOT / "jobsearch/data/cv_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    print(f"CV profile: {profile.get('candidate')}")
    print(f"  Seniority: {profile.get('seniority_level')}")
    prefs = profile.get("location_preferences") or []
    print(f"  Locations: {', '.join(prefs[:5])}...")
    print(f"  Qualified role families: {len(profile.get('qualified_role_families') or [])}")
    print()

    for label, path in [
        ("jobs_cache.json", lib.JOBS_CACHE_PATH),
        ("jobs_cache_live.json", lib.JOBS_LIVE_PATH),
    ]:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            jobs = raw if isinstance(raw, list) else raw.get("jobs") or []
            print(f"Cache {label}: {len(jobs)} jobs")
        else:
            print(f"Cache {label}: missing (run Search on dashboard)")
    print()

    runs = lib.list_output_runs()
    if runs:
        print(f"Scoring runs: {len(runs)} (latest: {runs[0].name})")
        latest = runs[0]
        scores: list[int] = []
        for match_file in latest.glob("*/match.json"):
            try:
                match = json.loads(match_file.read_text(encoding="utf-8"))
                inner = match.get("match") or match
                scores.append(int(inner.get("match_score") or 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        good = sum(1 for score in scores if score >= 50)
        print(f"  Latest run: {len(scores)} scored, {good} at 50%+ match")
        if scores:
            print(
                f"  Score range: {min(scores)}-{max(scores)}%, "
                f"avg {sum(scores) // len(scores)}%"
            )
    else:
        print("Scoring runs: none yet (click Score AI after Search)")
    print()

    print("Testing live job sources (1-3 min)...")
    try:
        source_counts: list[tuple[str, str]] = []

        def on_source_done(**payload):
            source_name = payload.get("source_name", "unknown")
            merged_jobs = payload.get("merged_jobs") or []
            sources_meta = payload.get("sources_meta") or []
            error = payload.get("error")
            step = payload.get("step")
            total = payload.get("total_steps")
            prefix = f"[{step}/{total}] " if step and total else ""
            if error:
                line = f"{prefix}{source_name}: ERROR - {error[:80]}"
            else:
                last = next(
                    (entry for entry in reversed(sources_meta) if entry.get("source") == source_name),
                    {},
                )
                count = last.get("count", "?")
                line = f"{prefix}{source_name}: {count} jobs (merged {len(merged_jobs)})"
            print(f"  {line}")

        jobs, meta = lib.fetch_germany_free_jobs(on_source_done=on_source_done)
        print(f"\nMerged free sources: {len(jobs)} unique jobs")
        by_source: dict[str, int] = {}
        for job in jobs:
            source = job.get("source") or "unknown"
            by_source[source] = by_source.get(source, 0) + 1
        for source, count in sorted(by_source.items(), key=lambda item: -item[1])[:12]:
            print(f"  {source}: {count}")
    except Exception as exc:
        print(f"Scrape test failed: {exc}")
        return 1
    print()

    if mistral:
        print("Testing AI scoring against Ivana CV (sample career-counselor role)...")
        api_key = os.getenv("MISTRAL_API_KEY", "").strip()
        cv_text = lib.load_cv()
        profile = lib.load_profile()
        sample = {
            "title": "Career Counselor / Karriereberater (m/w/d)",
            "company": "Test GmbH",
            "location": "Frankfurt am Main, Germany",
            "description": (
                "Career guidance, adult education, counseling. Bachelor degree required. "
                "German B2. Experience in teaching or social work."
            ),
            "apply_url": "https://example.com/job/1",
            "source": "test",
        }
        try:
            match = lib.match_job(api_key, cv_text, sample, profile)
            if match:
                print(f"  Sample score: {match.get('match_score')}%")
                print(f"  Recommendation: {match.get('recommendation')}")
                reasoning = (match.get("reasoning") or "")[:160]
                print(f"  Reasoning: {reasoning}...")
            else:
                print("  No match returned")
        except Exception as exc:
            print(f"  Scoring error: {exc}")
            return 1
    else:
        print("AI scoring test skipped: add MISTRAL_API_KEY to .env for evaluation")

    print("\n=== SUMMARY ===")
    print("Scraping: Arbeitsagentur, EURES, Arbeitnow, RSS feeds (StepStone/Indeed/Adzuna when reachable)")
    print("Optional: Jooble API, Apify LinkedIn/Indeed")
    print("NOT wired yet: Xing, Jobware, Stellenanzeigen, Jobrapido (reference list only)")
    print("Evaluation: Mistral AI compares each job to Ivana's CV profile after you click Score AI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
