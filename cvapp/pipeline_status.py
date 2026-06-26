"""Lightweight background pipeline status (file-based, no extra DB required)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

STATUS_PATH = Path(__file__).resolve().parents[1] / 'jobsearch' / 'data' / 'pipeline_status.json'
CANCEL_PATH = STATUS_PATH.parent / 'pipeline_cancel.flag'
STALE_RUNNING_MINUTES = 12
STALE_SEARCH_START_MINUTES = 8
STALE_SEARCH_NO_PROGRESS_MINUTES = 4
_lock = threading.RLock()


def read_status() -> dict:
    if not STATUS_PATH.exists():
        return {}
    try:
        data = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}
    if is_cancelled() and data.get('state') == 'running':
        data['state'] = 'completed'
        data['message'] = data.get('message') or 'Cancelled.'
    _clear_stale_running(data)
    return data


def _cache_job_count() -> int:
    try:
        from jobsearch import jobsearch_lib as lib

        jobs = lib.load_cached_jobs()
        return len(jobs) if isinstance(jobs, list) else 0
    except Exception:
        return 0


def _mark_recovered(data: dict, *, message: str) -> None:
    data['state'] = 'completed'
    data['phase'] = data.get('phase') or 'search'
    data['error'] = ''
    data['message'] = message
    data['progress'] = int(data.get('total') or data.get('progress') or 0)
    STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _clear_stale_running(data: dict) -> None:
    """If status says running but nothing updated recently, recover or fail."""
    if data.get('state') != 'running':
        return
    updated = data.get('updated_at')
    if not updated:
        return
    try:
        last = datetime.fromisoformat(updated)
    except ValueError:
        data['state'] = 'failed'
        data['error'] = 'Pipeline status was invalid — click Cancel, then Find jobs again.'
        data['message'] = 'Stale run cleared'
        STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return
    age = datetime.now() - last
    if age < timedelta(0):
        age = timedelta(minutes=STALE_SEARCH_NO_PROGRESS_MINUTES + 1)
    phase = str(data.get('phase') or '').lower()
    progress = int(data.get('progress') or 0)
    total = int(data.get('total') or 0)
    live_count = int(data.get('live_count') or 0)
    cache_n = _cache_job_count()
    msg = (data.get('message') or '').lower()
    if phase == 'search' and cache_n > 0 and age > timedelta(minutes=STALE_SEARCH_NO_PROGRESS_MINUTES):
        if progress == 0 or 'starting search' in msg:
            _mark_recovered(
                data,
                message=(
                    f'Found {cache_n} roles in your region. '
                    'Browse → All jobs to see the full list. Click Score AI to compare them to your CV.'
                ),
            )
            return
    if phase == 'search' and progress == 0 and total == 0 and live_count == 0:
        if age > timedelta(minutes=STALE_SEARCH_START_MINUTES):
            data['state'] = 'failed'
            data['error'] = (
                'Search stopped before any jobs were saved (server restart or timeout). '
                'Click Cancel, then Find jobs again.'
            )
            data['message'] = 'Stale search cleared'
            STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
            return
    if phase == 'search' and progress == 0 and total > 0 and age > timedelta(minutes=STALE_SEARCH_NO_PROGRESS_MINUTES):
        if cache_n > 0:
            _mark_recovered(
                data,
                message=(
                    f'Found {cache_n} roles in your region. '
                    'Browse → All jobs to see the full list.'
                ),
            )
            return
    if age > timedelta(minutes=STALE_RUNNING_MINUTES):
        if cache_n > 0 and phase == 'search':
            _mark_recovered(
                data,
                message=(
                    f'Found {cache_n} roles in your region. '
                    'Browse → All jobs to see the full list.'
                ),
            )
            return
        data['state'] = 'failed'
        data['error'] = (
            'Pipeline stopped unexpectedly (server restart or timeout). '
            'Click Cancel, then Find jobs again.'
        )
        data['message'] = 'Stale run cleared'
        STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def write_status(**fields) -> dict:
    with _lock:
        if CANCEL_PATH.exists() and fields.get('state') == 'running':
            if STATUS_PATH.exists():
                try:
                    return json.loads(STATUS_PATH.read_text(encoding='utf-8'))
                except Exception:
                    return {}
            return {}
        data: dict = {}
        if STATUS_PATH.exists():
            try:
                data = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
            except Exception:
                data = {}
        data.update(fields)
        data['updated_at'] = datetime.now().isoformat(timespec='seconds')
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return data


def clear_cancel() -> None:
    with _lock:
        if CANCEL_PATH.exists():
            CANCEL_PATH.unlink()


def request_cancel() -> None:
    """Stop background search/scoring and unblock the UI."""
    with _lock:
        CANCEL_PATH.write_text(datetime.now().isoformat(timespec='seconds'), encoding='utf-8')
        data: dict = {}
        if STATUS_PATH.exists():
            try:
                data = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
            except Exception:
                data = {}
        data.update({
            'state': 'completed',
            'phase': data.get('phase') or 'search',
            'message': 'Cancelled — your saved jobs are still in Browse → All jobs.',
            'error': '',
            'label': '',
        })
        data['updated_at'] = datetime.now().isoformat(timespec='seconds')
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def clear_status() -> None:
    request_cancel()


def is_cancelled() -> bool:
    return CANCEL_PATH.exists()


def is_running() -> bool:
    if is_cancelled():
        return False
    return read_status().get('state') == 'running'


def start_background(target, *, label: str, kwargs: dict) -> bool:
    with _lock:
        if is_running():
            return False

        clear_cancel()
        write_status(
            state='running',
            label=label,
            message=f'{label} started…',
            error='',
            progress=0,
            total=kwargs.get('max_jobs', 0),
            started_at=datetime.now().isoformat(timespec='seconds'),
        )

        def _runner():
            try:
                target(**kwargs)
            except Exception as exc:
                if not is_cancelled():
                    write_status(state='failed', error=str(exc), message=f'{label} failed')

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return True
