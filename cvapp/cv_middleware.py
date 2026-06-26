"""Password gate for the whole personal site (CV, transcript, jobs, tailored docs)."""

from __future__ import annotations

from urllib.parse import quote

from django.shortcuts import redirect

from .cv_access import cv_is_unlocked, cv_password_enabled

# Paths that stay reachable without unlocking (assets + unlock form + scheduled cron).
_PUBLIC_PREFIXES = (
    '/cv/unlock',
    '/cv/logout',
    '/health/',
    '/assets/',
    '/static/',
    '/robots.txt',
    '/favicon.ico',
)

# Applied to every password-protected HTML/API response (discourage caching and indexing).
_PRIVATE_HEADERS = {
    'Cache-Control': 'no-store, no-cache, must-revalidate, private, max-age=0',
    'Pragma': 'no-cache',
    'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet, noimageindex',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'interest-cohort=(), browsing-topics=()',
    'X-Frame-Options': 'DENY',
}


class CVAccessMiddleware:
    """Require CV_ACCESS_PASSWORD before any personal data is served."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _is_public(self, path: str) -> bool:
        if path.startswith('/jobs/cron/daily'):
            return True
        return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)

    def __call__(self, request):
        if cv_password_enabled() and not self._is_public(request.path):
            if not cv_is_unlocked(request):
                next_url = quote(request.get_full_path(), safe='')
                return redirect(f'/cv/unlock/?next={next_url}')

        response = self.get_response(request)

        if cv_password_enabled() and not self._is_public(request.path):
            for header, value in _PRIVATE_HEADERS.items():
                response.headers[header] = value

        return response
