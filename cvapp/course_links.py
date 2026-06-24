"""Official university pages for Ivana Jovic education record links."""

from __future__ import annotations

# Norwegian and international institutions from the consolidated education record.
_INSTITUTION_URLS: dict[str, str] = {
    'PED': 'https://www.uio.no/english/studies/programmes/',
    'JUS': 'https://www.uio.no/english/studies/programmes/',
    'BA': 'https://www.oslomet.no/en/about/positive-history/merger',
    'SPA': 'https://www.usn.no/english/about',
    'SCAN': 'https://www.bg.ac.rs/index.php/en/',
}


def course_syllabus_url(course_code: str) -> str:
    """Best verified public page for a program/course code on the education record."""
    code = (course_code or '').strip().upper()
    if not code:
        return ''
    if code in _INSTITUTION_URLS:
        return _INSTITUTION_URLS[code]
    if code.startswith(('IR', 'IRB', 'IRF')):
        return 'https://www.oslomet.no/en'
    return ''
