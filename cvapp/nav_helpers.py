"""Shared stats and actions for the global dashboard top bar."""

from __future__ import annotations

import json
import os

from . import applied_jobs
from . import pipeline_status as pstatus

import jobsearch_lib as lib

BROWSE_VIEW_LABELS = {
    'all': 'All jobs',
    'good': 'Good matches',
    'it_good': 'IT · ready to apply',
    'it': 'IT & tech',
    'non_it_good': 'Non-tech · ready',
    'non_it': 'Non-tech',
    'unscored': 'Awaiting score',
    'degree': 'Degree-ready',
    'full': 'Full match',
}


def _get_cache_info() -> dict:
    path = getattr(lib, 'JOBS_CACHE_PATH', None)
    if not path or not path.exists():
        return {'exists': False, 'count': 0, 'updated': None}
    try:
        jobs = json.loads(path.read_text(encoding='utf-8'))
        count = len(jobs) if isinstance(jobs, list) else 0
    except Exception:
        count = 0
    from datetime import datetime
    return {
        'exists': True,
        'count': count,
        'updated': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
    }


def _browse_filter_qs(request) -> str:
    parts: list[str] = []
    if request.GET.get('english_ok') == '1':
        parts.append('english_ok=1')
    if request.GET.get('entry') == '1':
        parts.append('entry=1')
    program = request.GET.get('program', '').strip().lower()
    if program:
        parts.append(f'program={program}')
    if not parts:
        return ''
    return '&' + '&'.join(parts)


def _browse_context(request, tab_stats: dict) -> dict:
    view = request.GET.get('view', 'all').strip().lower()
    if view in ('picks', 'broad', 'apply', 'strong', 'matches', 'review', 'scored'):
        view = 'good'
    if view in ('unanalyzed', 'waiting', 'new'):
        view = 'unscored'
    if view not in BROWSE_VIEW_LABELS:
        view = 'all'
    raw_total = tab_stats.get('cache_raw_total', tab_stats.get('cache_total', 0))
    return {
        'browse_view': view,
        'browse_view_label': BROWSE_VIEW_LABELS.get(view, view),
        'browse_filter_qs': _browse_filter_qs(request),
        'browse_english_ok': request.GET.get('english_ok') == '1',
        'browse_entry_only': request.GET.get('entry') == '1',
        'browse_program': request.GET.get('program', '').strip().lower(),
        'browse_all_total': raw_total,
        'browse_scored_total': tab_stats.get('scored_total', 0),
        'browse_good_total': tab_stats.get('good_fits_total', 0),
        'browse_it_good_total': tab_stats.get('it_good_total', 0),
        'browse_non_it_good_total': tab_stats.get('non_it_good_total', 0),
        'browse_it_total': tab_stats.get('it_total', 0),
        'browse_non_it_total': tab_stats.get('non_it_total', 0),
        'browse_other_total': tab_stats.get('other_total', 0),
        'browse_degree_total': tab_stats.get('degree_ready_total', 0),
        'browse_full_total': tab_stats.get('full_match_total', 0),
        'browse_unscored_total': tab_stats.get('unscored_total', 0),
    }


def get_topbar_context(request=None) -> dict:
    lib.load_env_files()
    cache_info = _get_cache_info()

    from cvapp.views import _find_resumable_run, _market_tab_stats

    tab_stats = getattr(request, '_market_tab_stats', None) if request else None
    on_market = bool(request and '/jobs/market' in (request.path or ''))
    if tab_stats is None and on_market:
        tab_stats = _market_tab_stats()
    elif tab_stats is None:
        tab_stats = {
            'cache_raw_total': cache_info.get('count', 0),
            'cache_total': cache_info.get('count', 0),
            'good_fits_total': 0,
            'waiting_for_ai': 0,
            'unscored_total': 0,
            'scored_total': 0,
            'non_it_total': 0,
            'it_total': 0,
            'other_total': 0,
            'it_good_total': 0,
            'non_it_good_total': 0,
            'degree_ready_total': 0,
            'full_match_total': 0,
        }
    resumable = _find_resumable_run()
    cache_count = tab_stats['cache_raw_total']
    waiting_for_ai = tab_stats['waiting_for_ai']

    ctx = {
        'nav_cache_info': {**cache_info, 'count': cache_count},
        'nav_good_fits_count': tab_stats['good_fits_total'],
        'nav_waiting_for_ai': waiting_for_ai,
        'nav_applied_count': len(applied_jobs.applied_ids()),
        'nav_pipeline_running': pstatus.is_running(),
        'nav_resumable_run': resumable.name if resumable else '',
        'nav_incomplete_scoring': False,
        'nav_mistral_key': bool(os.getenv('MISTRAL_API_KEY', '').strip()),
    }
    try:
        from cvapp.views import list_generated_role_cvs
        ctx['nav_generated_role_cvs'] = list_generated_role_cvs(limit=12)
    except Exception:
        ctx['nav_generated_role_cvs'] = []
    if request and '/jobs/market' in (request.path or ''):
        ctx.update(_browse_context(request, tab_stats))
    return ctx
