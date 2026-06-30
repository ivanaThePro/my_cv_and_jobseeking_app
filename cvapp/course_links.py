"""Official syllabus URLs and on-site PDF backups for Ivana's course record."""

from __future__ import annotations

# University / faculty home pages (institution column + section headers).
INSTITUTION_HOME_URLS: dict[str, str] = {
    'uio': 'https://www.uio.no/english/',
    'uio_ifi': 'https://www.uio.no/english/about/organisation/faculty/matnat/ifi/',
    'oslomet': 'https://www.oslomet.no/en',
    'usn': 'https://www.usn.no/english',
    'belgrade': 'https://www.bg.ac.rs/index.php/en/',
    'belgrade_philology': 'https://www.fil.bg.ac.rs/en/',
    'linnaeus': 'https://lnu.se/en/',
    'uppsala': 'https://www.uu.se/en/',
    'ltu': 'https://www.ltu.se/en',
}

# Degree / programme pages on the consolidated education record.
PROGRAM_URLS: dict[str, str] = {
    'PED': 'https://www.uio.no/english/studies/programmes/ppu/',
    'JUS': 'https://www.uio.no/studier/emner/jus/jus/JUR1511/index.html',
    'BA': 'https://student.oslomet.no/en/bachelor-utviklingsstudier',
    'SPA': 'https://www.usn.no/studier/arsstudium-i-spansk/',
    'SCAN': 'https://www.fil.bg.ac.rs/en/departments/department-of-germanic-studies/scandinavian-languages-literatures-and-cultures',
    'UTVBA_PLAN': 'https://student.oslomet.no/en/studier/-/studieinfo/programplan/UTVBA/2026/H%C3%98ST',
}

# OsloMet UTVBA / completed BA modules (transcript codes + current catalogue where available).
_UTVB_COURSE_URLS: dict[str, str] = {
    'QUTV2ÅR1': 'https://student.oslomet.no/en/studier/-/studieinfo/emne/UTVB2000/2026/H%C3%98ST',
    'QUTV2ÅR3': PROGRAM_URLS['UTVBA_PLAN'],
    'QUTV2ÅR5': 'https://student.oslomet.no/en/studier/-/studieinfo/emne/UTVB2500/2026/H%C3%98ST',
    'UTVIÅR-OVERG': PROGRAM_URLS['UTVBA_PLAN'],
    'UTVB2100': 'https://student.oslomet.no/en/studier/-/studieinfo/emne/UTVB2100/2026/H%C3%98ST',
    'UTVB3200': 'https://student.oslomet.no/en/studier/-/studieinfo/emne/UTVB3200/2026/H%C3%98ST',
    'UTVB3300': 'https://student.oslomet.no/en/studier/-/studieinfo/emne/UTVB3300/2026/H%C3%98ST',
    'KRIM2920': 'https://www.uio.no/studier/emner/hf/ikrs/KRIM2920/index.html',
    'KRIM2914': 'https://www.uio.no/studier/emner/hf/ikrs/KRIM2914/index.html',
}

# Official public syllabus pages (Linnaeus PDFs, Swedish universities, UiO).
_COURSE_SYLLABUS_URLS: dict[str, str] = {
    '1DV501': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV501-1.pdf',
    '1DV502': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV502-2.000.pdf',
    '1DV503': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV503-2.000.pdf',
    '1DV508': 'https://kursplan.lnu.se/kursplaner/kursplan-1DV508-4.pdf',
    '1DV510': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV510-1.pdf',
    '1DV535': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV535-1.pdf',
    '1DV607': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV607-3.pdf',
    '1DV700': 'https://kursplan.lnu.se/kursplaner/syllabus-1DV700-1.pdf',
    '2DV505': 'https://kursplan.lnu.se/kursplaner/syllabus-2DV505-1.pdf',
    '1DT110': 'https://www.uu.se/en/study/syllabus?query=50973',
    'D0017D': 'https://www.ltu.se/en/education/syllabuses/course-syllabus?id=D0017D',
    'IN1000': 'https://www.uio.no/studier/emner/matnat/ifi/IN1000/index-eng.html',
}

# Which institution home URL each IT course belongs to.
_COURSE_INSTITUTION_KEYS: dict[str, str] = {
    '1DV501': 'linnaeus',
    '1DV502': 'linnaeus',
    '1DV503': 'linnaeus',
    '1DV508': 'linnaeus',
    '1DV510': 'linnaeus',
    '1DV535': 'linnaeus',
    '1DV607': 'linnaeus',
    '1DV700': 'linnaeus',
    '2DV505': 'linnaeus',
    '1DT110': 'uppsala',
    'D0017D': 'ltu',
    'IN1000': 'uio_ifi',
}

# Backup PDFs served at /course-syllabus/<filename>
_COURSE_BACKUP_PDFS: dict[str, str] = {
    '1DV501': 'syllabus-1DV501-1.pdf',
    '1DV502': 'syllabus-1DV502-2.000.pdf',
    '1DV503': 'syllabus-1DV503-2.000.pdf',
    '1DV508': 'kursplan-1DV508-4.pdf',
    '1DV510': 'syllabus-1DV510-1.pdf',
    '1DV535': 'syllabus-1DV535-1.pdf',
    '1DV607': 'syllabus-1DV607-3.pdf',
    '1DV700': 'syllabus-1DV700-1.pdf',
    '2DV505': 'syllabus-2DV505-1.pdf',
    'D0017D': 'Syllabus_D0017D.pdf',
}


def institution_home_url(key: str) -> str:
    return INSTITUTION_HOME_URLS.get((key or '').strip().lower(), '')


def program_page_url(program_code: str) -> str:
    code = (program_code or '').strip().upper()
    return PROGRAM_URLS.get(code, '')


def utvb_course_url(course_code: str) -> str:
    code = (course_code or '').strip().upper()
    return _UTVB_COURSE_URLS.get(code, '')


def course_syllabus_url(course_code: str) -> str:
    """Best verified public page for a program or course code."""
    code = (course_code or '').strip().upper()
    if not code:
        return ''
    if code in _COURSE_SYLLABUS_URLS:
        return _COURSE_SYLLABUS_URLS[code]
    if code in _UTVB_COURSE_URLS:
        return _UTVB_COURSE_URLS[code]
    if code in PROGRAM_URLS:
        return PROGRAM_URLS[code]
    if code.startswith(('IR', 'IRB', 'IRF')):
        return 'https://www.oslomet.no/en'
    return ''


def course_institution_url(course_code: str) -> str:
    code = (course_code or '').strip().upper()
    key = _COURSE_INSTITUTION_KEYS.get(code, '')
    return institution_home_url(key)


def course_syllabus_backup_path(course_code: str) -> str:
    """Relative URL path for on-site PDF backup, if available."""
    code = (course_code or '').strip().upper()
    filename = _COURSE_BACKUP_PDFS.get(code)
    if not filename:
        return ''
    return f'/course-syllabus/{filename}'
