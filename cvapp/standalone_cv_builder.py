"""Build 2-page timeline CVs in the polished teal timeline format."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from html import escape
from urllib.parse import quote as urlquote

ACCENT_TEAL = '#0f766e'
ACCENT_TEAL_LIGHT = '#059669'
ACCENT_BLUE = '#1e3a8a'
ACCENT_BLUE_LIGHT = '#2563eb'
ACCENT_INDIGO = '#4338ca'
ACCENT_INDIGO_LIGHT = '#6366f1'
ACCENT_PURPLE = '#5b21b6'
ACCENT_PURPLE_LIGHT = '#7c3aed'
ACCENT_SKY = '#0369a1'
ACCENT_SKY_LIGHT = '#0284c7'

LANGUAGES = (
    'Serbo-Croatian (native); Norwegian, English, Spanish (proficient); '
    'Russian (intermediate); Macedonian (basic)'
)
REQUIREMENTS_TOOLS = 'Microsoft Office, Protel, Opera, Karriere Pro, Ad Opus'


def cv_public_base_url() -> str:
    """Public site base URL for QR codes and absolute transcript links.

    Empty by default — HTML uses same-origin paths (/transcript/, etc.).
    Set CV_PUBLIC_BASE_URL on Render when you need absolute URLs in PDFs/QR codes.
    """
    try:
        from django.conf import settings as django_settings

        configured = str(getattr(django_settings, 'CV_PUBLIC_BASE_URL', '') or '').strip().rstrip('/')
        if configured:
            return configured
    except Exception:
        pass
    for key in ('CV_PUBLIC_BASE_URL', 'RENDER_EXTERNAL_URL', 'PUBLIC_SITE_URL'):
        value = os.getenv(key, '').strip().rstrip('/')
        if value:
            return value
    return ''


def transcript_public_url() -> str:
    base = cv_public_base_url()
    return f'{base}/transcript/' if base else '/transcript/'


def professional_courses_public_url() -> str:
    base = cv_public_base_url()
    return f'{base}/cv/html/professional/' if base else '/cv/html/professional/'


def qr_code_url(target_path: str) -> str:
    """QR image URL; uses absolute target only when a public base URL is configured."""
    base = cv_public_base_url()
    if base:
        target = f'{base}{target_path}' if target_path.startswith('/') else target_path
    else:
        target = target_path if target_path.startswith('/') else f'/{target_path}'
    return f'https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urlquote(target, safe="")}'


_LEGACY_PUBLIC_BASES = (
    'https://cv-website-1-t8oi.onrender.com',
    'http://cv-website-1-t8oi.onrender.com',
    'https://cv-9eq5.onrender.com',
    'http://cv-9eq5.onrender.com',
)


def rewrite_legacy_public_links(html: str) -> str:
    """Strip old Render absolute URLs so links stay on the current site."""
    for legacy in _LEGACY_PUBLIC_BASES:
        html = html.replace(legacy, '')
    return html


# CAREER_TIMELINE is built dynamically in ivana_role_defs.build_career_timeline
CAREER_TIMELINE = ''


@dataclass(frozen=True)
class RoleCV:
    slug: str
    label: str
    description: str
    job_title: str
    accent: str = ACCENT_TEAL
    accent_light: str = ACCENT_TEAL_LIGHT
    verify_bg: str = '#f0fdfa'
    verify_border: str = '#99f6e4'
    skills_heading: str = 'PROFESSIONAL SKILLS & EXPERTISE'
    profile_intro: str = ''
    profile_highlights: tuple[str, ...] = ()
    skills: tuple[tuple[str, str], ...] = ()
    education_focus: str = (
        'International Development, Practical-Pedagogical Education, Spanish language studies, '
        'Scandinavian languages, and labor law (in progress).'
    )
    recent_bullets: tuple[str, ...] = (
        'Career counseling and Norwegian instruction for foreign-speaking adults at Hero Kompetanse.',
        'Substitute Spanish teaching at Rudolf Steiner School; based in Frankfurt am Main, Germany.',
    )
    award_items: tuple[str, ...] = ()
    interests: str = 'Languages, teaching, hiking, reading, community work.'
    availability: str = 'Frankfurt am Main, Germany | Open to Rhine-Main & NRW | EU work authorized'


def _highlights(items: tuple[str, ...]) -> str:
    if not items:
        return ''
    return ''.join(f'<p class="profile-highlight">{item}</p>' for item in items)


def build_role_cv_html(cv: RoleCV) -> str:
    from .cv_template import edu_card, load_cv_role_styles, skills_from_role_pairs
    from .ivana_role_defs import build_career_timeline

    transcript_url = transcript_public_url()
    professional_courses_url = professional_courses_public_url()
    recent = ''.join(f'<li>{escape(b)}</li>' for b in cv.recent_bullets)
    timeline = build_career_timeline(
        recent_bullets_html=recent,
        education_focus=cv.education_focus,
        professional_url=professional_courses_url,
    )
    awards = ''.join(cv.award_items)
    skills = skills_from_role_pairs(
        cv.skills + (('Languages & Communication', LANGUAGES),),
        courses_url=professional_courses_url,
    )
    highlights = _highlights(cv.profile_highlights)
    styles = load_cv_role_styles()
    edu_snapshot = (
        edu_card(
            'Education',
            'BA International Development',
            'Dissertation on migrant worker exploitation in Gulf countries; fieldwork in Mexico.',
            ('International development', 'Migration studies', 'Research methods', 'Fieldwork'),
            link_url=professional_courses_url,
        )
        + edu_card(
            'Education',
            'Practical-Pedagogical Education',
            'Authorized teacher for pre-school, primary, secondary, and adult level (University of Oslo).',
            ('Pedagogy', 'Adult education', 'Teaching authorization'),
            link_url=professional_courses_url,
        )
        + edu_card(
            'Verification',
            'Verified education record',
            (
                f'Recruiter-friendly education and course details: '
                f'<a class="web-link priority-education-link course-record-cta" href="{escape(professional_courses_url)}" '
                f'rel="noopener noreferrer" target="_blank" title="Open detailed education and course record">'
                f'View detailed education and course record</a>.'
            ),
        )
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="noindex, nofollow, noarchive, nosnippet, noimageindex" name="robots"/>
<title>Ivana Jovic - {escape(cv.label)}</title>
<style>
{styles}
</style>
</head>
<body class="cv-two-page-balanced cv-edge-polished timeline-polished-v3 timeline-light-v4 timeline-clean-v5 final-no-shadow-cv">
<main class="page">
<header class="hero">
<div class="hero-main">
<h1>Ivana Jovic</h1>
<div class="role-title">{escape(cv.job_title)}</div>
<div class="hero-meta">
<span class="meta-item meta-status">Frankfurt am Main</span>
<span class="meta-item">Email: ivanatjovic@gmail.com</span>
<span class="meta-item">Phone: +47 47 313 788</span>
</div>
</div>
<aside class="qr-card">
<img alt="QR code — education record" src="{qr_code_url('/transcript/')}"/>
<p>Scan for<br/>education record</p>
</aside>
</header>
<nav aria-label="Verification links" class="verify-bar">
<span class="verify-label">Links &rarr;</span>
<a href="{escape(transcript_url)}" rel="noopener noreferrer" target="_blank">Consolidated education record</a>
<a class="priority-education-link course-record-cta" href="{escape(professional_courses_url)}" rel="noopener noreferrer" target="_blank" title="Open detailed education and course record">Detailed education and course record</a>
</nav>
<section class="section">
<h2 class="section-title">Professional Profile</h2>
<div class="profile-box profile-unified">{'<p class="profile-intro">' + escape(cv.profile_intro) + '</p>' if cv.profile_intro else ''}{highlights}</div>
</section>
<section class="section">
<h2 class="section-title">{escape(cv.skills_heading)}</h2>
<div class="skills-grid">{skills}</div>
</section>
<section class="section education-snapshot-section">
<h2 class="section-title">Education &amp; Credentials Snapshot</h2>
<div class="edu-snapshot">{edu_snapshot}</div>
</section>
<section class="section">
<h2 class="section-title">Complete Career &amp; Education Chronology (MM/YYYY - MM/YYYY)</h2>
<p class="timeline-note">Full chronology retained to show continuity. Education entries are tagged inside the timeline so they remain visible without breaking the chronology.</p>
<div>{timeline}</div>
</section>
<section class="section">
<h2 class="section-title">Awards &amp; Additional Information</h2>
<div class="bottom-grid">
<article class="info-card"><h3>Awards &amp; Recognition</h3><ul>{awards}</ul></article>
<article class="info-card"><h3>Additional Information</h3>
<ul>
<li><strong>Availability:</strong> {escape(cv.availability)}</li>
<li><strong>Interests:</strong> {escape(cv.interests)}</li>
<li><strong>Verification:</strong> Education and experience per consolidated CV record.</li>
</ul></article>
</div>
</section>
</main>
</body>
</html>"""


def _role(
    slug: str,
    label: str,
    description: str,
    job_title: str,
    profile_intro: str,
    skills: tuple[tuple[str, str], ...],
    *,
    accent: str = ACCENT_TEAL,
    accent_light: str = ACCENT_TEAL_LIGHT,
    verify_bg: str = '#f0fdfa',
    verify_border: str = '#99f6e4',
    skills_heading: str = 'TECHNICAL SKILLS & EXPERTISE',
    profile_highlights: tuple[str, ...] = (),
    education_focus: str | None = None,
    recent_bullets: tuple[str, ...] | None = None,
    award_items: tuple[str, ...] | None = None,
    interests: str | None = None,
) -> RoleCV:
    from .ivana_role_defs import IVANA_AWARDS

    return RoleCV(
        slug=slug,
        label=label,
        description=description,
        job_title=job_title,
        accent=accent,
        accent_light=accent_light,
        verify_bg=verify_bg,
        verify_border=verify_border,
        skills_heading=skills_heading,
        profile_intro=profile_intro,
        profile_highlights=profile_highlights,
        skills=skills,
        education_focus=education_focus or RoleCV.education_focus,
        recent_bullets=recent_bullets or RoleCV.recent_bullets,
        award_items=award_items or IVANA_AWARDS,
        interests=interests or RoleCV.interests,
    )


from .ivana_role_defs import LANGUAGES as _IVANA_LANGUAGES, build_all_role_cvs

LANGUAGES = _IVANA_LANGUAGES
_ALL_ROLE_CVS = build_all_role_cvs()

_PUBLISHED_ROLE_SLUGS = frozenset(_ALL_ROLE_CVS.keys())
ROLE_CVS = {slug: _ALL_ROLE_CVS[slug] for slug in _PUBLISHED_ROLE_SLUGS}


def build_role_cv_html_by_slug(slug: str) -> str | None:
    cv = ROLE_CVS.get(slug)
    if not cv:
        return None
    return build_role_cv_html(cv)


def build_ai_tailored_cv_html(base_slug: str, ai_payload: dict) -> str:
    """Merge AI-tailored header/profile/skills onto the fixed 2-page timeline template."""
    from dataclasses import replace

    base = ROLE_CVS.get(base_slug) or ROLE_CVS['graduate-trainee']
    ai = ai_payload or {}
    boxes = ai.get('skill_boxes') or []
    skills: list[tuple[str, str]] = []
    for item in boxes:
        if isinstance(item, dict):
            h = str(item.get('heading') or '').strip()
            p = str(item.get('content') or '').strip()
            if h and p:
                skills.append((h, p))
    if len(skills) < 3:
        skills = list(base.skills[:3])
    highlights = tuple(str(h) for h in (ai.get('profile_highlights') or []) if h)
    customized = replace(
        base,
        job_title=str(ai.get('header_job_title') or base.job_title).strip() or base.job_title,
        profile_intro=str(ai.get('profile_intro') or base.profile_intro).strip() or base.profile_intro,
        profile_highlights=highlights,
        skills=tuple(skills[:3]),
        interests=str(ai.get('interests') or base.interests).strip() or base.interests,
    )
    return build_role_cv_html(customized)


def build_cover_letter_html(
    *,
    job_title: str,
    company: str,
    location: str = '',
    ai_payload: dict | None = None,
) -> str:
    """One-page print-friendly cover letter matching the CV teal style."""
    ai = ai_payload or {}
    greeting = escape(str(ai.get('greeting') or 'Dear Hiring Manager'))
    closing = escape(str(ai.get('closing') or 'Kind regards,'))
    subject = escape(str(ai.get('subject_line') or f'Application for {job_title}'))
    paragraphs = []
    for para in ai.get('paragraphs') or []:
        text = str(para or '').strip()
        if text:
            paragraphs.append(f'<p>{escape(text)}</p>')
    if not paragraphs:
        paragraphs.append('<p>I am writing to apply for the advertised role.</p>')
    location_line = f'<div class="meta-line">{escape(location)}</div>' if location else ''
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ivana Jovic - Cover Letter - {escape(job_title)}</title>
    <style>
        @page {{ size: A4; margin: 2cm 2cm; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            line-height: 1.5; color: #111827; background: #fff; margin: 0; padding: 0;
            font-size: 11pt;
        }}
        .letter-container {{ max-width: 700px; margin: 0 auto; padding: 24px 20px; }}
        .sender-block {{
            border-bottom: 2px solid #0f766e; padding-bottom: 12px; margin-bottom: 20px;
        }}
        .sender-name {{ font-size: 14pt; font-weight: 700; color: #0f766e; margin: 0 0 4px; }}
        .sender-contact {{ font-size: 10pt; color: #4b5563; margin: 2px 0; }}
        .meta-line {{ font-size: 10pt; color: #64748b; margin-top: 8px; }}
        .recipient-block {{ margin-bottom: 24px; font-size: 10.5pt; color: #334155; }}
        .recipient-block strong {{ color: #0f172a; }}
        .subject-line {{
            font-weight: 700; color: #0f766e; margin-bottom: 18px; font-size: 11pt;
        }}
        .letter-body p {{ margin: 0 0 14px; text-align: justify; }}
        .closing {{ margin-top: 24px; }}
        .signature {{ margin-top: 32px; font-weight: 600; color: #0f172a; }}
        @media print {{
            body {{ background: white; }}
            .letter-container {{ padding: 0; }}
        }}
    </style>
</head>
<body>
<div class="letter-container">
    <div class="sender-block">
        <div class="sender-name">Ivana Jovic</div>
        <div class="sender-contact">ivanatjovic@gmail.com | +47 47 313 788</div>
        <div class="sender-contact">Frankfurt am Main, Germany</div>
        {location_line}
    </div>
    <div class="recipient-block">
        <strong>{escape(company)}</strong><br>
        Re: {escape(job_title)}
    </div>
    <div class="subject-line">Subject: {subject}</div>
    <div class="letter-body">
        <p>{greeting},</p>
        {''.join(paragraphs)}
        <div class="closing">
            <p>{closing}</p>
            <div class="signature">Ivana Jovic</div>
        </div>
    </div>
</div>
</body>
</html>"""
