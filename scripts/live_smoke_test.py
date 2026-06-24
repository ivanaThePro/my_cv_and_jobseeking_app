"""Smoke-test live deployment (set CV_PUBLIC_BASE_URL or pass as argv[1])."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.getenv('CV_PUBLIC_BASE_URL', '')).strip().rstrip('/')
if not BASE:
    print('Set CV_PUBLIC_BASE_URL or pass base URL as first argument.')
    sys.exit(2)


def fetch(method: str, path: str, timeout: int = 120) -> tuple[int, str]:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers={'User-Agent': 'cv-live-smoke/1.0'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode('utf-8', errors='replace')


def main() -> int:
    rows: list[tuple[str, str, str]] = []
    get_paths = [
        '/_sys/check/',
        '/jobs/market/',
        '/jobs/market/data/?view=all',
        '/jobs/status/',
        '/cv/',
        '/transcript/',
        '/home/',
        '/cv/html/professional/',
    ]
    for path in get_paths:
        try:
            code, body = fetch('GET', path)
            note = 'OK'
            if path.startswith('/jobs/market/data'):
                data = json.loads(body)
                note = f"ok={data.get('ok')} jobs={len(data.get('jobs') or [])}"
            elif path == '/jobs/status/':
                data = json.loads(body)
                note = f"state={data.get('state') or 'idle'}"
            rows.append((path, str(code), note))
        except urllib.error.HTTPError as exc:
            rows.append((path, str(exc.code), exc.reason))
        except Exception as exc:
            rows.append((path, 'ERR', str(exc)[:100]))

    for label, path in [
        ('cron POST no secret', '/jobs/cron/daily/'),
        ('cron POST bad secret', '/jobs/cron/daily/?secret=wrong-secret-probe-xyz'),
    ]:
        try:
            code, body = fetch('POST', path)
            rows.append((label, str(code), body[:100]))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')[:100]
            rows.append((label, str(exc.code), body))
        except Exception as exc:
            rows.append((label, 'ERR', str(exc)[:100]))

    for path, code, note in rows:
        print(f'{path:36} {code:4}  {note}')

    # If CRON_SECRET is configured, unauthorized probes must be 403.
    cron_codes = {r[1] for r in rows if r[0].startswith('cron')}
    if '403' in cron_codes:
        print('\nCRON_SECRET probe: server rejects unauthorized cron (good — secret is configured).')
    elif '401' in cron_codes or '403' in cron_codes:
        pass
    else:
        print('\nCRON_SECRET probe: unexpected response — check Render env on web + cron services.')

    failed = [r for r in rows if r[1] not in ('200', '302', '403')]
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
