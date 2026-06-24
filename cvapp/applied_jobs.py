"""Track jobs the user has applied to (file-based storage)."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

APPLIED_PATH = Path(__file__).resolve().parents[1] / 'jobsearch' / 'data' / 'applied_jobs.json'
_lock = threading.Lock()

_COUNTRY_NAMES = {
    'DE': 'Germany',
    'AT': 'Austria',
    'CH': 'Switzerland',
    'NL': 'Netherlands',
    'US': 'United States',
    'USA': 'United States',
    'UK': 'United Kingdom',
    'GB': 'United Kingdom',
    'FR': 'France',
    'ES': 'Spain',
    'IT': 'Italy',
    'PL': 'Poland',
    'BE': 'Belgium',
    'LU': 'Luxembourg',
    'IE': 'Ireland',
    'SE': 'Sweden',
    'NO': 'Norway',
    'DK': 'Denmark',
    'FI': 'Finland',
    'CZ': 'Czech Republic',
}


def _read_raw() -> dict:
    if not APPLIED_PATH.exists():
        return {}
    try:
        data = json.loads(APPLIED_PATH.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_raw(data: dict) -> None:
    APPLIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')


def infer_country(job: dict | None = None, *, location: str = '') -> str:
    if job:
        country = str(job.get('country') or '').strip()
        if country:
            upper = country.upper()
            return _COUNTRY_NAMES.get(upper, country)
        location = location or str(job.get('location') or '')

    loc = (location or '').strip()
    if not loc:
        return ''

    if ',' in loc:
        tail = loc.rsplit(',', 1)[-1].strip()
        if tail:
            upper = tail.upper()
            return _COUNTRY_NAMES.get(upper, tail)

    upper = loc.upper()
    if upper in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[upper]

    lower = loc.lower()
    for name in (
        'germany', 'deutschland', 'austria', 'österreich', 'switzerland', 'schweiz',
        'netherlands', 'niederlande', 'france', 'frankreich', 'spain', 'italien',
        'italy', 'poland', 'belgium', 'luxembourg', 'ireland', 'sweden', 'norway',
        'denmark', 'finland', 'united kingdom', 'united states',
    ):
        if name in lower:
            return name.title()

    if re.search(r'\bDE\b', loc):
        return 'Germany'
    if len(loc) <= 40:
        return loc
    return ''


def list_applied() -> list[dict]:
    entries = list(_read_raw().values())
    entries.sort(key=lambda entry: entry.get('applied_at', ''))
    return entries


def applied_ids() -> set[str]:
    return set(_read_raw().keys())


def is_applied(job_id: str) -> bool:
    return job_id in _read_raw()


def mark_applied(
    *,
    job_id: str,
    title: str,
    company: str,
    location: str = '',
    country: str = '',
    apply_url: str = '',
) -> dict:
    with _lock:
        data = _read_raw()
        entry = {
            'job_id': job_id,
            'title': title,
            'company': company,
            'location': location,
            'country': country or infer_country(location=location),
            'apply_url': apply_url,
            'applied_at': datetime.now().isoformat(timespec='seconds'),
        }
        data[job_id] = entry
        _write_raw(data)
        return entry


def unmark_applied(job_id: str) -> bool:
    with _lock:
        data = _read_raw()
        if job_id not in data:
            return False
        del data[job_id]
        _write_raw(data)
        return True
