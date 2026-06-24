"""Scheduled job search, auto-score, and email digest helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from django.core.mail import send_mail

from . import pipeline_status as pstatus

JOBSEARCH_ROOT = Path(__file__).resolve().parents[1] / 'jobsearch'
DIGEST_STATE_PATH = JOBSEARCH_ROOT / 'data' / 'digest_state.json'


def auto_score_after_search_enabled() -> bool:
    return os.getenv('AUTO_SCORE_AFTER_SEARCH', 'true').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )


def scheduled_search_enabled() -> bool:
    return os.getenv('SCHEDULED_JOB_SEARCH', 'true').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )


def digest_email_enabled() -> bool:
    return os.getenv('JOB_DIGEST_EMAIL', '').strip() != ''


def digest_recipient() -> str:
    return os.getenv('JOB_DIGEST_EMAIL', '').strip() or os.getenv('DEFAULT_FROM_EMAIL', '').strip()


def _load_digest_state() -> dict:
    if not DIGEST_STATE_PATH.exists():
        return {}
    try:
        return json.loads(DIGEST_STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_digest_state(data: dict) -> None:
    DIGEST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_STATE_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _good_match_jobs(jobs_payload: list[dict], *, limit: int = 10) -> list[dict]:
    rows = [
        job for job in jobs_payload
        if job.get('good_match') and int(job.get('match_score') or 0) >= 50
    ]
    rows.sort(key=lambda j: (-(j.get('match_score') or 0), j.get('title') or ''))
    return rows[:limit]


def send_job_digest_email(jobs_payload: list[dict], *, force: bool = False) -> str:
    """Email new 50%+ matches. Returns status message."""
    recipient = digest_recipient()
    if not recipient:
        return 'Digest skipped — set JOB_DIGEST_EMAIL on Render.'

    good = _good_match_jobs(jobs_payload, limit=20)
    state = _load_digest_state()
    seen = set(state.get('sent_job_ids') or [])
    fresh = [j for j in good if j.get('job_id') not in seen]
    if not fresh and not force:
        return 'Digest skipped — no new 50%+ matches since last email.'

    top = fresh[:3] if fresh else good[:3]
    if not top:
        return 'Digest skipped — no 50%+ matches to report.'

    lines = [
        'Your daily job digest from Ivana CV job search',
        f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '',
        f'{len(fresh)} new strong match(es) today (showing top {len(top)}):',
        '',
    ]
    for i, job in enumerate(top, 1):
        title = job.get('title_en') or job.get('title') or 'Role'
        company = job.get('company') or 'Company'
        score = job.get('match_score')
        hint = (job.get('list_hint') or '')[:200]
        url = job.get('apply_url') or ''
        lines.append(f'{i}. {title} @ {company} ({score}% match)')
        if hint:
            lines.append(f'   {hint}')
        if url:
            lines.append(f'   Apply: {url}')
        lines.append('')

    base = os.getenv('CV_PUBLIC_BASE_URL', '').strip().rstrip('/')
    browse_url = f'{base}/jobs/market/?view=good' if base else '/jobs/market/?view=good'
    lines.extend([
        'Browse all matches:',
        browse_url,
        '',
        '— Automated by your CV job search site',
    ])
    body = '\n'.join(lines)
    subject = f'{len(fresh) or len(top)} new job match(es) 50%+ — Ivana CV jobs'

    email_host = os.getenv('EMAIL_HOST', '').strip()
    if not email_host:
        _save_digest_state({
            'last_digest_at': datetime.now().isoformat(timespec='seconds'),
            'sent_job_ids': list(seen | {j.get('job_id') for j in top if j.get('job_id')}),
            'last_digest_preview': body[:2000],
        })
        return (
            'Digest prepared (email not sent — add EMAIL_HOST + EMAIL_HOST_USER + '
            'EMAIL_HOST_PASSWORD on Render). Preview saved locally.'
        )

    from_email = os.getenv('DEFAULT_FROM_EMAIL', recipient)
    send_mail(subject, body, from_email, [recipient], fail_silently=False)
    _save_digest_state({
        'last_digest_at': datetime.now().isoformat(timespec='seconds'),
        'sent_job_ids': list(seen | {j.get('job_id') for j in top if j.get('job_id')}),
    })
    return f'Digest emailed to {recipient} ({len(top)} roles).'


def run_daily_automation(*, send_digest: bool = True) -> dict:
    """Search → auto-score → optional digest. Used by cron and management command."""
    import jobsearch_lib as lib
    from .views import (
        DEFAULT_MAX_JOBS,
        DEFAULT_MIN_SCORE,
        WEB_MAX_JOBS,
        _background_score,
        _build_unified_job_rows,
        _load_market_cached_jobs,
        _merged_scored_lookup,
        _row_to_job_payload,
        applied_jobs,
    )

    if pstatus.is_running():
        return {'ok': False, 'error': 'Pipeline already running'}

    lib.load_env_files()
    results: dict = {'ok': True, 'steps': []}

    if scheduled_search_enabled():
        pstatus.write_status(
            state='running',
            label='Scheduled search',
            phase='search',
            message='Daily search started…',
            progress=0,
            total=0,
        )

        def on_progress(**fields):
            fields.setdefault('phase', 'search')
            pstatus.write_status(state='running', label='Scheduled search', **fields)

        jobs = lib.refresh_jobs_cache(include_apify=True, on_progress=on_progress)
        results['steps'].append(f'Search: {len(jobs)} jobs in cache')
    else:
        results['steps'].append('Search skipped (SCHEDULED_JOB_SEARCH=false)')

    if auto_score_after_search_enabled() and os.getenv('MISTRAL_API_KEY', '').strip():
        pstatus.write_status(
            state='running',
            label='Scheduled scoring',
            phase='score',
            message='Scoring jobs with AI…',
        )
        _background_score(
            use_cache=True,
            max_jobs=min(DEFAULT_MAX_JOBS, WEB_MAX_JOBS),
            min_score=DEFAULT_MIN_SCORE,
            dry_run=True,
        )
        results['steps'].append('Score: completed')
    else:
        if not os.getenv('MISTRAL_API_KEY', '').strip():
            results['steps'].append('Score skipped — MISTRAL_API_KEY missing')
        else:
            results['steps'].append('Score skipped (AUTO_SCORE_AFTER_SEARCH=false)')

    if send_digest and digest_email_enabled():
        cached = _load_market_cached_jobs()
        scored_lookup = _merged_scored_lookup(None)
        applied_id_set = applied_jobs.applied_ids()
        browse_rows = [
            row for row in _build_unified_job_rows(cached, scored_lookup, hide_low_scores=False)
            if row['job_id'] not in applied_id_set
        ]
        payload = [_row_to_job_payload(row) for row in browse_rows]
        digest_msg = send_job_digest_email(payload)
        results['steps'].append(digest_msg)
    elif send_digest:
        results['steps'].append('Digest skipped — JOB_DIGEST_EMAIL not set')

    # If search ran but scoring was skipped, clear stale "running" status.
    if pstatus.read_status().get('state') == 'running':
        pstatus.write_status(
            state='completed',
            phase='search',
            message=results.get('message') or 'Daily automation finished.',
            error='',
            progress=100,
            total=100,
        )

    results['message'] = ' · '.join(results['steps'])
    return results
