from pathlib import Path

_CSS_CACHE: dict[str, str] = {}
_STATIC_DIR = Path(__file__).resolve().parent / 'static'


def _read_css(name: str) -> str:
    if name in _CSS_CACHE:
        return _CSS_CACHE[name]
    path = _STATIC_DIR / 'css' / name
    if not path.is_file():
        return ''
    text = path.read_text(encoding='utf-8')
    # @import does not work inside inline <style>
    lines = [line for line in text.splitlines() if not line.strip().startswith('@import')]
    _CSS_CACHE[name] = '\n'.join(lines)
    return _CSS_CACHE[name]


def candidate_context(request):
    from .cv_profiles import PERSON_EMAIL, PERSON_NAME, PERSON_PHONE

    return {
        'person_name': PERSON_NAME,
        'person_email': PERSON_EMAIL,
        'person_phone': PERSON_PHONE,
    }


def profile_context(request):
    try:
        import jobsearch_lib as lib
        lib.load_env_files()
        return {'profile': lib.load_profile()}
    except Exception:
        return {'profile': {}}


def pipeline_status_context(request):
    from .pipeline_status import read_status
    return {'pipeline_status': read_status()}


def dashboard_styles(request):
    """Inline dashboard CSS so styling works even when /assets/ URLs fail."""
    return {
        'dashboard_css_inline': _read_css('dashboard.css'),
        'cv_css_inline': _read_css('style.css'),
    }


def topbar_context(request):
    path = (request.path or '').rstrip('/')
    if path.endswith('/jobs/applied') or request.GET.get('view') == 'applied':
        nav_section = 'applied'
    elif path in ('', '/jobs/market'):
        nav_section = 'browse'
    else:
        nav_section = ''
    try:
        from .nav_helpers import get_topbar_context
        return {**get_topbar_context(request), 'nav_section': nav_section}
    except Exception:
        return {
            'nav_cache_info': {'count': 0, 'updated': None},
            'nav_good_fits_count': 0,
            'nav_waiting_for_ai': 0,
            'nav_applied_count': 0,
            'nav_pipeline_running': False,
            'nav_resumable_run': '',
            'nav_incomplete_scoring': False,
            'nav_mistral_key': False,
            'nav_section': nav_section,
        }
