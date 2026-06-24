import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings as django_settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import applied_jobs
from . import pipeline_status as pstatus
from .cv_access import (
    check_cv_password,
    cv_is_unlocked,
    ensure_cv_access,
    grant_cv_access,
    require_cv_access,
    revoke_cv_access,
)
from .cv_pdf import build_cv_pdf_bytes
from .cv_profiles import DEFAULT_CV_SLUG, get_cv_profile, list_cv_profiles
from .standalone_cv import get_standalone_cv, list_standalone_cvs, read_standalone_cv_html
from .standalone_cv_builder import build_ai_tailored_cv_html, build_cover_letter_html, ROLE_CVS

JOB_SEARCH_ROOT = Path(__file__).resolve().parents[1] / 'jobsearch'
TAILORED_CV_DIR = JOB_SEARCH_ROOT / 'data' / 'tailored_cvs'
if JOB_SEARCH_ROOT.exists() and str(JOB_SEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(JOB_SEARCH_ROOT))

import jobsearch_lib as lib  # noqa: E402

JOB_SEARCH_OUTPUT_ROOT = JOB_SEARCH_ROOT / 'output'
JOB_ENGINE_ROOT = JOB_SEARCH_ROOT
DEFAULT_MAX_JOBS = int(getattr(django_settings, 'JOB_DEFAULT_MAX_JOBS', 250))
DEFAULT_MIN_SCORE = int(getattr(django_settings, 'JOB_DEFAULT_MIN_SCORE', 50))
DISPLAY_MIN_SCORE = int(getattr(django_settings, 'JOB_DISPLAY_MIN_SCORE', 50))
LIST_MIN_SCORE = int(getattr(django_settings, 'JOB_LIST_MIN_SCORE', 30))
WEB_MAX_JOBS = 250

APP_STATIC_DIR = Path(__file__).resolve().parent / 'static'
COURSE_SYLLABUS_DIR = Path(__file__).resolve().parents[1] / 'course sylabus'
_ASSET_MIME = {
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
}

_JOBS_HUB_URL_FALLBACKS = {
    'jobs_status_api': '/jobs/status/',
    'jobs_applied_toggle': '/jobs/applied/toggle/',
    'jobs_generate_materials': '/jobs/generate-materials/',
    'jobs_import_url': '/jobs/import-url/',
    'jobs_refine_materials': '/jobs/refine-materials/',
    'jobs_applied': '/jobs/applied/',
    'jobs_market': '/jobs/market/',
    'jobs_market_live': '/jobs/market/live/',
}

VALID_MATERIAL_TYPES = frozenset({'cv', 'cover_letter', 'both'})
REFINE_MATERIAL_TYPES = frozenset({'cv', 'cover_letter'})

_STATS_CACHE: dict = {'at': 0.0, 'data': {}}
_STATS_CACHE_TTL = 15.0
_SLIM_JOBS_CACHE: dict = {'key': '', 'payloads': []}


def _slim_jobs_cache_key() -> str:
    path = getattr(lib, 'JOBS_CACHE_PATH', None)
    mtime = int(path.stat().st_mtime) if path and path.exists() else 0
    runs = _list_job_runs()
    run_key = '|'.join(r.name for r in runs)
    live_path = getattr(lib, 'JOBS_LIVE_PATH', None)
    live_mtime = int(live_path.stat().st_mtime) if live_path and live_path.exists() else 0
    live_count = 0
    if pstatus.is_running():
        try:
            live_count = len(lib.load_live_jobs().get('jobs') or [])
        except Exception:
            live_count = 0
    return f'{mtime}:{run_key}:{len(applied_jobs.applied_ids())}:{live_mtime}:{live_count}'


def _build_slim_jobs_list(master_rows: list[dict]) -> list[dict]:
    """Build slim payloads; reuse cached rows so live-search refreshes stay fast."""
    cached_by_id = {
        p['job_id']: p
        for p in (_SLIM_JOBS_CACHE.get('payloads') or [])
        if isinstance(p, dict) and p.get('job_id')
    }
    payloads: list[dict] = []
    for row in master_rows:
        job_id = row['job_id']
        hit = cached_by_id.get(job_id)
        if hit:
            payloads.append(hit)
        else:
            payloads.append(_row_to_job_list_payload(row))
    _SLIM_JOBS_CACHE['key'] = _slim_jobs_cache_key()
    _SLIM_JOBS_CACHE['payloads'] = payloads
    return payloads


def _invalidate_slim_jobs_cache() -> None:
    _SLIM_JOBS_CACHE['key'] = ''
    _SLIM_JOBS_CACHE['payloads'] = []
    _BROWSE_BASE_ROWS_CACHE['key'] = ''
    _BROWSE_BASE_ROWS_CACHE['rows'] = []
    _BROWSE_BASE_ROWS_CACHE['stats'] = None


_MARKET_DATA_CACHE: dict = {'key': '', 'at': 0.0, 'data': None}
_MARKET_DATA_CACHE_TTL = 20.0
_SCORED_LOOKUP_CACHE: dict = {'key': '', 'lookup': {}}
_BROWSE_BASE_ROWS_CACHE: dict = {'key': '', 'rows': [], 'stats': None}


def _safe_reverse(name: str, *args, **kwargs) -> str:
    try:
        return reverse(name, *args, **kwargs)
    except Exception:
        return _JOBS_HUB_URL_FALLBACKS.get(name, '/')


def _jobs_hub_urls(*, view: str = 'non_it') -> dict:
    return {
        'status_url': _safe_reverse('jobs_status_api'),
        'applied_toggle_url': _safe_reverse('jobs_applied_toggle'),
        'generate_materials_url': _safe_reverse('jobs_generate_materials'),
        'refine_materials_url': _safe_reverse('jobs_refine_materials'),
        'import_job_url': _safe_reverse('jobs_import_url'),
        'score_one_url': _safe_reverse('jobs_score_one'),
        'applied_page_url': _safe_reverse('jobs_applied'),
        'browse_page_url': f"{_safe_reverse('jobs_market')}?view={view}",
        'live_data_url': _safe_reverse('jobs_market_live'),
    }


def system_check(request):
    """Diagnostic: which code folder is running (local DEBUG only)."""
    if not django_settings.DEBUG:
        raise Http404('Not found')
    import cvsite.urls as site_urls
    import cvapp.urls as app_urls
    lines = [
        'Project OK - new URLconf is loaded.',
        'Homepage: consolidated academic record (courses only).',
        'Deploy marker: 2026-06-15-transcript-root',
        f'cvsite.urls file: {site_urls.__file__}',
        f'cvapp.urls file: {app_urls.__file__}',
        f'First routes: {[str(p.pattern) for p in site_urls.urlpatterns[:4]]}',
        f'serve_asset: {serve_asset.__module__}.{serve_asset.__name__}',
    ]
    from django.http import HttpResponse
    return HttpResponse(
        '<pre>' + '\n'.join(lines) + '</pre>',
        content_type='text/html; charset=utf-8',
    )


def serve_asset(request, asset_path: str):
    """Serve CSS/JS directly from cvapp/static (bypasses broken staticfiles handler on Windows)."""
    safe = Path(asset_path)
    if '..' in safe.parts or safe.is_absolute():
        raise Http404('Invalid asset path')
    full_path = APP_STATIC_DIR / safe
    if not full_path.is_file():
        raise Http404(f'Asset not found: {asset_path}')
    content_type = _ASSET_MIME.get(full_path.suffix.lower(), 'application/octet-stream')
    return FileResponse(full_path.open('rb'), content_type=content_type)


def serve_course_syllabus_backup(request, filename: str):
    """Serve syllabus backup PDFs inline from the live site."""
    safe = Path(filename)
    if '..' in safe.parts or safe.is_absolute() or safe.suffix.lower() != '.pdf':
        raise Http404('Invalid syllabus path')
    full_path = COURSE_SYLLABUS_DIR / safe
    if not full_path.is_file():
        raise Http404(f'Syllabus backup not found: {filename}')
    response = FileResponse(full_path.open('rb'), content_type='application/pdf')
    response['Content-Disposition'] = content_disposition_header(False, safe.name)
    return response


def _require_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing {name}. Add to environment.env in the job search project.')
    return value


def _list_job_runs() -> list[Path]:
    if not JOB_SEARCH_OUTPUT_ROOT.exists():
        return []
    runs = [p for p in JOB_SEARCH_OUTPUT_ROOT.iterdir() if p.is_dir()]
    return sorted(runs, key=lambda p: p.name, reverse=True)


def _read_optional_file(path: Path) -> str:
    return path.read_text(encoding='utf-8').strip() if path.exists() else ''


def _job_id(lookup_key: str) -> str:
    return hashlib.sha256(lookup_key.encode('utf-8')).hexdigest()[:16]


def _normalize_apply_url(url: str) -> str:
    return lib.normalize_apply_url(url)


def _resolve_apply_url(job: dict) -> str:
    return lib.resolve_apply_url(job)


def _best_apply_url(job: dict) -> str:
    """Prefer a direct listing URL; re-resolve legacy EURES / search links."""
    resolved = _resolve_apply_url(job)
    if resolved:
        return resolved
    return _normalize_apply_url(
        (job.get('apply_url') or job.get('applyUrl') or job.get('url') or job.get('link') or '').strip(),
    )


def _django_cv_link(slug: str | None = None, label: str = 'General CV') -> dict:
    slug = slug or DEFAULT_CV_SLUG
    return {
        'slug': slug,
        'label': label,
        'url': reverse('cv_variant', args=[slug]),
        'standalone': False,
    }


def _standalone_cv_link(slug: str, label: str) -> dict:
    return {
        'slug': slug,
        'label': label,
        'url': reverse('cv_standalone', args=[slug]),
        'standalone': True,
    }


def _suggest_cv_profile(title: str, description: str = '') -> dict:
    t = (title or '').lower()
    stub = {'title': title or '', 'description': description or ''}
    if any(
        k in t
        for k in (
            'support', 'helpdesk', 'service desk', 'technical support',
            'it support', 'technician', 'desktop support',
        )
    ):
        return _standalone_cv_link('support-technician', 'Support Technician CV')
    if any(k in t for k in ('teacher', 'lærer', 'pedagog', 'counsel', 'karriere', 'spanish', 'norwegian')):
        return _standalone_cv_link('graduate-trainee', 'Graduate Trainee CV')
    if lib.is_it_focused_job(stub):
        return _standalone_cv_link('python-developer', 'Python / Backend Developer CV')
    return _standalone_cv_link('python-developer', 'Python / Backend Developer CV')


def _tailored_cv_path(job_id: str) -> Path:
    safe = hashlib.sha256(job_id.encode('utf-8')).hexdigest()[:24]
    return TAILORED_CV_DIR / f'{safe}.html'


def _ensure_tailored_cv_dir() -> None:
    TAILORED_CV_DIR.mkdir(parents=True, exist_ok=True)


def _tailored_cv_url(job_id: str) -> str:
    try:
        return reverse('job_tailored_cv', args=[job_id])
    except Exception:
        return f'/jobs/tailored-cv/{job_id}/'


def _tailored_cover_path(job_id: str) -> Path:
    safe = hashlib.sha256(job_id.encode('utf-8')).hexdigest()[:24]
    return TAILORED_CV_DIR / f'{safe}-cover.html'


def _tailored_cover_url(job_id: str) -> str:
    try:
        return reverse('job_tailored_cover_letter', args=[job_id])
    except Exception:
        return f'/jobs/tailored-cover/{job_id}/'


def _job_materials_meta_list(job_id: str) -> dict:
    """Materials flags for list cards — skip per-job disk checks (detail view loads full meta)."""
    return {
        'has_tailored_cv': False,
        'has_tailored_cover_letter': False,
        'tailored_cv_url': '',
        'tailored_cover_letter_url': '',
    }


def _job_materials_meta(row: dict) -> dict:
    run_name = row.get('run_name') or ''
    folder_name = row.get('folder_name') or ''
    job_id = row.get('job_id') or ''
    tailored_path = _tailored_cv_path(job_id) if job_id else None
    cover_path = _tailored_cover_path(job_id) if job_id else None
    has_tailored_cv = bool(tailored_path and tailored_path.is_file())
    has_tailored_cover_letter = bool(cover_path and cover_path.is_file())
    if not run_name or not folder_name:
        return {
            'has_resume': False,
            'has_cover_letter': False,
            'has_tailored_cv': has_tailored_cv,
            'has_tailored_cover_letter': has_tailored_cover_letter,
            'resume_preview': '',
            'cover_preview': '',
            'resume_pdf_url': '',
            'cover_letter_pdf_url': '',
            'tailored_cv_url': _tailored_cv_url(job_id) if has_tailored_cv else '',
            'tailored_cover_letter_url': _tailored_cover_url(job_id) if has_tailored_cover_letter else '',
        }
    folder = JOB_SEARCH_OUTPUT_ROOT / run_name / folder_name
    resume_txt = folder / 'tailored_resume.txt'
    cover_txt = folder / 'cover_letter.txt'
    resume_pdf = folder / 'tailored_resume.pdf'
    cover_pdf = folder / 'cover_letter.pdf'
    resume_preview = ''
    cover_preview = ''
    if resume_txt.exists():
        resume_preview = resume_txt.read_text(encoding='utf-8')[:1200]
    if cover_txt.exists():
        cover_preview = cover_txt.read_text(encoding='utf-8')[:1200]
    return {
        'has_resume': resume_txt.exists() or resume_pdf.exists(),
        'has_cover_letter': cover_txt.exists() or cover_pdf.exists(),
        'has_tailored_cv': has_tailored_cv,
        'has_tailored_cover_letter': has_tailored_cover_letter,
        'resume_preview': resume_preview,
        'cover_preview': cover_preview,
        'resume_pdf_url': (
            reverse('job_material_pdf', args=[run_name, folder_name, 'resume'])
            if resume_pdf.exists() else ''
        ),
        'cover_letter_pdf_url': (
            reverse('job_material_pdf', args=[run_name, folder_name, 'cover_letter'])
            if cover_pdf.exists() else ''
        ),
        'tailored_cv_url': _tailored_cv_url(job_id) if has_tailored_cv else '',
        'tailored_cover_letter_url': _tailored_cover_url(job_id) if has_tailored_cover_letter else '',
    }


def _row_blob(row: dict) -> str:
    return f"{row.get('title', '')} {row.get('company', '')} {row.get('description', '')}"


def _passes_browse_filters(
    row: dict,
    *,
    english_ok: bool,
    entry_only: bool,
    program: str,
) -> bool:
    blob = _row_blob(row)
    title = row.get('title') or ''
    if english_ok and lib.hard_german_required(blob):
        return False
    if entry_only and lib.SENIOR_EXCLUDE.search(blob) and not lib.JUNIOR_SIGNAL.search(blob):
        return False
    if program == 'trainee' and not lib.TRAINEE_PROGRAM_SIGNAL.search(blob):
        return False
    if program == 'werkstudent' and not lib.WERKSTUDENT_SIGNAL.search(blob):
        return False
    return True


def _is_full_match_row(row: dict) -> bool:
    if not row.get('scored'):
        return False
    match = row.get('match') or {}
    if match.get('logistics_ok') is False or match.get('dealbreakers'):
        return False
    if not lib.is_full_requirement_match(match):
        return False
    score = int(row.get('match_score') or match.get('match_score') or 0)
    return score >= DISPLAY_MIN_SCORE


def _is_degree_ready_row(row: dict) -> bool:
    if not row.get('scored'):
        return False
    blob = _row_blob(row)
    title = row.get('title') or ''
    match = row.get('match') or {}
    return lib.is_degree_requirement_met(match, blob=blob, title=title)


def _is_it_good_row(row: dict) -> bool:
    return _is_it_row(row) and _is_good_match_row(row)


def _is_non_it_good_row(row: dict) -> bool:
    return _is_non_it_degree_row(row) and _is_good_match_row(row)


def _sort_browse_rows(rows: list[dict]) -> list[dict]:
    """Best matches first; poor scores last; unscored in the middle."""

    def _tier(row: dict) -> int:
        score = int(row.get('match_score') or 0)
        if _is_good_match_row(row):
            return 0
        if not row.get('scored'):
            return 1
        if score < LIST_MIN_SCORE:
            return 3
        return 2

    return sorted(
        rows,
        key=lambda row: (
            _tier(row),
            -(row.get('match_score') or 0),
            row.get('title') or '',
        ),
    )


def _is_listable_in_all_view(row: dict) -> bool:
    """All jobs tab: show unscored + decent scores; hide obvious mismatches (0–29%)."""
    if not row.get('scored'):
        return True
    score = row.get('match_score')
    if score is None:
        return True
    return int(score) >= LIST_MIN_SCORE


def _scoring_priority(job: dict) -> tuple:
    """Score teaching & education roles before counseling/service listings."""
    stub = {
        'title': job.get('title') or '',
        'description': job.get('description') or job.get('descriptionText') or '',
    }
    if lib.is_it_focused_job(stub):
        bucket = 0
    elif lib.is_non_it_degree_job(stub):
        bucket = 1
    else:
        bucket = 2
    return (bucket, (stub['title'] or '').lower())


def _is_non_it_degree_row(row: dict) -> bool:
    if _is_it_row(row):
        return False
    return lib.is_non_it_degree_job({
        'title': row.get('title') or '',
        'description': row.get('description') or row.get('description_preview') or '',
        'company': row.get('company') or '',
        'location': row.get('location') or '',
    })


def _is_it_row(row: dict) -> bool:
    return lib.is_it_focused_job({
        'title': row.get('title') or '',
        'description': row.get('description') or row.get('description_preview') or '',
    })


def _career_branch(row: dict) -> str:
    if _is_it_row(row):
        return 'it'
    if _is_non_it_degree_row(row):
        return 'non_it'
    return 'other'


def _row_career_bucket(row: dict) -> int:
    """Sort key: non-IT degree roles before other, IT last."""
    if _is_it_row(row):
        return 2
    if _is_non_it_degree_row(row):
        return 0
    return 1


def _qualification_label(row: dict) -> str:
    if not row.get('scored'):
        return 'Awaiting score'
    match = row.get('match') or {}
    score = int(row.get('match_score') or 0)
    if _is_full_match_row(row):
        return 'Full match'
    if lib.is_full_requirement_match(match) and score < DISPLAY_MIN_SCORE:
        return 'Requirements met'
    if _is_degree_ready_row(row):
        return 'Degree-ready'
    if score >= DISPLAY_MIN_SCORE and match.get('recommendation') in ('apply', 'review'):
        return 'Good match'
    if score >= DISPLAY_MIN_SCORE:
        return 'Good match'
    return f'{score}% match'


def _job_lookup_key(job: dict, *, title: str = '', company: str = '') -> str:
    url = _best_apply_url(job)
    if url:
        return url
    if not title or not company:
        _, _, title, company = lib.job_text_fields(job)
    return f'{company}|{title}'.lower()


def _cache_job_to_display(job: dict) -> dict:
    desc, _, title, company = lib.job_text_fields(job)
    apply_url = _best_apply_url(job)
    lookup_key = _job_lookup_key(job, title=title, company=company)
    location = job.get('location') or job.get('locationName') or ''
    return {
        'job_id': _job_id(lookup_key),
        'title': title or 'Unknown title',
        'company': company or 'Unknown company',
        'location': location,
        'country': applied_jobs.infer_country(job, location=location),
        'apply_url': apply_url,
        'source': job.get('source') or job.get('provider') or '',
        'remote': bool(job.get('workRemoteAllowed') or job.get('remote')),
        'description': desc or '',
        'description_preview': (desc or '')[:300],
        'lookup_key': lookup_key,
    }


def _find_cached_job_by_id(job_id: str) -> dict | None:
    """Resolve a job from disk cache and in-progress live search results."""
    try:
        cached = _load_market_cached_jobs()
    except Exception:
        cached = []
    for job in cached:
        card = _cache_job_to_display(job)
        if card['job_id'] == job_id:
            return card
    try:
        live_jobs = lib.load_live_jobs().get('jobs') or []
    except Exception:
        live_jobs = []
    for job in live_jobs:
        card = _cache_job_to_display(job)
        if card['job_id'] == job_id:
            return card
    return None


def _job_context_from_snapshot(snap: dict) -> tuple[dict, dict, dict, dict, str] | tuple[None, ...]:
    """Build AI context from the job payload the browser already has (fallback when cache lags)."""
    job_id = str(snap.get('job_id') or '').strip()
    if not job_id:
        return None, None, None, None, ''
    title = str(snap.get('title') or 'Unknown title')
    company = str(snap.get('company') or 'Unknown company')
    location = str(snap.get('location') or '')
    description = str(snap.get('description') or '')
    apply_url = _best_apply_url(snap)
    card = {
        'job_id': job_id,
        'title': title,
        'company': company,
        'location': location,
        'country': snap.get('country') or applied_jobs.infer_country(location=location),
        'apply_url': apply_url,
        'description': description,
    }
    job_for_ai = {
        'title': title,
        'company': company,
        'location': location,
        'description': description,
        'applyUrl': apply_url,
    }
    match_detail = snap.get('match_detail') if isinstance(snap.get('match_detail'), dict) else {}
    match: dict = {}
    if snap.get('match_score') is not None:
        match['match_score'] = snap.get('match_score')
    if snap.get('recommendation'):
        match['recommendation'] = snap.get('recommendation')
    if snap.get('ai_summary'):
        match['ai_summary'] = snap.get('ai_summary')
    if match_detail:
        for key in (
            'reasoning', 'title_vs_requirements_note', 'must_have_met_count',
            'must_have_total', 'required_met', 'required_missing', 'dealbreakers',
            'requirements_analysis',
        ):
            if match_detail.get(key) is not None:
                match[key] = match_detail[key]
    base_slug = _suggest_cv_profile(title, description)['slug']
    if base_slug == 'professional' or base_slug not in ROLE_CVS:
        base_slug = next(iter(ROLE_CVS), DEFAULT_CV_SLUG)
    return card, job_for_ai, match, {}, base_slug


def _remember_job_snapshot(snap: dict, *, job_id: str) -> None:
    """Persist a browser-provided job into live cache so later lookups succeed."""
    try:
        title = str(snap.get('title') or '').strip()
        if not title:
            return
        raw = {
            'title': title,
            'company': str(snap.get('company') or ''),
            'location': str(snap.get('location') or ''),
            'description': str(snap.get('description') or ''),
            'applyUrl': _best_apply_url(snap),
            'source': str(snap.get('source') or ''),
            'remote': bool(snap.get('remote')),
        }
        live = lib.load_live_jobs()
        jobs = list(live.get('jobs') or [])
        if any(_cache_job_to_display(j)['job_id'] == job_id for j in jobs):
            return
        jobs.append(raw)
        lib.save_live_jobs(jobs, sources=live.get('sources') or [])
    except Exception:
        pass


def _append_job_to_cache(job: dict) -> tuple[str, bool]:
    """Add imported job to disk cache. Returns (job_id, created_new)."""
    lookup_key = _job_lookup_key(job)
    job_id = _job_id(lookup_key)
    try:
        cached = list(lib.load_cached_jobs())
    except Exception:
        cached = []
    for existing in cached:
        if _job_lookup_key(existing) == lookup_key:
            return job_id, False
    entry = {
        'title': job.get('title') or 'Imported job',
        'company': job.get('company') or job.get('companyName') or 'Unknown company',
        'location': job.get('location') or job.get('locationName') or '',
        'description': job.get('description') or job.get('descriptionText') or '',
        'url': job.get('url') or job.get('applyUrl') or '',
        'applyUrl': job.get('applyUrl') or job.get('url') or '',
        'source': job.get('source') or 'Imported link',
        'provider': job.get('provider') or 'Imported',
        'refnr': job.get('refnr') or '',
        'workRemoteAllowed': bool(job.get('remote') or job.get('workRemoteAllowed')),
    }
    cached.append(entry)
    lib.save_jobs_cache(cached)
    _STATS_CACHE['at'] = 0.0
    _invalidate_slim_jobs_cache()
    _MARKET_DATA_CACHE['at'] = 0.0
    return job_id, True


def _score_single_imported_job(job: dict) -> dict | None:
    api_key = os.getenv('MISTRAL_API_KEY', '').strip()
    if not api_key:
        return None
    cv = lib.load_cv()
    profile = lib.load_profile()
    match = lib.match_job(api_key, cv, job, profile)
    _, _, title, company = lib.job_text_fields(job)
    runs = _list_job_runs()
    if runs:
        run_dir = runs[0]
    else:
        run_id = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        run_dir = JOB_SEARCH_OUTPUT_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
    lib.write_job_output(run_dir, job, title, company, match, None)
    _invalidate_scored_lookup_cache()
    _STATS_CACHE['at'] = 0.0
    _MARKET_DATA_CACHE['at'] = 0.0
    return match


def _job_payload_for_imported(job: dict, *, match: dict | None = None) -> dict:
    card = _cache_job_to_display(job)
    row = {
        **card,
        'scored': bool(match),
        'match': lib.localize_match_for_display(match or {}),
        'match_score': int((match or {}).get('match_score') or 0) if match else None,
        'recommendation': (match or {}).get('recommendation', ''),
        'ai_summary': ((match or {}).get('reasoning') or '')[:500],
        'folder_name': '',
        'run_name': '',
        'keyword_hint': '',
    }
    if match:
        row['match_score'] = int(match.get('match_score') or 0)
    return _row_to_job_payload(row)


@require_POST
def jobs_score_one(request):
    """Score a single job with AI (urgent) without waiting for bulk Score AI."""
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    job_id = str(body.get('job_id') or '').strip()
    if not job_id:
        return JsonResponse({'ok': False, 'error': 'job_id required'}, status=400)

    status = pstatus.read_status()
    if status.get('state') == 'running' and (status.get('phase') or '') == 'score':
        return JsonResponse({
            'ok': False,
            'error': 'Bulk scoring is running — wait for it to finish or click Cancel.',
        }, status=409)

    if not os.getenv('MISTRAL_API_KEY', '').strip():
        return JsonResponse({'ok': False, 'error': 'MISTRAL_API_KEY missing on server.'}, status=503)

    job = _find_cached_job_by_id(job_id)
    if not job:
        snap = body.get('job') if isinstance(body.get('job'), dict) else {}
        if snap:
            title = str(snap.get('title') or '').strip()
            if title:
                job = {
                    'title': title,
                    'company': str(snap.get('company') or ''),
                    'location': str(snap.get('location') or ''),
                    'description': str(snap.get('description') or ''),
                    'applyUrl': str(
                        snap.get('apply_url')
                        or snap.get('applyUrl')
                        or snap.get('url')
                        or ''
                    ),
                    'source': str(snap.get('source') or ''),
                    'remote': bool(snap.get('remote')),
                }
                _remember_job_snapshot(snap, job_id=job_id)
    if not job:
        return JsonResponse(
            {
                'ok': False,
                'error': 'Job not found in server cache yet. Refresh once or run Search, then try Score again.',
            },
            status=404,
        )

    try:
        match = _score_single_imported_job(job)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)

    if not match:
        return JsonResponse({'ok': False, 'error': 'Scoring failed.'}, status=500)

    payload = _job_payload_for_imported(job, match=match)
    return JsonResponse({'ok': True, 'job': payload})


@require_POST
def jobs_import_url(request):
    """Import a job from an external posting URL and optionally score it."""
    try:
        return _jobs_import_url_impl(request)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)


def _jobs_import_url_impl(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    raw_url = str(body.get('url') or '').strip()
    if not raw_url:
        return JsonResponse({'ok': False, 'error': 'Paste a job posting URL.'}, status=400)

    score_now = body.get('score', True)
    api_key = os.getenv('MISTRAL_API_KEY', '').strip()
    try:
        job = lib.import_job_from_url(raw_url, api_key=api_key)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)[:300]}, status=400)

    job_id, created = _append_job_to_cache(job)
    match = None
    if score_now and api_key:
        try:
            match = _score_single_imported_job(job)
        except Exception as exc:
            return JsonResponse({
                'ok': True,
                'job': _job_payload_for_imported(job),
                'job_id': job_id,
                'created': created,
                'scored': False,
                'warning': f'Job added but scoring failed: {exc}',
            })

    payload = _job_payload_for_imported(job, match=match)
    return JsonResponse({
        'ok': True,
        'job': payload,
        'job_id': job_id,
        'created': created,
        'scored': bool(match),
        'message': 'Job added' + (' and scored' if match else ''),
    })


def _resolve_job_for_materials(body: dict) -> tuple[dict, dict, dict, dict, str] | tuple[None, ...]:
    """Resolve job from server cache, live search, or browser snapshot."""
    job_id = str(body.get('job_id') or '').strip()
    if not job_id:
        return None, None, None, None, ''

    ctx = _job_context_for_ai(job_id)
    if ctx[0]:
        return ctx

    snap = body.get('job')
    if isinstance(snap, dict) and (snap.get('title') or snap.get('company')):
        merged = {**snap, 'job_id': job_id}
        ctx = _job_context_from_snapshot(merged)
        if ctx[0]:
            _remember_job_snapshot(merged, job_id=job_id)
            return ctx

    return None, None, None, None, ''


def _scored_lookup_keys(meta: dict) -> list[str]:
    """All keys that may match a cached listing (URL-first, then company|title)."""
    keys: list[str] = []
    primary_url = _normalize_apply_url(
        meta.get('apply_url') or meta.get('applyUrl') or meta.get('url') or meta.get('link') or '',
    )
    primary = _job_lookup_key(
        {
            'applyUrl': primary_url,
            'link': meta.get('link') or '',
            'url': meta.get('url') or '',
        },
        title=meta.get('title', ''),
        company=meta.get('company', ''),
    )
    if primary:
        keys.append(primary)
    alt = f"{meta.get('company', '')}|{meta.get('title', '')}".lower()
    if alt and alt not in keys:
        keys.append(alt)
    return keys


def _build_scored_lookup(run_dir: Path | None) -> dict[str, dict]:
    """Map cache job keys → scored match.json payload (+ folder for detail links)."""
    if not run_dir or not run_dir.is_dir():
        return {}
    lookup: dict[str, dict] = {}
    for folder in run_dir.iterdir():
        if not folder.is_dir():
            continue
        match_file = folder / 'match.json'
        if not match_file.exists():
            continue
        try:
            meta = json.loads(match_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        if lib.is_legacy_match_payload(meta):
            continue
        payload = {
            **meta,
            'folder_name': folder.name,
            'run_name': run_dir.name,
        }
        for key in _scored_lookup_keys(meta):
            lookup[key] = payload
    return lookup


def _merged_scored_lookup(preferred_run: Path | None = None) -> dict[str, dict]:
    """Combine scores from every run (cached briefly — speeds up every page load)."""
    runs = _list_job_runs()
    cache_key = '|'.join(r.name for r in runs)
    if preferred_run and preferred_run.is_dir():
        lookup = dict(_SCORED_LOOKUP_CACHE.get('lookup') or {})
        if _SCORED_LOOKUP_CACHE.get('key') != cache_key:
            lookup = {}
            for run in sorted(runs, key=lambda p: p.name):
                lookup.update(_build_scored_lookup(run))
        lookup.update(_build_scored_lookup(preferred_run))
        return lookup
    if _SCORED_LOOKUP_CACHE.get('key') == cache_key and _SCORED_LOOKUP_CACHE.get('lookup'):
        return dict(_SCORED_LOOKUP_CACHE['lookup'])
    lookup: dict[str, dict] = {}
    for run in sorted(runs, key=lambda p: p.name):
        lookup.update(_build_scored_lookup(run))
    _SCORED_LOOKUP_CACHE['key'] = cache_key
    _SCORED_LOOKUP_CACHE['lookup'] = lookup
    return dict(lookup)


def _invalidate_scored_lookup_cache() -> None:
    _SCORED_LOOKUP_CACHE['key'] = ''
    _SCORED_LOOKUP_CACHE['lookup'] = {}
    _STATS_CACHE['at'] = 0.0
    _invalidate_slim_jobs_cache()


def _browse_base_rows(cached: list[dict], scored_lookup: dict[str, dict]) -> list[dict]:
    """All browse rows before URL/view filters — cached while job cache is unchanged."""
    cache_key = _slim_jobs_cache_key()
    if _BROWSE_BASE_ROWS_CACHE.get('key') == cache_key and _BROWSE_BASE_ROWS_CACHE.get('rows'):
        return list(_BROWSE_BASE_ROWS_CACHE['rows'])
    applied_id_set = applied_jobs.applied_ids()
    rows = [
        row for row in _build_unified_job_rows(cached, scored_lookup, hide_low_scores=False)
        if row['job_id'] not in applied_id_set
    ]
    _BROWSE_BASE_ROWS_CACHE['key'] = cache_key
    _BROWSE_BASE_ROWS_CACHE['rows'] = rows
    _BROWSE_BASE_ROWS_CACHE['stats'] = _market_tab_stats(rows)
    return rows


def _apply_scored_fields(row: dict, scored_lookup: dict[str, dict]) -> dict:
    scored = _lookup_scored_row(scored_lookup, row)
    if not scored:
        return row
    match = scored.get('match') or {}
    score = int(match.get('match_score') or 0) if match else None
    enriched = {
        **row,
        'scored': True,
        'match': match,
        'match_score': score,
        'recommendation': match.get('recommendation', ''),
        'ai_summary': (match.get('reasoning') or '')[:500],
        'folder_name': scored.get('folder_name', ''),
        'run_name': scored.get('run_name', ''),
        'qualified': _is_good_match_row({'scored': True, 'match': match}),
        'keyword_hint': '',
    }
    return enriched


def _fast_slim_jobs_payload(cached: list[dict], scored_lookup: dict[str, dict] | None = None) -> list[dict]:
    """Fast job list for live polling — avoids rebuilding unified rows."""
    scored_lookup = scored_lookup if scored_lookup is not None else _merged_scored_lookup(None)
    rows = [_apply_scored_fields(row, scored_lookup) for row in _fast_browse_rows_from_cache(cached)]
    return _build_slim_jobs_list(rows)


def _is_apply_ready_row(row: dict) -> bool:
    if not row.get('scored') or not _is_visible_job_row(row):
        return False
    match = row.get('match') or {}
    if lib.MATCH_MODE == 'broad':
        return lib.is_broad_opportunity(match)
    return lib.is_apply_list_job(match, row.get('apply_url') or '')


def _is_visible_job_row(row: dict) -> bool:
    """Hide AI-scored jobs below the display threshold (still in cache for records)."""
    if not row.get('scored'):
        return True
    score = row.get('match_score')
    if score is None:
        return True
    return int(score) >= DISPLAY_MIN_SCORE


def _is_good_match_row(row: dict) -> bool:
    """Scored jobs worth opening: at least DISPLAY_MIN_SCORE match."""
    if not row.get('scored'):
        return False
    if not _is_visible_job_row(row):
        return False
    match = row.get('match') or {}
    if match.get('logistics_ok') is False:
        return False
    score = int(match.get('match_score') or 0)
    if score < DISPLAY_MIN_SCORE:
        return False
    rec = match.get('recommendation') or 'skip'
    if rec in ('apply', 'review'):
        return True
    if score >= max(lib.BROAD_SCORE_MIN, DISPLAY_MIN_SCORE):
        return True
    return bool(match.get('qualified_to_apply') or match.get('broad_opportunity'))


def _keyword_fit_hint(job: dict, profile: dict | None = None) -> str:
    """Lightweight CV overlap hint for jobs not yet AI-scored."""
    try:
        desc, _, title, company = lib.job_text_fields(job)
        blob = f'{title} {company} {desc}'.lower()
        profile = profile if profile is not None else lib.load_profile()
        keywords = profile.get('all_search_keywords') or []
        if not keywords:
            clusters = profile.get('search_keyword_clusters') or {}
            for terms in clusters.values():
                keywords.extend(terms)
        hits = sum(1 for k in keywords if k and len(k) > 2 and k.lower() in blob)
        if hits >= 4:
            return f'CV keywords match ({hits}) — run AI to score'
        if hits >= 2:
            return f'Some CV overlap ({hits} keywords)'
    except Exception:
        pass
    return 'Not analyzed against your CV yet'


def _lookup_scored_row(scored_lookup: dict[str, dict], card: dict) -> dict | None:
    """Match cache card to scored output (URL key or company|title alias)."""
    keys = [card['lookup_key']]
    alt = f"{card['company']}|{card['title']}".lower()
    if alt not in keys:
        keys.append(alt)
    for key in keys:
        hit = scored_lookup.get(key)
        if hit:
            return hit
    return None


def _is_job_scored(job: dict, scored_lookup: dict[str, dict]) -> bool:
    card = _cache_job_to_display(job)
    return _lookup_scored_row(scored_lookup, card) is not None


def _unscored_cache_jobs(
    scored_lookup: dict[str, dict] | None = None,
    *,
    max_jobs: int = 0,
) -> tuple[list[dict], int]:
    """Jobs in cache that have no AI score yet (same pool as the job browser list)."""
    scored_lookup = scored_lookup if scored_lookup is not None else _merged_scored_lookup(None)
    try:
        cached = _load_market_cached_jobs()
    except Exception:
        return [], 0
    applied_ids = applied_jobs.applied_ids()
    unscored: list[dict] = []
    for job in cached:
        card = _cache_job_to_display(job)
        if card['job_id'] in applied_ids:
            continue
        if not _is_job_scored(job, scored_lookup):
            unscored.append(job)
    unscored.sort(key=_scoring_priority)
    total = len(unscored)
    if max_jobs > 0:
        unscored = unscored[:max_jobs]
    return unscored, total


def _market_tab_stats(browse_rows: list[dict] | None = None) -> dict:
    """Counts shown in the top bar and filter tabs (must match)."""
    if browse_rows is None:
        try:
            cached = _load_market_cached_jobs()
        except Exception:
            cached = []
        runs = _list_job_runs()
        run_dir = runs[0] if runs else None
        scored_lookup = _merged_scored_lookup(run_dir)
        browse_rows = _browse_base_rows(cached, scored_lookup)
        if _BROWSE_BASE_ROWS_CACHE.get('stats'):
            return dict(_BROWSE_BASE_ROWS_CACHE['stats'])
    visible = 0
    full_match = 0
    degree_ready = 0
    non_it = 0
    it = 0
    good = 0
    it_good = 0
    non_it_good = 0
    scored_total = 0
    hidden_low = 0
    for row in browse_rows:
        scored = bool(row.get('scored'))
        if scored:
            scored_total += 1
        if _is_visible_job_row(row):
            visible += 1
        elif scored:
            hidden_low += 1
        branch = row.get('career_branch')
        if branch not in ('it', 'non_it', 'other'):
            branch = _career_branch(row)
            row['career_branch'] = branch
        if branch == 'it':
            it += 1
        elif branch == 'non_it':
            non_it += 1
        if _is_good_match_row(row):
            good += 1
            if branch == 'it':
                it_good += 1
            elif branch == 'non_it':
                non_it_good += 1
        if _is_full_match_row(row):
            full_match += 1
        if _is_degree_ready_row(row):
            degree_ready += 1
    raw_total = len(browse_rows)
    return {
        'cache_total': visible,
        'cache_raw_total': raw_total,
        'hidden_low_score': hidden_low,
        'scored_total': scored_total,
        'unscored_total': raw_total - scored_total,
        'good_fits_total': good,
        'full_match_total': full_match,
        'degree_ready_total': degree_ready,
        'non_it_total': non_it,
        'it_total': it,
        'other_total': max(0, raw_total - it - non_it),
        'it_good_total': it_good,
        'non_it_good_total': non_it_good,
        'waiting_for_ai': max(0, raw_total - scored_total),
        'applied_total': len(applied_jobs.applied_ids()),
    }


def _build_unified_job_rows(
    cached: list[dict],
    scored_lookup: dict[str, dict],
    *,
    hide_low_scores: bool = True,
) -> list[dict]:
    """Every cached listing + AI score when available (one list, not 13 vs 124)."""
    rows = []
    seen_job_ids: set[str] = set()
    profile = lib.load_profile()
    for job in cached:
        card = _cache_job_to_display(job)
        if card['job_id'] in seen_job_ids:
            continue
        seen_job_ids.add(card['job_id'])
        scored = _lookup_scored_row(scored_lookup, card)
        match = (scored or {}).get('match') or {}
        score = int(match.get('match_score') or 0) if match else None
        rows.append({
            **card,
            'scored': bool(scored),
            'match': match,
            'match_score': score,
            'recommendation': match.get('recommendation', ''),
            'ai_summary': (match.get('reasoning') or '')[:500],
            'folder_name': (scored or {}).get('folder_name', ''),
            'run_name': (scored or {}).get('run_name', ''),
            'qualified': _is_good_match_row({'scored': bool(scored), 'match': match}),
            'keyword_hint': _keyword_fit_hint(job, profile) if not scored else '',
            'career_branch': _career_branch(card),
        })
    rows.sort(
        key=lambda row: (
            _row_career_bucket(row),
            0 if row['scored'] and row['qualified'] else 1,
            0 if row['scored'] else 2,
            -(row['match_score'] or 0),
            row['title'],
        ),
    )
    if hide_low_scores:
        return [row for row in rows if _is_visible_job_row(row)]
    return rows


def _load_job_folder(folder: Path) -> dict:
    match_file = folder / 'match.json'
    if not match_file.exists():
        return {}
    job = json.loads(match_file.read_text(encoding='utf-8'))
    if isinstance(job.get('match'), dict):
        job['match'] = lib.localize_match_for_display(job['match'])
    job['folder_name'] = folder.name
    job['description'] = _read_optional_file(folder / 'job_description.txt')
    job['tailored_resume'] = _read_optional_file(folder / 'tailored_resume.txt')
    job['cover_letter'] = _read_optional_file(folder / 'cover_letter.txt')
    job['positioning_notes'] = _read_optional_file(folder / 'positioning_notes.txt')
    return job


def _load_job_run(run_dir: Path) -> list[dict]:
    jobs = []
    for folder in sorted(run_dir.iterdir()):
        if folder.is_dir():
            job = _load_job_folder(folder)
            if job:
                jobs.append(job)
    return sorted(jobs, key=lambda j: -int(j.get('match', {}).get('match_score', 0)))


def _apify_configured() -> bool:
    """Token plus saved dataset(s) and/or APIFY_AUTO_RUN for live actor scrapes."""
    lib.load_env_files()
    if not os.getenv('APIFY_TOKEN', '').strip():
        return False
    if os.getenv('APIFY_AUTO_RUN', '').strip().lower() in ('1', 'true', 'yes', 'on'):
        return True
    if lib.parse_apify_dataset_specs():
        return True
    return bool(os.getenv('APIFY_DATASET_ID', '').strip())


def _check_env_vars() -> dict:
    """Check which env vars are configured."""
    lib.load_env_files()
    return {
        'apify_token': bool(os.getenv('APIFY_TOKEN', '').strip()),
        'apify_dataset': _apify_configured(),
        'apify_auto_run': os.getenv('APIFY_AUTO_RUN', '').strip().lower() in ('1', 'true', 'yes', 'on'),
        'mistral_key': bool(os.getenv('MISTRAL_API_KEY', '').strip()),
    }


def _get_recent_runs(limit=5) -> list[dict]:
    """Get metadata for recent runs."""
    runs = _list_job_runs()[:limit]
    recent = []
    for run in runs:
        try:
            summary_file = run / 'summary.json'
            if summary_file.exists():
                results = json.loads(summary_file.read_text(encoding='utf-8'))
                recent.append({
                    'name': run.name,
                    'date': run.name,
                    'total': len(results),
                    'apply': sum(1 for r in results if r.get('recommendation') == 'apply'),
                    'review': sum(1 for r in results if r.get('recommendation') == 'review'),
                    'skip': sum(1 for r in results if r.get('recommendation') == 'skip'),
                })
        except Exception:
            pass
    return recent


def _get_cache_info() -> dict:
    path = getattr(lib, 'JOBS_CACHE_PATH', None)
    if not path or not path.exists():
        return {
            'exists': False,
            'count': 0,
            'updated': None,
            'path': str(path) if path else 'unknown',
        }

    try:
        jobs = json.loads(path.read_text(encoding='utf-8'))
        count = len(jobs) if isinstance(jobs, list) else 0
    except Exception:
        count = 0

    return {
        'exists': True,
        'count': count,
        'updated': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'path': str(path),
    }


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if 'APIFY_TOKEN' in text or 'APIFY_DATASET_ID' in text:
        return 'Add APIFY_TOKEN and APIFY_DATASET_ID to your .env file, then restart the server.'
    if 'MISTRAL_API_KEY' in text or 'Missing MISTRAL' in text:
        return 'Add MISTRAL_API_KEY to your .env file, then restart the server.'
    if 'No cache at' in text or 'Cache empty' in text:
        return 'No job cache yet — click Refresh listings first.'
    if 'Dataset empty' in text:
        return 'Apify dataset returned no jobs. Check APIFY_DATASET_ID or use Refresh again.'
    if 'Mistral error' in text:
        return f'AI scoring failed: {text[:200]}'
    if 'timeout' in text.lower():
        return 'Request timed out. Lower max jobs in Control Panel (try 5–10) and run again.'
    return text[:300] if len(text) > 300 else text


def _dashboard_redirect(
    message: str = '',
    *,
    error: str = '',
    extra: str = '',
    view: str = 'all',
) -> str:
    url = reverse('jobs_market')
    params = [f'view={view}']
    if message:
        params.append(f'message={quote_plus(message)}')
    if error:
        params.append(f'error={quote_plus(error)}')
    if extra:
        params.append(extra)
    return f'{url}?{"&".join(params)}'


def _load_market_cached_jobs() -> list[dict]:
    """Cache on disk; during search/score keep showing saved jobs and merge live partial results."""
    cached: list[dict] = []
    try:
        cached = list(lib.load_cached_jobs())
    except Exception:
        cached = []
    status = pstatus.read_status()
    if status.get('state') != 'running':
        return cached
    live_jobs = lib.load_live_jobs().get('jobs') or []
    if not live_jobs:
        return cached
    if not cached:
        return list(live_jobs)
    by_key: dict[str, dict] = {}
    for job in cached:
        by_key[_job_lookup_key(job)] = job
    for job in live_jobs:
        by_key[_job_lookup_key(job)] = job
    return list(by_key.values())


def _apply_browse_url_filters(
    rows: list[dict],
    *,
    location_query: str = '',
    query: str = '',
    source_query: str = '',
    remote_only: bool = False,
    english_ok: bool = False,
    entry_only: bool = False,
    program: str = '',
) -> list[dict]:
    filtered: list[dict] = []
    for row in rows:
        if not _passes_browse_filters(row, english_ok=english_ok, entry_only=entry_only, program=program):
            continue
        if location_query and location_query.lower() not in row['location'].lower():
            continue
        if source_query and source_query not in row['source'].lower():
            continue
        if remote_only and not row['remote']:
            continue
        if query:
            blob = (
                f"{row['title']} {row['company']} {row['location']} "
                f"{row['description_preview']} {row['ai_summary']}"
            ).lower()
            if query not in blob:
                continue
        filtered.append(row)
    return filtered


def _filter_rows_for_market_view(rows: list[dict], view: str, browse_rows: list[dict]) -> list[dict]:
    if view == 'full':
        return [row for row in rows if _is_full_match_row(row)]
    if view == 'degree':
        return [row for row in rows if _is_degree_ready_row(row)]
    if view == 'non_it':
        return [row for row in rows if _is_non_it_degree_row(row)]
    if view == 'it':
        return [row for row in rows if _is_it_row(row)]
    if view == 'it_good':
        return [row for row in rows if _is_it_good_row(row)]
    if view == 'non_it_good':
        return [row for row in rows if _is_non_it_good_row(row)]
    if view == 'good':
        return [row for row in rows if _is_good_match_row(row)]
    if view == 'unscored':
        return [row for row in rows if not row['scored']]
    if view == 'all':
        return [row for row in browse_rows if _is_listable_in_all_view(row)]
    return list(rows)


def _normalize_market_view(raw_view: str) -> str:
    view = (raw_view or 'all').strip().lower()
    if view in ('picks', 'broad', 'apply', 'strong', 'matches', 'review', 'scored'):
        return 'good'
    if view in ('unanalyzed', 'waiting', 'new'):
        return 'unscored'
    if view in ('non_it', 'it', 'full', 'degree', 'good', 'unscored', 'all', 'applied', 'it_good', 'non_it_good'):
        return view
    return 'all'


_OPTIONAL_EMPTY_SOURCE_MARKERS = (
    'stepstone rss',
    'indeed rss',
    'adzuna rss',
    'remote jobs rss',
    'remotive api',
)


def _source_issues_for_ui(diagnostics: dict | None) -> list[dict]:
    """Summarize failed or empty job sources for the browse page banner."""
    if not diagnostics:
        return []
    issues: list[dict] = []
    for src in diagnostics.get('sources') or []:
        if not isinstance(src, dict):
            continue
        status = str(src.get('status') or '').lower()
        count = int(src.get('count') or 0)
        if status == 'ok' and count > 0:
            continue
        if status not in ('error', 'empty', 'failed') and count == 0:
            status = 'empty'
        elif status not in ('error', 'empty', 'failed'):
            continue
        source_name = str(src.get('source') or 'Unknown')
        if status == 'empty' and any(m in source_name.lower() for m in _OPTIONAL_EMPTY_SOURCE_MARKERS):
            continue
        issues.append({
            'source': source_name[:80],
            'status': status,
            'error': str(src.get('error') or '')[:160],
            'count': count,
        })
    return issues[:8]


def _jobs_market_query(request) -> dict:
    """Shared job list logic for HTML page and JSON refresh during scoring."""
    cached = _load_market_cached_jobs()
    runs = _list_job_runs()
    selected_run = request.GET.get('run') or (runs[0].name if runs else '')
    run_dir = next((r for r in runs if r.name == selected_run), runs[0] if runs else None)
    scored_lookup = _merged_scored_lookup(run_dir)

    location_query = request.GET.get('location', '').strip()
    query = request.GET.get('q', '').strip().lower()
    source_query = request.GET.get('source', '').strip().lower()
    remote_only = request.GET.get('remote') == '1'
    english_ok = request.GET.get('english_ok') == '1'
    entry_only = request.GET.get('entry') == '1'
    program = request.GET.get('program', '').strip().lower()
    view = _normalize_market_view(request.GET.get('view', 'all'))
    if view == 'applied':
        return {'redirect': redirect(reverse('jobs_applied'))}

    applied_id_set = applied_jobs.applied_ids()
    browse_rows = _browse_base_rows(cached, scored_lookup)
    url_filtered_browse = _apply_browse_url_filters(
        browse_rows,
        location_query=location_query,
        query=query,
        source_query=source_query,
        remote_only=remote_only,
        english_ok=english_ok,
        entry_only=entry_only,
        program=program,
    )
    has_url_filters = any([
        location_query, query, source_query, remote_only, english_ok, entry_only, program,
    ])
    if has_url_filters:
        tab_stats = _market_tab_stats(url_filtered_browse)
    else:
        tab_stats = dict(_BROWSE_BASE_ROWS_CACHE.get('stats') or _market_tab_stats(url_filtered_browse))
    request._market_tab_stats = tab_stats

    rows = _filter_rows_for_market_view(url_filtered_browse, view, url_filtered_browse)

    filtered_rows = _sort_browse_rows(rows)
    master_rows = _sort_browse_rows(url_filtered_browse)

    selected_job_id = request.GET.get('job', '').strip()
    pipeline_status = pstatus.read_status()

    view_labels = {
        'non_it': 'Counseling & service',
        'non_it_good': 'Non-IT & degree-friendly · ready to apply',
        'it': 'IT & tech',
        'it_good': 'IT & tech · ready to apply',
        'full': 'Full match (50%+)',
        'degree': 'Degree-ready (scored)',
        'good': 'Good matches (50%+)',
        'unscored': 'Awaiting score',
        'all': 'All jobs',
        'applied': 'Jobs you applied to',
    }

    return {
        'redirect': None,
        'cached': cached,
        'runs': runs,
        'selected_run': selected_run,
        'view': view,
        'view_label': view_labels.get(view, view),
        'filtered_rows': filtered_rows,
        'master_rows': master_rows,
        'selected_job_id': selected_job_id,
        'tab_stats': tab_stats,
        'cache_total': tab_stats['cache_total'],
        'cache_raw_total': tab_stats.get('cache_raw_total', tab_stats['cache_total']),
        'hidden_low_score': tab_stats.get('hidden_low_score', 0),
        'scored_total': tab_stats['scored_total'],
        'unscored_total': tab_stats['unscored_total'],
        'good_fits_total': tab_stats['good_fits_total'],
        'full_match_total': tab_stats.get('full_match_total', 0),
        'degree_ready_total': tab_stats.get('degree_ready_total', 0),
        'non_it_total': tab_stats.get('non_it_total', 0),
        'it_total': tab_stats.get('it_total', 0),
        'it_good_total': tab_stats.get('it_good_total', 0),
        'non_it_good_total': tab_stats.get('non_it_good_total', 0),
        'other_total': tab_stats.get('other_total', 0),
        'location_query': location_query,
        'query': request.GET.get('q', ''),
        'source_query': request.GET.get('source', ''),
        'remote_only': remote_only,
        'english_ok': english_ok,
        'entry_only': entry_only,
        'program': program,
        'pipeline_status': pipeline_status,
        'pipeline_running': pstatus.is_running(),
        'resumable_run': _find_resumable_run(),
    }


def _get_saved_settings(request):
    saved = request.session.get('job_settings', {})
    return {
        'max_jobs': int(saved.get('max_jobs', DEFAULT_MAX_JOBS)),
        'min_score': int(saved.get('min_score', DEFAULT_MIN_SCORE)),
    }


def _load_profile():
    try:
        return lib.load_profile()
    except Exception:
        return {}


def _job_engine_available() -> bool:
    return JOB_SEARCH_ROOT.exists() and (JOB_SEARCH_ROOT / 'jobsearch.py').exists()


def _run_job_engine(action: str, extra_args=None) -> str:
    if not _job_engine_available():
        raise RuntimeError('Local job engine not found in workspace.')

    cmd = [sys.executable, 'jobsearch.py']
    if action == 'refresh':
        cmd.append('--refresh-cache')
    elif action == 'dry_run':
        cmd.extend(['--use-cache', '--dry-run'])
    elif action == 'generate':
        cmd.extend(['--use-cache', '--min-score', str(DEFAULT_MIN_SCORE)])
    else:
        raise ValueError('Unsupported external action')

    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd,
        cwd=str(JOB_ENGINE_ROOT),
        capture_output=True,
        text=True,
        timeout=1200,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'Exit {result.returncode}')
    return result.stdout.strip()


def _send_file_response(path: Path, filename: str) -> FileResponse:
    if not path.exists() or not path.is_file():
        raise Http404('File not found')
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=filename)


def _cv_page_context(profile) -> dict:
    section_links = [
        ('summary', 'Profile'),
        ('experience', 'Professional experience'),
        ('education', 'Education'),
        ('skills', 'Skills'),
        ('additional', 'Courses & references'),
    ]
    if profile.show_additional_experience and profile.additional_experience:
        section_links.insert(-1, ('additional-experience', 'Additional experience'))

    return {
        'cv': profile,
        'section_links': section_links,
        'job_search_url': reverse('jobs_market'),
        'cv_protected': bool(getattr(django_settings, 'CV_ACCESS_PASSWORD', '')),
    }


def cv_unlock(request):
    """Password gate for CV pages (when CV_ACCESS_PASSWORD is set)."""
    from .cv_access import (
        cv_password_enabled,
        record_unlock_failure,
        unlock_is_locked,
        unlock_lockout_remaining,
    )
    from .cv_i18n import ui

    next_url = request.POST.get('next') or request.GET.get('next') or reverse('cv_select')
    if not cv_password_enabled():
        return redirect(next_url)
    if cv_is_unlocked(request) and request.method != 'POST':
        return redirect(next_url)

    if unlock_is_locked(request):
        mins = max(1, unlock_lockout_remaining(request) // 60)
        return render(request, 'cvapp/cv_unlock.html', {
            'error': f'Too many failed attempts. Try again in about {mins} minute(s).',
            'next_url': next_url,
            'signed_out': False,
            'locked': True,
        })

    if request.method == 'POST':
        if check_cv_password(request.POST.get('password', '')):
            grant_cv_access(request)
            return redirect(next_url)
        record_unlock_failure(request)
        error = 'Incorrect password. Please try again.'
        if unlock_is_locked(request):
            mins = max(1, unlock_lockout_remaining(request) // 60)
            error = f'Too many failed attempts. Try again in about {mins} minute(s).'
        return render(request, 'cvapp/cv_unlock.html', {
            'error': error,
            'next_url': next_url,
            'signed_out': False,
            'locked': unlock_is_locked(request),
        })
    signed_out = request.GET.get('signed_out') == '1'
    return render(request, 'cvapp/cv_unlock.html', {
        'next_url': next_url,
        'signed_out': signed_out,
        'signed_out_msg': ui('en', 'signed_out'),
        'locked': False,
    })


def cv_gate(request):
    """Dashboard entry point — always checks password before the CV chooser."""
    blocked = ensure_cv_access(request)
    if blocked is not None:
        return blocked
    return redirect('cv_select')


def cv_logout(request):
    """Clear CV unlock session and return to the password screen."""
    revoke_cv_access(request)
    if getattr(django_settings, 'CV_ACCESS_PASSWORD', ''):
        return redirect(f"{reverse('cv_unlock')}?signed_out=1")
    return redirect('jobs_market')


def portfolio_home(request):
    """Personal site entry — job workspace (password gate via middleware)."""
    return redirect('jobs_market')


def robots_txt(request):
    """Tell crawlers and AI indexers to stay away from this personal site."""
    bots = (
        '*',
        'GPTBot',
        'ChatGPT-User',
        'Google-Extended',
        'Googlebot',
        'anthropic-ai',
        'ClaudeBot',
        'Claude-Web',
        'CCBot',
        'Bytespider',
        'Amazonbot',
        'FacebookBot',
        'meta-externalagent',
        'Applebot-Extended',
        'cohere-ai',
        'Diffbot',
        'Omgilibot',
        'PerplexityBot',
        'YouBot',
    )
    lines = []
    for bot in bots:
        lines.extend([f'User-agent: {bot}', 'Disallow: /', ''])
    body = '\n'.join(lines).rstrip() + '\n'
    return HttpResponse(body, content_type='text/plain; charset=utf-8')


def academic_transcript(request):
    """Full LADOK-style academic transcript (standalone HTML)."""
    from .cv_i18n import inject_lang_bar, inject_privacy_meta, lang_switcher_html, normalize_lang, translate_document_html
    from .standalone_cv_builder import rewrite_legacy_public_links

    path = Path(django_settings.BASE_DIR) / 'academic_transcript_improved.html'
    if not path.is_file():
        raise Http404('Academic transcript not found')
    lang = normalize_lang(request.GET.get('lang'))
    html = rewrite_legacy_public_links(path.read_text(encoding='utf-8'))
    html = translate_document_html(html, lang=lang, doc_kind='transcript')
    bar = lang_switcher_html(base_path='/transcript/', current_lang=lang)
    html = inject_privacy_meta(html)
    return HttpResponse(
        inject_lang_bar(html, bar_html=bar),
        content_type='text/html; charset=utf-8',
    )


@require_cv_access
def cv_select(request):
    """Choose which CV variant to view."""
    from .cv_i18n import SUPPORTED_LANGS, localized_role_cv, normalize_lang, picker_context
    from .standalone_cv import StandaloneCV

    lang = normalize_lang(request.GET.get('lang'))

    def _localized(cv: StandaloneCV) -> StandaloneCV:
        loc = localized_role_cv(cv.slug, label=cv.label, description=cv.description, lang=lang)
        return StandaloneCV(
            slug=cv.slug,
            label=loc['label'],
            description=loc['description'],
            filename=cv.filename,
            generated=cv.generated,
        )

    role_cvs = [_localized(c) for c in list_standalone_cvs() if c.slug != 'professional']
    professional_cv = _localized(get_standalone_cv('professional'))
    picker = picker_context(lang)
    return render(request, 'cvapp/cv_select.html', {
        'cv_profiles': list_cv_profiles(),
        'standalone_cvs': role_cvs,
        'professional_cv': professional_cv,
        'cv_lang': lang,
        'cv_langs': SUPPORTED_LANGS,
        'picker': picker,
    })


def cv_standalone(request, name):
    """Serve a standalone HTML CV (password-protected personal site)."""
    from .cv_i18n import inject_lang_bar, inject_privacy_meta, lang_switcher_html, normalize_lang, translate_document_html

    html = read_standalone_cv_html(name)
    lang = normalize_lang(request.GET.get('lang'))
    doc_kind = 'professional' if name == 'professional' else name
    html = translate_document_html(html, lang=lang, doc_kind=doc_kind)
    bar = lang_switcher_html(
        base_path=f'/cv/html/{name}/',
        current_lang=lang,
    )
    html = inject_lang_bar(html, bar_html=bar)
    html = inject_privacy_meta(html)
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@require_cv_access
def cv_variant(request, slug):
    """Full web CV for a specific role profile."""
    profile = get_cv_profile(slug)
    return render(request, profile.web_template, _cv_page_context(profile))


def cv_legacy_redirect(request, target):
    """Backward-compatible redirects from old /cv/ URLs."""
    if target == 'download':
        return redirect('cv_download_pdf', slug=DEFAULT_CV_SLUG)
    if target == 'print':
        return redirect('cv_page', slug=DEFAULT_CV_SLUG)
    return redirect('cv_select')


@require_cv_access
def cv_download_pdf(request, slug):
    """Download the CV as a PDF attachment."""
    profile = get_cv_profile(slug)
    try:
        pdf_bytes = build_cv_pdf_bytes(request, profile=profile)
    except RuntimeError as exc:
        return HttpResponse(str(exc), status=503, content_type='text/plain; charset=utf-8')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{profile.pdf_filename}"'
    return response


def dashboard_home(request):
    """Legacy home URL — job workspace is the Jobs page."""
    settings = _get_saved_settings(request)
    if request.method == 'POST' and 'max_jobs' in request.POST:
        try:
            settings['max_jobs'] = int(request.POST.get('max_jobs', DEFAULT_MAX_JOBS))
            settings['min_score'] = int(request.POST.get('min_score', DEFAULT_MIN_SCORE))
            request.session['job_settings'] = settings
            return redirect(_dashboard_redirect(message='Settings saved.'))
        except (ValueError, TypeError):
            return redirect(_dashboard_redirect(error='Invalid settings.'))

    query = request.GET.urlencode()
    target = reverse('jobs_market')
    if query:
        target = f'{target}?{query}'
    return redirect(target)


def _quick_market_stats(*, allow_slow: bool = True) -> dict:
    """Lightweight counts for live status bar (cached a few seconds)."""
    now = time.time()
    if now - _STATS_CACHE.get('at', 0) < _STATS_CACHE_TTL and _STATS_CACHE.get('data'):
        return dict(_STATS_CACHE['data'])
    if not allow_slow:
        try:
            raw = len(_load_market_cached_jobs())
        except Exception:
            raw = 0
        return {
            'cache_total': raw,
            'cache_raw_total': raw,
            'hidden_low_score': 0,
            'scored_total': 0,
            'unscored_total': raw,
            'good_fits_total': 0,
            'full_match_total': 0,
            'degree_ready_total': 0,
            'non_it_total': 0,
            'it_total': 0,
            'other_total': 0,
            'it_good_total': 0,
            'non_it_good_total': 0,
        }
    try:
        cached = _load_market_cached_jobs()
    except Exception:
        cached = []
    scored_lookup = _merged_scored_lookup(None)
    applied_ids = applied_jobs.applied_ids()
    rows = [
        row for row in _build_unified_job_rows(cached, scored_lookup, hide_low_scores=False)
        if row['job_id'] not in applied_ids
    ]
    data = _market_tab_stats(rows)
    _STATS_CACHE['at'] = now
    _STATS_CACHE['data'] = data
    return data


def jobs_status_api(request):
    """JSON status for live progress bar (no page reload)."""
    status = pstatus.read_status()
    running = status.get('state') == 'running'
    live = lib.load_live_jobs()
    elapsed = 0
    started = status.get('started_at')
    if started and status.get('state') == 'running':
        try:
            elapsed = int((datetime.now() - datetime.fromisoformat(started)).total_seconds())
        except ValueError:
            elapsed = 0
    total = int(status.get('total') or 0)
    progress = int(status.get('progress') or 0)
    percent = int(100 * progress / total) if total > 0 else 0
    latest = status.get('latest_jobs')
    if not latest:
        raw_live = live.get('jobs') or []
        latest = lib._jobs_for_live_feed(raw_live, limit=30) if raw_live else []
    live_count = int(status.get('live_count') or live.get('count') or len(latest))
    phase = status.get('phase') or ''
    if not phase and status.get('state') == 'running':
        label = (status.get('label') or '').lower()
        phase = 'score' if 'scor' in label else 'search'
    market = _quick_market_stats(allow_slow=not running)
    sources = []
    if phase == 'search':
        sources = status.get('sources') or live.get('sources') or []
    return JsonResponse({
        'state': status.get('state') or 'idle',
        'label': status.get('label') or '',
        'phase': phase,
        'message': status.get('message') or '',
        'progress': progress,
        'total': total,
        'percent': min(100, percent),
        'elapsed_seconds': elapsed,
        'error': status.get('error') or '',
        'live_count': live_count,
        'latest_jobs': latest[-30:],
        'sources': sources,
        'scored_total': market.get('scored_total', 0),
        'unscored_total': market.get('unscored_total', 0),
        'good_fits_total': market.get('good_fits_total', 0),
        'cache_raw_total': market.get('cache_raw_total', 0),
        'it_total': market.get('it_total', 0),
        'non_it_total': market.get('non_it_total', 0),
        'other_total': market.get('other_total', 0),
        'it_good_total': market.get('it_good_total', 0),
        'non_it_good_total': market.get('non_it_good_total', 0),
        'degree_ready_total': market.get('degree_ready_total', 0),
        'full_match_total': market.get('full_match_total', 0),
    })


def jobs_control(request):
    """Settings only — same page as home (no separate nav)."""
    if request.method == 'GET':
        return redirect(reverse('jobs_market') + '#settings')
    env_vars = _check_env_vars()
    cache_info = _get_cache_info()
    source_diagnostics = lib.load_source_diagnostics()
    last_run = _get_recent_runs(limit=1)[0] if _get_recent_runs(limit=1) else None
    free_sources = getattr(lib, 'ALTERNATIVE_SOURCES', [])
    settings = _get_saved_settings(request)
    profile = _load_profile()
    
    message = request.GET.get('message', '')
    error = request.GET.get('error', '')
    
    if request.method == 'POST' and 'max_jobs' in request.POST:
        try:
            settings['max_jobs'] = int(request.POST.get('max_jobs', DEFAULT_MAX_JOBS))
            settings['min_score'] = int(request.POST.get('min_score', DEFAULT_MIN_SCORE))
            request.session['job_settings'] = settings
            return redirect(_dashboard_redirect(message='Settings saved.'))
        except (ValueError, TypeError):
            return redirect(_dashboard_redirect(error='Invalid settings.'))

    return render(request, 'cvapp/jobs_control.html', {
        'max_jobs': settings['max_jobs'],
        'min_score': settings['min_score'],
        'web_max_jobs': WEB_MAX_JOBS,
        'match_mode': getattr(lib, 'MATCH_MODE', 'broad'),
        'jooble_configured': bool(os.getenv('JOOBLE_API_KEY', '').strip()),
        'apify_token': env_vars['apify_token'],
        'apify_dataset': env_vars['apify_dataset'],
        'apify_auto_run': env_vars.get('apify_auto_run', False),
        'source_mode': 'Free DE job portals',
        'source_ready': True,
        'mistral_key': env_vars['mistral_key'],
        'cache_info': cache_info,
        'last_run': last_run,
        'free_sources': free_sources,
        'source_diagnostics': source_diagnostics,
        'profile': profile,
        'job_engine_available': _job_engine_available(),
        'job_engine_path': str(JOB_ENGINE_ROOT),
        'message': message,
        'error': error,
    })


def jobs_external_refresh(request):
    if request.method != 'POST':
        return redirect('jobs_control')
    try:
        output = _run_job_engine('refresh')
        message = 'Local job engine cache refreshed successfully.'
        return redirect(f"{reverse('jobs_control')}?message={quote_plus(message)}")
    except Exception as exc:
        return redirect(f"{reverse('jobs_control')}?error={quote_plus(_friendly_error(exc))}")


def jobs_external_dry_run(request):
    if request.method != 'POST':
        return redirect('jobs_control')
    try:
        output = _run_job_engine('dry_run')
        message = 'Local job engine dry-run completed successfully.'
        return redirect(f"{reverse('jobs_control')}?message={quote_plus(message)}")
    except Exception as exc:
        return redirect(f"{reverse('jobs_control')}?error={quote_plus(_friendly_error(exc))}")


def jobs_external_generate(request):
    if request.method != 'POST':
        return redirect('jobs_control')
    try:
        output = _run_job_engine('generate')
        message = 'Local job engine full generation completed successfully.'
        return redirect(f"{reverse('jobs_control')}?message={quote_plus(message)}")
    except Exception as exc:
        return redirect(f"{reverse('jobs_control')}?error={quote_plus(_friendly_error(exc))}")


def job_material_pdf(request, run_name: str, folder_name: str, material_type: str):
    run_name = Path(run_name).name
    folder_name = Path(folder_name).name
    run_dir = JOB_SEARCH_OUTPUT_ROOT / run_name
    if not run_dir.exists() or not run_dir.is_dir():
        raise Http404('Job run not found')
    pdf_map = {
        'resume': 'tailored_resume.pdf',
        'cover_letter': 'cover_letter.pdf',
    }
    if material_type not in pdf_map:
        raise Http404('Unsupported download type')
    file_path = run_dir / folder_name / pdf_map[material_type]
    return _send_file_response(file_path, pdf_map[material_type])


def jobs_results(request):
    """Legacy URL — same data as Your jobs, scored-only view."""
    query = request.GET.copy()
    if 'view' not in query:
        query['view'] = 'scored'
    return redirect(f"{reverse('jobs_market')}?{query.urlencode()}")


def job_tailored_cv(request, job_id: str):
    """Serve AI-generated 2-page HTML CV for one job (print → PDF)."""
    path = _tailored_cv_path(job_id)
    if not path.is_file():
        raise Http404('Tailored CV not generated yet for this job')
    return HttpResponse(path.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')


def job_tailored_cover_letter(request, job_id: str):
    """Serve AI-generated HTML cover letter for one job (print → PDF)."""
    path = _tailored_cover_path(job_id)
    if not path.is_file():
        raise Http404('Tailored cover letter not generated yet for this job')
    return HttpResponse(path.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')


def _job_context_for_ai(job_id: str) -> tuple[dict, dict, dict, dict, str] | tuple[None, ...]:
    """Load cached job, match data, and suggested base CV slug for AI generation."""
    card = _find_cached_job_by_id(job_id)
    if not card:
        return None, None, None, None, ''
    runs = _list_job_runs()
    run_dir = runs[0] if runs else None
    scored_lookup = _merged_scored_lookup(run_dir)
    scored_row = _lookup_scored_row(scored_lookup, card)
    match = (scored_row or {}).get('match') or {}
    job_for_ai = {
        'title': card['title'],
        'company': card['company'],
        'location': card['location'],
        'description': card.get('description') or '',
        'applyUrl': card.get('apply_url') or '',
    }
    base_slug = _suggest_cv_profile(card['title'], card.get('description', ''))['slug']
    if base_slug == 'professional' or base_slug not in ROLE_CVS:
        base_slug = next(iter(ROLE_CVS), DEFAULT_CV_SLUG)
    return card, job_for_ai, match, scored_row or {}, base_slug


@require_POST
def jobs_generate_materials(request):
    """Generate tailored HTML CV and/or cover letter for one job via AI."""
    try:
        return _jobs_generate_materials_impl(request)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)


def _jobs_generate_materials_impl(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    job_id = str(body.get('job_id') or '').strip()
    if not job_id:
        return JsonResponse({'ok': False, 'error': 'job_id required'}, status=400)

    material = str(body.get('material') or 'cv').strip().lower()
    output_lang = str(body.get('lang') or 'auto').strip().lower()
    if output_lang not in ('auto', 'en', 'de', 'no'):
        output_lang = 'auto'

    if material not in VALID_MATERIAL_TYPES:
        return JsonResponse(
            {'ok': False, 'error': 'material must be cv, cover_letter, or both'},
            status=400,
        )

    card, job_for_ai, match, _scored_row, base_slug = _resolve_job_for_materials(body)
    if not card:
        return JsonResponse(
            {
                'ok': False,
                'error': (
                    'This job is not on the server yet. '
                    'Wait until Search shows Done, refresh the page (Ctrl+Shift+R), then click Create again.'
                ),
            },
            status=404,
        )

    lib.load_env_files()
    try:
        api_key = _require_env('MISTRAL_API_KEY')
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    cv = lib.load_cv()
    profile = lib.load_profile()
    response: dict = {'ok': True, 'material': material}

    if material in ('cv', 'both'):
        try:
            ai_payload = lib.generate_tailored_html_cv(
                api_key,
                cv,
                job_for_ai,
                match=match,
                profile=profile,
                base_slug=base_slug,
                output_language=output_lang,
            )
            html = build_ai_tailored_cv_html(base_slug, ai_payload)
        except Exception as exc:
            return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)

        out_path = _tailored_cv_path(job_id)
        out_path.write_text(html, encoding='utf-8')
        meta_path = out_path.with_suffix('.json')
        meta_path.write_text(
            json.dumps({
                'job_id': job_id,
                'title': card['title'],
                'company': card['company'],
                'base_slug': base_slug,
                'language': output_lang,
                'generated_at': datetime.now().isoformat(),
                'ai_payload': ai_payload,
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        response['tailored_cv_url'] = _tailored_cv_url(job_id)
        response['base_slug'] = base_slug
        response['label'] = ROLE_CVS.get(base_slug).label if base_slug in ROLE_CVS else 'Tailored CV'

    if material in ('cover_letter', 'both'):
        try:
            letter_payload = lib.generate_tailored_cover_letter(
                api_key,
                cv,
                job_for_ai,
                match=match,
                profile=profile,
                output_language=output_lang,
            )
            letter_html = build_cover_letter_html(
                job_title=card['title'],
                company=card['company'],
                location=card.get('location') or '',
                ai_payload=letter_payload,
            )
        except Exception as exc:
            return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)

        cover_path = _tailored_cover_path(job_id)
        cover_path.write_text(letter_html, encoding='utf-8')
        cover_meta = cover_path.with_suffix('.json')
        cover_meta.write_text(
            json.dumps({
                'job_id': job_id,
                'title': card['title'],
                'company': card['company'],
                'language': output_lang,
                'generated_at': datetime.now().isoformat(),
                'ai_payload': letter_payload,
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        response['tailored_cover_letter_url'] = _tailored_cover_url(job_id)

    return JsonResponse(response)


def _load_tailored_ai_payload(path: Path) -> tuple[dict, str]:
    """Return (ai_payload, base_slug) from sidecar JSON if present."""
    meta_path = path.with_suffix('.json')
    if not meta_path.is_file():
        return {}, 'python-developer'
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except Exception:
        return {}, 'python-developer'
    payload = meta.get('ai_payload') if isinstance(meta.get('ai_payload'), dict) else {}
    base_slug = str(meta.get('base_slug') or 'python-developer')
    return payload, base_slug


@require_POST
def jobs_refine_materials(request):
    """Revise tailored CV or cover letter using natural-language feedback."""
    try:
        return _jobs_refine_materials_impl(request)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)


def _jobs_refine_materials_impl(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    job_id = str(body.get('job_id') or '').strip()
    instruction = str(body.get('instruction') or body.get('message') or '').strip()
    material = str(body.get('material') or 'cv').strip().lower()
    output_lang = str(body.get('lang') or 'auto').strip().lower()
    if output_lang not in ('auto', 'en', 'de', 'no'):
        output_lang = 'auto'
    if not job_id:
        return JsonResponse({'ok': False, 'error': 'job_id required'}, status=400)
    if len(instruction) < 4:
        return JsonResponse({'ok': False, 'error': 'Tell the AI what to change (at least 4 characters).'}, status=400)
    if material not in REFINE_MATERIAL_TYPES:
        return JsonResponse({'ok': False, 'error': 'material must be cv or cover_letter'}, status=400)

    card, job_for_ai, match, _scored_row, base_slug = _resolve_job_for_materials(body)
    if not card:
        return JsonResponse(
            {
                'ok': False,
                'error': (
                    'This job is not on the server yet. '
                    'Wait until Search shows Done, refresh the page (Ctrl+Shift+R), then try again.'
                ),
            },
            status=404,
        )

    lib.load_env_files()
    try:
        api_key = _require_env('MISTRAL_API_KEY')
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    cv = lib.load_cv()
    profile = lib.load_profile()
    response: dict = {'ok': True, 'material': material}

    if material == 'cv':
        cv_path = _tailored_cv_path(job_id)
        current_payload, saved_slug = _load_tailored_ai_payload(cv_path)
        if saved_slug:
            base_slug = saved_slug
        try:
            ai_payload = lib.refine_tailored_html_cv(
                api_key,
                cv,
                job_for_ai,
                match=match,
                profile=profile,
                base_slug=base_slug,
                current_payload=current_payload or None,
                instruction=instruction,
                output_language=output_lang,
            )
            html = build_ai_tailored_cv_html(base_slug, ai_payload)
        except Exception as exc:
            return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)
        cv_path.write_text(html, encoding='utf-8')
        cv_path.with_suffix('.json').write_text(
            json.dumps({
                'job_id': job_id,
                'title': card['title'],
                'company': card['company'],
                'base_slug': base_slug,
                'language': output_lang,
                'generated_at': datetime.now().isoformat(),
                'ai_payload': ai_payload,
                'last_instruction': instruction[:500],
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        response['tailored_cv_url'] = _tailored_cv_url(job_id)
    else:
        cover_path = _tailored_cover_path(job_id)
        current_payload, _ = _load_tailored_ai_payload(cover_path)
        try:
            letter_payload = lib.refine_tailored_cover_letter(
                api_key,
                cv,
                job_for_ai,
                match=match,
                profile=profile,
                current_payload=current_payload or None,
                instruction=instruction,
                output_language=output_lang,
            )
            letter_html = build_cover_letter_html(
                job_title=card['title'],
                company=card['company'],
                location=card.get('location') or '',
                ai_payload=letter_payload,
            )
        except Exception as exc:
            return JsonResponse({'ok': False, 'error': _friendly_error(exc)}, status=500)
        cover_path.write_text(letter_html, encoding='utf-8')
        cover_path.with_suffix('.json').write_text(
            json.dumps({
                'job_id': job_id,
                'title': card['title'],
                'company': card['company'],
                'language': output_lang,
                'generated_at': datetime.now().isoformat(),
                'ai_payload': letter_payload,
                'last_instruction': instruction[:500],
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        response['tailored_cover_letter_url'] = _tailored_cover_url(job_id)

    return JsonResponse(response)


def _format_applied_date(iso_value: str) -> str:
    if not iso_value:
        return ''
    try:
        dt = datetime.fromisoformat(iso_value)
        return dt.strftime('%d %b %Y')
    except ValueError:
        return iso_value[:10]


def _applied_entries() -> tuple[list[dict], int]:
    entries = []
    for index, row in enumerate(applied_jobs.list_applied(), start=1):
        entries.append({
            **row,
            'number': index,
            'applied_date': _format_applied_date(row.get('applied_at', '')),
        })
    return entries, len(entries)


def _card_list_hint(row: dict, match: dict) -> str:
    """One-line English summary for compact job cards."""
    if row.get('scored') and match:
        text = (match.get('reasoning') or row.get('ai_summary') or '').strip()
        if text:
            return text[:160] + ('…' if len(text) > 160 else '')
        met = match.get('required_met') or []
        miss = match.get('required_missing') or []
        parts: list[str] = []
        if met:
            parts.append('Strengths: ' + ', '.join(str(x) for x in met[:3]))
        if miss:
            parts.append('Gaps: ' + ', '.join(str(x) for x in miss[:2]))
        if parts:
            return ' · '.join(parts)[:180]
    hint = (row.get('keyword_hint') or '').strip()
    if hint:
        return hint
    return 'Not scored yet — use Score AI for an English match summary'


def _recommendation_label(recommendation: str, *, scored: bool) -> str:
    if not scored:
        return ''
    rec = (recommendation or '').strip().lower()
    return {
        'apply': 'Ready to apply',
        'review': 'Worth reviewing',
        'skip': 'Low fit',
    }.get(rec, '')


def _career_branch_label(branch: str) -> str:
    return {
        'it': 'IT & tech',
        'non_it': 'Counseling & service',
        'other': 'Mixed role',
    }.get((branch or '').strip(), '')


def _row_to_job_payload(row: dict, *, applied_date: str = '') -> dict:
    match = lib.localize_match_for_display(row.get('match') or {})
    materials = _job_materials_meta(row)
    cv_profile = _suggest_cv_profile(row.get('title', ''), row.get('description', ''))
    title = row.get('title') or ''
    title_en = lib.english_display_title(title)
    career_branch = row.get('career_branch') or _career_branch(row)
    payload = {
        'job_id': row['job_id'],
        'title': title,
        'title_en': title_en,
        'company': row['company'],
        'location': row['location'],
        'country': row.get('country') or applied_jobs.infer_country(location=row['location']),
        'source': row['source'],
        'apply_url': _best_apply_url({'apply_url': row['apply_url'], 'refnr': row.get('refnr', ''), 'description': row.get('description', '')}),
        'remote': row['remote'],
        'description': (row.get('description') or row.get('description_preview') or '')[:1200],
        'match_score': row.get('match_score'),
        'recommendation': row.get('recommendation') or '',
        'recommendation_label': _recommendation_label(row.get('recommendation') or '', scored=bool(row.get('scored'))),
        'ai_summary': row.get('ai_summary') or '',
        'list_hint': _card_list_hint(row, match),
        'scored': row.get('scored', False),
        'keyword_hint': row.get('keyword_hint') or '',
        'run_name': row.get('run_name') or '',
        'folder_name': row.get('folder_name') or '',
        'applied_date': applied_date,
        'qualification_label': _qualification_label(row),
        'good_match': _is_good_match_row(row),
        'full_match': _is_full_match_row(row),
        'degree_ready': _is_degree_ready_row(row),
        'listable_in_all': _is_listable_in_all_view(row),
        'career_branch': career_branch,
        'career_branch_label': _career_branch_label(career_branch),
        'role_category': (match.get('role_category') or '') if match else '',
        'cv_profile': cv_profile,
        'materials': materials,
        'match_detail': {
            'reasoning': match.get('reasoning') or '',
            'title_note': match.get('title_vs_requirements_note') or '',
            'must_have_met': match.get('must_have_met_count'),
            'must_have_total': match.get('must_have_total'),
            'required_met': match.get('required_met') or [],
            'required_missing': match.get('required_missing') or [],
            'dealbreakers': match.get('dealbreakers') or [],
            'requirements': (match.get('requirements_analysis') or [])[:10],
        } if match else None,
    }
    return payload


def _row_to_job_list_payload(row: dict, *, applied_date: str = '') -> dict:
    """Compact job card payload for the browse API (keeps responses fast)."""
    match = row.get('match') or {}
    title = row.get('title') or ''
    title_en = lib.english_display_title(title)
    career_branch = row.get('career_branch') or _career_branch(row)
    job_id = row['job_id']
    blob = _row_blob(row)
    md = None
    if match:
        md = {
            'reasoning': (match.get('reasoning') or '')[:320],
            'title_note': (match.get('title_vs_requirements_note') or '')[:160],
            'must_have_met': match.get('must_have_met_count'),
            'must_have_total': match.get('must_have_total'),
            'required_met': list(match.get('required_met') or [])[:4],
            'required_missing': list(match.get('required_missing') or [])[:4],
            'dealbreakers': list(match.get('dealbreakers') or [])[:3],
            'requirements': list(match.get('requirements_analysis') or [])[:6],
        }
    return {
        'job_id': job_id,
        'title': title,
        'title_en': title_en,
        'company': row['company'],
        'location': row['location'],
        'country': row.get('country') or applied_jobs.infer_country(location=row['location']),
        'source': row['source'],
        'apply_url': _best_apply_url({
            'apply_url': row['apply_url'],
            'refnr': row.get('refnr', ''),
            'description': row.get('description', ''),
        }),
        'remote': row['remote'],
        'description': (row.get('description') or row.get('description_preview') or '')[:480],
        'match_score': row.get('match_score'),
        'recommendation': row.get('recommendation') or '',
        'recommendation_label': _recommendation_label(row.get('recommendation') or '', scored=bool(row.get('scored'))),
        'ai_summary': (row.get('ai_summary') or '')[:240],
        'list_hint': _card_list_hint(row, match),
        'scored': row.get('scored', False),
        'keyword_hint': row.get('keyword_hint') or '',
        'run_name': row.get('run_name') or '',
        'folder_name': row.get('folder_name') or '',
        'applied_date': applied_date,
        'qualification_label': _qualification_label(row),
        'good_match': _is_good_match_row(row),
        'full_match': _is_full_match_row(row),
        'degree_ready': _is_degree_ready_row(row),
        'listable_in_all': _is_listable_in_all_view(row),
        'career_branch': career_branch,
        'career_branch_label': _career_branch_label(career_branch),
        'role_category': (match.get('role_category') or '') if match else '',
        'cv_profile': _suggest_cv_profile(title, row.get('description', '')),
        'materials': _job_materials_meta_list(job_id),
        'match_detail': md,
        'german_required': lib.hard_german_required(blob),
        'senior_excluded': bool(
            lib.SENIOR_EXCLUDE.search(blob) and not lib.JUNIOR_SIGNAL.search(blob)
        ),
        'has_trainee_program': bool(lib.TRAINEE_PROGRAM_SIGNAL.search(blob)),
        'has_werkstudent': bool(lib.WERKSTUDENT_SIGNAL.search(blob)),
    }


def _build_applied_jobs_payload(
    applied_entries: list[dict],
    cached: list[dict],
    scored_lookup: dict[str, dict],
) -> list[dict]:
    """LinkedIn-style applied list: merge saved applications with cache + scores."""
    row_by_id = {
        row['job_id']: row
        for row in _build_unified_job_rows(cached, scored_lookup, hide_low_scores=False)
    }
    payload: list[dict] = []
    for entry in applied_entries:
        jid = entry.get('job_id') or ''
        row = row_by_id.get(jid)
        if row:
            payload.append(_row_to_job_payload(row, applied_date=entry.get('applied_date', '')))
            continue
        payload.append({
            'job_id': jid,
            'title': entry.get('title') or 'Unknown role',
            'company': entry.get('company') or 'Unknown company',
            'location': entry.get('location') or '',
            'country': entry.get('country') or applied_jobs.infer_country(location=entry.get('location', '')),
            'source': '',
            'apply_url': _best_apply_url(entry),
            'remote': False,
            'description': '',
            'match_score': None,
            'recommendation': '',
            'ai_summary': '',
            'scored': False,
            'keyword_hint': '',
            'run_name': '',
            'folder_name': '',
            'applied_date': entry.get('applied_date', ''),
            'match_detail': None,
        })
    return payload


def _company_website_url(job: dict) -> str:
    """Best-effort direct employer site from posting text or apply URL."""
    desc = job.get('description') or job.get('description_preview') or ''
    employer, _listing = lib.extract_apply_urls_from_description(desc)
    if employer and not lib.is_intermediary_board_url(employer):
        return employer
    apply = _best_apply_url(job)
    if apply and not lib.is_intermediary_board_url(apply):
        return apply
    return ''


def _build_applied_table_rows(
    applied_entries: list[dict],
    cached: list[dict],
    scored_lookup: dict[str, dict],
) -> list[dict]:
    jobs = _build_applied_jobs_payload(applied_entries, cached, scored_lookup)
    rows: list[dict] = []
    for index, job in enumerate(jobs, start=1):
        title_en = lib.english_display_title(job.get('title') or '')
        company_url = _company_website_url(job)
        listing_url = (job.get('apply_url') or '').strip()
        rows.append({
            'number': index,
            'job_id': job.get('job_id') or '',
            'company': job.get('company') or 'Unknown company',
            'title': job.get('title') or '',
            'title_en': title_en,
            'company_url': company_url,
            'listing_url': listing_url,
            'country': job.get('country') or job.get('location') or '',
            'applied_date': job.get('applied_date') or '',
            'match_score': job.get('match_score'),
            'scored': bool(job.get('scored')),
        })
    return rows


def jobs_applied(request):
    """Dedicated Applied page — LinkedIn split view, separate from job browsing."""
    try:
        cached = lib.load_cached_jobs()
    except Exception:
        cached = []

    runs = _list_job_runs()
    run_dir = runs[0] if runs else None
    scored_lookup = _merged_scored_lookup(run_dir)
    applied_entries, applied_total = _applied_entries()
    applied_rows = _build_applied_table_rows(applied_entries, cached, scored_lookup)
    applied_id_list = sorted(applied_jobs.applied_ids())

    return render(request, 'cvapp/jobs_applied_hub.html', {
        'applied_total': applied_total,
        'applied_rows': applied_rows,
        'applied_ids_json': json.dumps(applied_id_list),
        **_jobs_hub_urls(view='non_it'),
    })


@require_POST
def jobs_applied_toggle(request):
    """Mark or unmark a job as applied (JSON for Jobs browser, form POST for Applied page)."""
    wants_json = 'application/json' in (request.content_type or '')
    body: dict = {}
    if wants_json:
        try:
            body = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'ok': False, 'error': 'Invalid request'}, status=400)
        job_id = (body.get('job_id') or '').strip()
    else:
        job_id = (request.POST.get('job_id') or '').strip()

    if not job_id:
        if wants_json:
            return JsonResponse({'ok': False, 'error': 'Missing job_id'}, status=400)
        return redirect(reverse('jobs_applied'))

    if applied_jobs.is_applied(job_id):
        applied_jobs.unmark_applied(job_id)
        if wants_json:
            return JsonResponse({'ok': True, 'applied': False})
        return redirect(reverse('jobs_applied'))

    title = (body.get('title') or request.POST.get('title') or '').strip()
    company = (body.get('company') or request.POST.get('company') or '').strip()
    location = (body.get('location') or request.POST.get('location') or '').strip()
    country = (body.get('country') or request.POST.get('country') or '').strip()
    apply_url = (body.get('apply_url') or request.POST.get('apply_url') or '').strip()

    if not title or not company:
        cached = _find_cached_job_by_id(job_id)
        if cached:
            title = title or cached.get('title', '')
            company = company or cached.get('company', '')
            location = location or cached.get('location', '')
            country = country or cached.get('country', '')
            apply_url = apply_url or cached.get('apply_url', '')

    entry = applied_jobs.mark_applied(
        job_id=job_id,
        title=title or 'Unknown role',
        company=company or 'Unknown company',
        location=location,
        country=country,
        apply_url=apply_url,
    )
    if wants_json:
        return JsonResponse({
            'ok': True,
            'applied': True,
            'entry': {
                **entry,
                'applied_date': _format_applied_date(entry.get('applied_at', '')),
            },
        })
    return redirect(reverse('jobs_applied'))


def jobs_market(request):
    """
    One job list: all listings from cache with AI filter/sort when scored.
    Default view = all jobs from the last search (LinkedIn-style browse).
    """
    ctx = _jobs_market_query(request)
    if ctx.get('redirect'):
        return ctx['redirect']

    if (
        ctx['view'] in ('good', 'it_good', 'non_it_good', 'full', 'degree')
        and ctx['good_fits_total'] == 0
        and ctx['cache_raw_total'] > 0
    ):
        q = request.GET.copy()
        q['view'] = 'all'
        if not q.get('message'):
            q['message'] = 'Showing all jobs — Good matches appear after AI scoring.'
        return redirect(reverse('jobs_market') + '?' + q.urlencode())

    applied_entries, applied_total = _applied_entries()
    applied_id_list = sorted(applied_jobs.applied_ids())
    cache_info = _get_cache_info()
    profile = _load_profile()
    resumable_run = ctx['resumable_run']
    source_diagnostics = lib.load_source_diagnostics()
    source_issues = _source_issues_for_ui(source_diagnostics)
    master_rows = ctx['master_rows']
    embed_cap = 300
    if len(master_rows) > embed_cap:
        slim_embed = [_row_to_job_list_payload(row) for row in master_rows[:embed_cap]]
        jobs_lazy_load = True
    else:
        slim_embed = _build_slim_jobs_list(master_rows)
        jobs_lazy_load = False

    return render(request, 'cvapp/jobs_market.html', {
        'message': request.GET.get('message', ''),
        'error': request.GET.get('error', ''),
        'applied_entries': applied_entries,
        'applied_total': applied_total,
        'entries': applied_entries,
        'total': applied_total,
        'jobs_list': slim_embed,
        'jobs_json': json.dumps(slim_embed, ensure_ascii=True, separators=(',', ':')),
        'jobs_lazy_load': jobs_lazy_load,
        'jobs_total_count': len(master_rows),
        'applied_ids_json': json.dumps(applied_id_list),
        'selected_job_id': ctx['selected_job_id'],
        'display_count': len(ctx['filtered_rows']),
        'cache_total': ctx['cache_total'],
        'cache_raw_total': ctx['cache_raw_total'],
        'hidden_low_score': ctx['hidden_low_score'],
        'scored_total': ctx['scored_total'],
        'unscored_total': ctx['unscored_total'],
        'good_fits_total': ctx['good_fits_total'],
        'full_match_total': ctx['full_match_total'],
        'degree_ready_total': ctx['degree_ready_total'],
        'non_it_total': ctx['non_it_total'],
        'it_total': ctx['it_total'],
        'matches_total': ctx['good_fits_total'],
        'view': ctx['view'],
        'view_label': ctx['view_label'],
        'english_ok': ctx['english_ok'],
        'entry_only': ctx['entry_only'],
        'program': ctx['program'],
        'selected_run': ctx['selected_run'],
        'runs': [r.name for r in ctx['runs']],
        'cache_info': cache_info,
        'location_query': ctx['location_query'],
        'query': ctx['query'],
        'source_query': ctx['source_query'],
        'remote_only': ctx['remote_only'],
        'profile': profile,
        'match_mode': getattr(lib, 'MATCH_MODE', 'broad'),
        'pipeline_status': ctx['pipeline_status'],
        'resumable_run': resumable_run.name if resumable_run else '',
        'broad_min': getattr(lib, 'BROAD_SCORE_MIN', 32),
        'pipeline_running': ctx['pipeline_running'],
        'source_issues': source_issues,
        'source_updated_at': source_diagnostics.get('timestamp', ''),
        **_jobs_hub_urls(view=ctx['view']),
    })


def _fast_browse_rows_from_cache(cached: list[dict]) -> list[dict]:
    """Build browse rows without scored lookup (fast path for live search polling)."""
    applied = applied_jobs.applied_ids()
    rows: list[dict] = []
    seen: set[str] = set()
    for job in cached:
        card = _cache_job_to_display(job)
        job_id = card['job_id']
        if job_id in applied or job_id in seen:
            continue
        seen.add(job_id)
        branch = _career_branch(card)
        rows.append({
            **card,
            'scored': False,
            'match': {},
            'match_score': None,
            'recommendation': '',
            'ai_summary': '',
            'career_branch': branch,
            'keyword_hint': '',
            'folder_name': '',
            'run_name': '',
            'qualified': False,
        })
    return rows


def jobs_market_live(request):
    """Fast JSON list for live search — polled every few seconds while Find jobs runs."""
    status = pstatus.read_status()
    cached = _load_market_cached_jobs()
    scored_lookup = _merged_scored_lookup(None)
    payloads = _fast_slim_jobs_payload(cached, scored_lookup)
    live_jobs = lib.load_live_jobs().get('jobs') or []
    return JsonResponse({
        'ok': True,
        'jobs': payloads,
        'total_count': len(payloads),
        'live_count': len(live_jobs) or int(status.get('live_count') or 0),
        'pipeline_running': pstatus.is_running(),
        'pipeline_phase': status.get('phase') or '',
        'search_running': status.get('state') == 'running' and (status.get('phase') or 'search') == 'search',
        'message': status.get('message') or '',
    })


def jobs_market_data(request):
    """JSON job list — refreshed during AI scoring without a full page reload."""
    from . import pipeline_status as pstatus

    if pstatus.is_running():
        _MARKET_DATA_CACHE['at'] = 0.0
    cache_key = request.get_full_path()
    now = time.time()
    cached_entry = _MARKET_DATA_CACHE
    if (
        now - cached_entry.get('at', 0) < _MARKET_DATA_CACHE_TTL
        and cached_entry.get('key') == cache_key
        and cached_entry.get('data')
    ):
        return JsonResponse(cached_entry['data'])
    ctx = _jobs_market_query(request)
    if ctx.get('redirect'):
        return JsonResponse({'ok': False, 'error': 'redirect'}, status=400)
    phase = ctx['pipeline_status'].get('phase') or ''
    view_scored = sum(1 for row in ctx['filtered_rows'] if row.get('scored'))
    view_unscored = len(ctx['filtered_rows']) - view_scored
    source_diagnostics = lib.load_source_diagnostics()
    slim_jobs = _build_slim_jobs_list(ctx['master_rows'])
    payload = {
        'ok': True,
        'jobs': slim_jobs,
        'view': ctx['view'],
        'scored_total': ctx['scored_total'],
        'unscored_total': ctx['unscored_total'],
        'good_fits_total': ctx['good_fits_total'],
        'cache_raw_total': ctx['cache_raw_total'],
        'view_scored_count': view_scored,
        'view_unscored_count': view_unscored,
        'display_count': len(ctx['filtered_rows']),
        'pipeline_running': ctx['pipeline_running'],
        'pipeline_phase': phase,
        'pipeline_progress': int(ctx['pipeline_status'].get('progress') or 0),
        'pipeline_total': int(ctx['pipeline_status'].get('total') or 0),
        'pipeline_message': ctx['pipeline_status'].get('message') or '',
        'it_total': ctx['it_total'],
        'non_it_total': ctx['non_it_total'],
        'other_total': ctx['other_total'],
        'it_good_total': ctx['it_good_total'],
        'non_it_good_total': ctx['non_it_good_total'],
        'degree_ready_total': ctx['degree_ready_total'],
        'full_match_total': ctx['full_match_total'],
        'view_label': ctx['view_label'],
        'source_issues': _source_issues_for_ui(source_diagnostics),
        'source_updated_at': source_diagnostics.get('timestamp', ''),
    }
    if not ctx['pipeline_running']:
        _MARKET_DATA_CACHE['key'] = cache_key
        _MARKET_DATA_CACHE['at'] = now
        _MARKET_DATA_CACHE['data'] = payload
    else:
        _MARKET_DATA_CACHE['at'] = 0.0
    return JsonResponse(payload)


@require_cv_access
def cv_page(request, slug):
    """Print-friendly CV (browser Print → Save as PDF)."""
    from .cv_pdf import cv_render_context

    profile = get_cv_profile(slug)
    return render(
        request,
        profile.print_template,
        cv_render_context(for_browser_print=True, profile=profile),
    )


def _job_identity(job: dict) -> str:
    return _job_lookup_key(job)


def _load_existing_run_state(out_dir: Path) -> tuple[list[dict], set[str]]:
    """Results list + keys already scored in this run folder."""
    results: list[dict] = []
    keys: set[str] = set()
    summary = out_dir / 'summary.json'
    if summary.exists():
        try:
            data = json.loads(summary.read_text(encoding='utf-8'))
            if isinstance(data, list):
                results = data
        except Exception:
            results = []
    for folder in out_dir.iterdir():
        if not folder.is_dir():
            continue
        match_file = folder / 'match.json'
        if not match_file.exists():
            continue
        try:
            meta = json.loads(match_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        url = (meta.get('apply_url') or '').strip()
        if url:
            keys.add(url)
        else:
            keys.add(f"{meta.get('company', '')}|{meta.get('title', '')}".lower())
    return results, keys


def _find_resumable_run() -> Path | None:
    """Deprecated: scoring now always targets unscored cache jobs in a fresh run."""
    return None


def _write_run_summaries(out_dir: Path, results: list[dict]) -> None:
    """Persist summary files so partial runs show up in the dashboard."""
    apply_list = [r for r in results if r.get('qualified_to_apply')]
    (out_dir / 'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    (out_dir / 'apply_shortlist.json').write_text(json.dumps(apply_list, indent=2), encoding='utf-8')
    scored_path = getattr(lib, 'SCORED_JOBS_PATH', None)
    if scored_path:
        scored_path.parent.mkdir(parents=True, exist_ok=True)
        scored_path.write_text(
            json.dumps(
                {
                    'run_id': out_dir.name,
                    'scored': len(results),
                    'qualified': len(apply_list),
                    'updated_at': datetime.now().isoformat(timespec='seconds'),
                    'jobs': results,
                },
                indent=2,
            ),
            encoding='utf-8',
        )


def _run_job_search_pipeline(
    use_cache: bool = True,
    max_jobs: int = DEFAULT_MAX_JOBS,
    min_score: int = DEFAULT_MIN_SCORE,
    dry_run: bool = True,
    *,
    track_progress: bool = False,
    resume_dir: Path | None = None,
) -> tuple[int, int, Path, int, int]:
    lib.load_env_files()
    if max_jobs > 0:
        max_jobs = min(max_jobs, WEB_MAX_JOBS)
    else:
        max_jobs = WEB_MAX_JOBS
    cv = lib.load_cv()
    profile = lib.load_profile()

    scored_lookup = _merged_scored_lookup(None)
    jobs, total_unscored = _unscored_cache_jobs(scored_lookup, max_jobs=max_jobs)
    if not jobs:
        if total_unscored == 0:
            raise RuntimeError(
                'Every job in your cache is already scored. Click Search again if you want fresh listings.'
            )
        raise RuntimeError('No unscored jobs available to analyze right now.')

    run_id = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    out_dir = JOB_SEARCH_OUTPUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total = len(jobs)
    api_key = _require_env('MISTRAL_API_KEY')

    if track_progress:
        pstatus.write_status(
            total=total,
            progress=0,
            run_id=run_id,
            phase='score',
            message=f'Scoring {total} new jobs ({total_unscored} waiting in total)…',
        )

    scored = 0
    generated = 0
    for index, job in enumerate(jobs, start=1):
        if pstatus.is_cancelled():
            break
        desc, about, title, company = lib.job_text_fields(job)
        if not desc:
            continue

        try:
            match = lib.match_job(api_key, cv, job, profile)
            score = int(match.get('match_score', 0))
            rec = match.get('recommendation', 'skip')

            materials = None
            if not dry_run and lib.should_generate(match, min_score):
                try:
                    materials = lib.generate_materials(api_key, cv, job, match, profile)
                    generated += 1
                except Exception as mat_exc:
                    materials = None
                    match['materials_error'] = str(mat_exc)[:200]

            lib.write_job_output(out_dir, job, title, company, match, materials)
            results.append({
                'score': score,
                'recommendation': rec,
                'qualified_to_apply': match.get('qualified_to_apply', False),
                'must_have_met': match.get('must_have_met_count', 0),
                'must_have_total': match.get('must_have_total', 0),
                'company': company,
                'title': title,
                'location': job.get('location', ''),
            })
            scored += 1
            _write_run_summaries(out_dir, results)
        except Exception as exc:
            results.append({
                'score': 0,
                'recommendation': 'error',
                'qualified_to_apply': False,
                'company': company,
                'title': title,
                'location': job.get('location', ''),
                'error': str(exc)[:200],
            })
            scored += 1
            _write_run_summaries(out_dir, results)

        if track_progress:
            apply_so_far = sum(1 for r in results if r.get('qualified_to_apply'))
            pstatus.write_status(
                progress=scored,
                total=total,
                run_id=run_id,
                phase='score',
                message=(
                    f'Scored {scored}/{total} · '
                    f'{apply_so_far} on apply list · {title[:40]}…'
                ),
            )

    (out_dir / 'summary.md').write_text(lib.build_summary_md(results, out_dir), encoding='utf-8')
    apply_n = sum(1 for r in results if r.get('qualified_to_apply'))
    matches_n = sum(
        1 for r in results
        if int(r.get('score') or 0) >= DISPLAY_MIN_SCORE
    )
    return total_unscored, generated, out_dir, len(results), matches_n


def _background_score(
    *,
    use_cache: bool,
    max_jobs: int,
    min_score: int,
    dry_run: bool,
    resume_dir: Path | None = None,
) -> None:
    try:
        if pstatus.is_cancelled():
            return
        before, generated, out_dir, scored_n, matches_n = _run_job_search_pipeline(
            use_cache=use_cache,
            max_jobs=max_jobs,
            min_score=min_score,
            dry_run=dry_run,
            track_progress=True,
            resume_dir=resume_dir,
        )
        if pstatus.is_cancelled():
            pstatus.write_status(
                state='completed',
                phase='score',
                message=f'Scoring stopped — {scored_n} jobs scored this run. Browse → All jobs.',
                run_id=out_dir.name,
                progress=scored_n,
                total=scored_n,
                error='',
            )
            return
        remaining = max(0, before - scored_n)
        msg = (
            f'Scored {scored_n} jobs this run · {matches_n} at 50%+ match. '
        )
        if remaining:
            msg += f'{remaining} still waiting — click Analyze again to continue. '
        else:
            msg += 'Open the Matches tab to see results. '
        msg += f'Run: {out_dir.name}.'
        pstatus.write_status(
            state='completed',
            phase='score',
            message=msg,
            run_id=out_dir.name,
            progress=scored_n,
            total=scored_n,
            error='',
        )
    except Exception as exc:
        pstatus.write_status(state='failed', error=str(exc), message='Pipeline failed')


def _get_pipeline_settings(request):
    settings = _get_saved_settings(request)
    if request.method == 'POST':
        settings['max_jobs'] = int(request.POST.get('max_jobs', settings['max_jobs']))
        settings['min_score'] = int(request.POST.get('min_score', settings['min_score']))
    return settings


def jobs_reset_pipeline(request):
    if request.method != 'POST':
        return redirect('jobs_market')
    pstatus.request_cancel()
    _MARKET_DATA_CACHE['at'] = 0.0
    _STATS_CACHE['at'] = 0.0
    try:
        lib.clear_live_jobs()
    except Exception:
        pass
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'message': 'Cancelled. Open Browse → All jobs to see your saved listings.',
        })
    return redirect(_dashboard_redirect(message='Pipeline reset. Browse → All jobs to see your listings.'))


@require_POST
def jobs_clear_scores(request):
    """Remove all saved AI match results (e.g. after switching candidate profile)."""
    removed = lib.clear_all_scored_runs()
    _invalidate_scored_lookup_cache()
    _MARKET_DATA_CACHE['at'] = 0.0
    _STATS_CACHE['at'] = 0.0
    msg = (
        f'Cleared {removed} saved score bundle(s). Click Score AI to match jobs against your CV.'
        if removed
        else 'No saved scores found — click Score AI to analyze jobs.'
    )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'removed': removed, 'message': msg})
    return redirect(_dashboard_redirect(message=msg))


def _background_refresh() -> None:
    from .jobs_automation import auto_score_after_search_enabled

    try:
        lib.load_env_files()

        def on_progress(**fields):
            fields.setdefault('phase', 'search')
            pstatus.write_status(state='running', label='Searching job sites', **fields)

        try:
            existing = lib.load_cached_jobs()
        except Exception:
            existing = []
        on_progress(
            message='Starting search…',
            live_count=len(existing),
            latest_jobs=lib._jobs_for_live_feed(existing, limit=80),
            progress=0,
            total=6,
            phase='search',
        )
        jobs = lib.refresh_jobs_cache(include_apify=True, on_progress=on_progress)
        diag = lib.load_source_diagnostics()
        source_lines = [
            f"{s.get('source')}: {s.get('count', 0)}"
            for s in (diag.get('sources') or [])
            if s.get('count', 0) > 0
        ]
        if auto_score_after_search_enabled() and os.getenv('MISTRAL_API_KEY', '').strip():
            pstatus.write_status(
                state='running',
                label='Score jobs',
                phase='score',
                message=f'Found {len(jobs)} roles — auto-scoring with AI…',
                live_count=len(jobs),
                progress=0,
                total=0,
            )
            _background_score(
                use_cache=True,
                max_jobs=min(DEFAULT_MAX_JOBS, WEB_MAX_JOBS),
                min_score=DEFAULT_MIN_SCORE,
                dry_run=True,
            )
            return

        message = (
            f'Found {len(jobs)} roles in your region. '
            f'Browse → All jobs to see the full list. '
        )
        if not os.getenv('MISTRAL_API_KEY', '').strip():
            message += 'Add MISTRAL_API_KEY on Render to enable auto-score after search. '
        else:
            message += 'Click Score AI to compare them to your CV. '
        message += 'Good matches (50%+) appear under Browse → Good matches.'
        if source_lines:
            message += ' Sources: ' + ', '.join(source_lines[:8]) + '.'
        if diag.get('apify_fallback_used'):
            message += ' Apify had few DE jobs — used free portals.'
        pstatus.write_status(
            state='completed',
            phase='search',
            message=message,
            error='',
            progress=100,
            total=100,
            live_count=len(jobs),
        )
    except Exception as exc:
        pstatus.write_status(state='failed', error=str(exc), message='Search failed')


@csrf_exempt
def jobs_cron_daily(request):
    """Render cron / external scheduler: daily search + score + digest."""
    secret = os.getenv('CRON_SECRET', '').strip()
    provided = (
        request.headers.get('X-Cron-Secret', '')
        or request.GET.get('secret', '')
        or request.POST.get('secret', '')
    ).strip()
    if not secret or provided != secret:
        return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=403)
    from .jobs_automation import run_daily_automation

    result = run_daily_automation(send_digest=True)
    status = 200 if result.get('ok') else 409
    return JsonResponse(result, status=status)


def jobs_refresh_cache(request):
    if request.method != 'POST':
        return redirect('jobs_market')
    if pstatus.is_running():
        return redirect(_dashboard_redirect(error='A search is already running. Wait or click Cancel.'))
    lib.load_env_files()
    _STATS_CACHE['at'] = 0.0
    _invalidate_slim_jobs_cache()
    _MARKET_DATA_CACHE['at'] = 0.0
    started = pstatus.start_background(_background_refresh, label='Searching job sites', kwargs={})
    if not started:
        return redirect(_dashboard_redirect(error='Could not start search.'))
    return redirect(_dashboard_redirect(
        message='Job search started — watch the progress bar above. Browse matches when it says Done.',
    ))


def jobs_resume_pipeline(request):
    """Continue scoring remaining cache jobs into the latest incomplete run."""
    if request.method != 'POST':
        return redirect('jobs_market')
    status = pstatus.read_status()
    if status.get('state') == 'running':
        return redirect(_dashboard_redirect(
            error='Pipeline still marked as running. Click Reset pipeline, then Resume scoring.',
        ))
    run = _find_resumable_run()
    if not run:
        return redirect(_dashboard_redirect(error='No partial run found — use Score jobs to start fresh.'))
    try:
        lib.load_env_files()
        if not os.getenv('MISTRAL_API_KEY', '').strip():
            return redirect(_dashboard_redirect(error='MISTRAL_API_KEY missing in .env — restart server after saving.'))
        cfg = _get_pipeline_settings(request)
        existing_results, _ = _load_existing_run_state(run)
        started = pstatus.start_background(
            _background_score,
            label='Resume scoring',
            kwargs={
                'use_cache': True,
                'max_jobs': min(cfg['max_jobs'], WEB_MAX_JOBS),
                'min_score': cfg['min_score'],
                'dry_run': True,
                'resume_dir': run,
            },
        )
        if not started:
            return redirect(_dashboard_redirect(error='Could not start background job.'))
        return redirect(_dashboard_redirect(
            message=(
                f'Resuming run {run.name} ({len(existing_results)} done). '
                f'Scoring up to {min(cfg["max_jobs"], WEB_MAX_JOBS)} total — refresh in a few minutes.'
            ),
        ))
    except Exception as exc:
        return redirect(_dashboard_redirect(error=_friendly_error(exc)))


def jobs_run_pipeline(request):
    if request.method != 'POST':
        return redirect('jobs_control')
    if pstatus.is_running():
        return redirect(_dashboard_redirect(error='Pipeline already running — check status below.'))
    try:
        lib.load_env_files()
        if not os.getenv('MISTRAL_API_KEY', '').strip():
            return redirect(_dashboard_redirect(error='MISTRAL_API_KEY missing in .env — restart server after saving.'))
        cfg = _get_pipeline_settings(request)
        started = pstatus.start_background(
            _background_score,
            label='Score jobs',
            kwargs={
                'use_cache': True,
                'max_jobs': min(cfg['max_jobs'], WEB_MAX_JOBS),
                'min_score': cfg['min_score'],
                'dry_run': True,
            },
        )
        if not started:
            return redirect(_dashboard_redirect(error='Could not start background job.'))
        return redirect(_dashboard_redirect(
            message=(
                f'Scoring up to {min(cfg["max_jobs"], WEB_MAX_JOBS)} jobs — '
                f'runs in the background; already-scored jobs are skipped.'
            ),
        ))
    except Exception as exc:
        return redirect(_dashboard_redirect(error=_friendly_error(exc)))


def jobs_run_full_pipeline(request):
    if request.method != 'POST':
        return redirect('jobs_control')
    if pstatus.is_running():
        return redirect(_dashboard_redirect(error='Pipeline already running — check status below.'))
    try:
        lib.load_env_files()
        if not os.getenv('MISTRAL_API_KEY', '').strip():
            return redirect(_dashboard_redirect(error='MISTRAL_API_KEY missing in .env — restart server after saving.'))
        cfg = _get_pipeline_settings(request)
        started = pstatus.start_background(
            _background_score,
            label='Generate materials',
            kwargs={
                'use_cache': True,
                'max_jobs': min(cfg['max_jobs'], WEB_MAX_JOBS),
                'min_score': cfg['min_score'],
                'dry_run': False,
            },
        )
        if not started:
            return redirect(_dashboard_redirect(error='Could not start background job.'))
        return redirect(_dashboard_redirect(
            message=f'Generating materials for up to {min(cfg["max_jobs"], WEB_MAX_JOBS)} jobs. Refresh in a few minutes.'
        ))
    except Exception as exc:
        return redirect(_dashboard_redirect(error=_friendly_error(exc)))


def job_detail(request, run_name: str, folder_name: str):
    run_name = Path(run_name).name
    folder_name = Path(folder_name).name
    run_dir = JOB_SEARCH_OUTPUT_ROOT / run_name
    if not run_dir.exists() or not run_dir.is_dir():
        raise Http404('Job run not found')
    job = _load_job_folder(run_dir / folder_name)
    if not job:
        raise Http404('Job details not found')

    return render(request, 'cvapp/job_detail.html', {
        'job': job,
        'run_name': run_name,
    })
