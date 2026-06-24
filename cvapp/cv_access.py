"""Password gate for CV pages and PDF download."""

from __future__ import annotations

import secrets
import time
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect

SESSION_KEY = 'cv_access_v3'
UNLOCK_FAIL_KEY = 'cv_unlock_fails'
UNLOCK_LOCK_KEY = 'cv_unlock_locked_until'
MAX_UNLOCK_FAILS = 8
LOCKOUT_SECONDS = 900  # 15 minutes


def cv_password_enabled() -> bool:
    return bool(getattr(settings, 'CV_ACCESS_PASSWORD', ''))


def cv_is_unlocked(request) -> bool:
    if not cv_password_enabled():
        return True
    return bool(request.session.get(SESSION_KEY))


def grant_cv_access(request) -> None:
    request.session[SESSION_KEY] = True
    request.session.pop(UNLOCK_FAIL_KEY, None)
    request.session.pop(UNLOCK_LOCK_KEY, None)
    request.session.modified = True
    request.session.save()


def revoke_cv_access(request) -> None:
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
    request.session.save()


def unlock_is_locked(request) -> bool:
    until = request.session.get(UNLOCK_LOCK_KEY, 0)
    return bool(until) and time.time() < float(until)


def unlock_lockout_remaining(request) -> int:
    until = float(request.session.get(UNLOCK_LOCK_KEY, 0) or 0)
    return max(0, int(until - time.time()))


def record_unlock_failure(request) -> None:
    fails = int(request.session.get(UNLOCK_FAIL_KEY, 0) or 0) + 1
    request.session[UNLOCK_FAIL_KEY] = fails
    if fails >= MAX_UNLOCK_FAILS:
        request.session[UNLOCK_LOCK_KEY] = time.time() + LOCKOUT_SECONDS
    request.session.modified = True
    request.session.save()


def check_cv_password(password: str) -> bool:
    expected = getattr(settings, 'CV_ACCESS_PASSWORD', '')
    if not expected:
        return True
    supplied = (password or '').strip()
    return secrets.compare_digest(supplied, expected)


def ensure_cv_access(request):
    """Return a redirect response if the visitor must unlock the CV first."""
    if cv_password_enabled() and not cv_is_unlocked(request):
        next_url = quote(request.get_full_path(), safe='')
        return redirect(f'/cv/unlock/?next={next_url}')
    return None


def require_cv_access(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        blocked = ensure_cv_access(request)
        if blocked is not None:
            return blocked
        return view_func(request, *args, **kwargs)

    return wrapper
