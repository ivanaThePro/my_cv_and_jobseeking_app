"""UI language helpers for public CV / transcript pages."""

from __future__ import annotations

from django.utils.html import escape

SUPPORTED_LANGS: dict[str, str] = {
    'en': 'English',
    'de': 'Deutsch',
    'no': 'Norsk',
}

UI_STRINGS: dict[str, dict[str, str]] = {
    'en': {
        'lang_note': 'Full page translation. Official course codes stay unchanged.',
        'tailored_hint': 'For each job, use Create on the job page — AI builds a tailored CV and cover letter.',
        'picker_title': 'CV & academic records',
        'picker_back': '\u2190 Back to Job Dashboard',
        'picker_lang_label': 'Language:',
        'picker_section_base': 'Base CV templates',
        'picker_section_base_hint': 'For each application, prefer Create on the job page — AI tailors CV and cover letter to that posting.',
        'picker_section_academic': 'Academic documentation',
        'picker_transcript_title': 'Consolidated academic record \u2197',
        'picker_transcript_desc': 'Education summary — Norwegian and international studies.',
        'signed_out': 'You have signed out. Enter your password to continue.',
    },
    'de': {
        'lang_note': 'Vollstaendige Seitenuebersetzung. Offizielle Kurscodes bleiben unveraendert.',
        'tailored_hint': 'Pro Stelle: „Create“ auf der Jobseite — KI erstellt Lebenslauf und Anschreiben.',
        'picker_title': 'Lebenslauf & akademische Nachweise',
        'picker_back': '\u2190 Zurueck zum Job-Dashboard',
        'picker_lang_label': 'Sprache:',
        'picker_section_base': 'Basis-Lebenslauf-Vorlagen',
        'picker_section_base_hint': 'Pro Bewerbung: „Create“ auf der Jobseite — KI passt Lebenslauf und Anschreiben an.',
        'picker_section_academic': 'Akademische Unterlagen',
        'picker_transcript_title': 'Konsolidierter akademischer Nachweis \u2197',
        'picker_transcript_desc': 'Bildungsuebersicht — norwegische und internationale Studien.',
        'signed_out': 'Sie wurden abgemeldet. Bitte Passwort eingeben.',
    },
    'no': {
        'lang_note': 'Full oversettelse av siden. Offisielle emnekoder beholdes uendret.',
        'tailored_hint': 'Per stilling: bruk «Create» på jobbsiden — AI lager skreddersydd CV og søknad.',
        'picker_title': 'CV og akademiske dokumenter',
        'picker_back': '\u2190 Tilbake til jobbdashboard',
        'picker_lang_label': 'Spraak:',
        'picker_section_base': 'Basis-CV-maler',
        'picker_section_base_hint': 'For hver søknad: bruk «Create» på jobbsiden — AI tilpasser CV og søknad.',
        'picker_section_academic': 'Akademisk dokumentasjon',
        'picker_transcript_title': 'Samlet akademisk oversikt \u2197',
        'picker_transcript_desc': 'Utdanningsoversikt — norske og internasjonale studier.',
        'signed_out': 'Du er logget ut. Skriv inn passordet for aa fortsette.',
    },
}

ROLE_CV_I18N: dict[str, dict[str, dict[str, str]]] = {
    'python-developer': {
        'de': {
            'label': 'Karriereberaterin CV',
            'description': 'Karriereberatung, Erwachsenenbildung und Berufsorientierung.',
        },
        'no': {
            'label': 'Karriereveileder CV',
            'description': 'Karriereveiledning, voksenopplaering og veiledning.',
        },
    },
    'support-technician': {
        'de': {
            'label': 'Kundenservice & Empfang CV',
            'description': 'Rezeption, Kundenservice und Front-Office-Rollen.',
        },
        'no': {
            'label': 'Kundeservice og resepsjon CV',
            'description': 'Resepsjon, kundeservice og front office.',
        },
    },
    'professional': {
        'de': {
            'label': 'Kurse & Kompetenzen',
            'description': 'Abschluesse, Hochschulkurse, Zertifikate und Faehigkeiten — Ergaenzung zu Rollen-CVs.',
        },
        'no': {
            'label': 'Kurs- og ferdighetsoversikt',
            'description': 'Grader, universitetskurs, sertifikater og ferdigheter — supplement til rolle-CVer.',
        },
    },
}


DOC_UI_LABELS: dict[str, dict[str, str]] = {
    'de': {
        'Course page': 'Kursseite',
        'Programme page': 'Programmseite',
        'Programme plan': 'Studienplan',
        'Programme overview': 'Programmuebersicht',
        'BA course modules': 'BA-Kursmodule',
        'Syllabus': 'Modulhandbuch',
        'PDF backup': 'PDF-Backup',
        'Credly verification': 'Credly-Verifizierung',
        'Certificate PDF': 'Zertifikat-PDF',
        'Certificate programme': 'Zertifikatsprogramm',
        'University of Oslo': 'Universitaet Oslo',
        'University of Oslo (IFI), Norway': 'Universitaet Oslo (IFI), Norwegen',
        'Linnaeus University, Sweden': 'Linnaeus-Universitaet, Schweden',
        'Luleå University of Technology, Sweden': 'Technische Universitaet Lulea, Schweden',
        'Uppsala University, Sweden': 'Universitaet Uppsala, Schweden',
        'Oslo Red Cross': 'Rotes Kreuz Oslo',
        'Anti-trafficking Centre, Belgrade': 'Zentrum gegen Menschenhandel, Belgrad',
    },
    'no': {
        'Course page': 'Emneside',
        'Programme page': 'Programside',
        'Programme plan': 'Programplan',
        'Programme overview': 'Programoversikt',
        'BA course modules': 'BA-emner',
        'Syllabus': 'Emneplan',
        'PDF backup': 'PDF-sikkerhetskopi',
        'Credly verification': 'Credly-verifisering',
        'Certificate PDF': 'Sertifikat-PDF',
        'Certificate programme': 'Sertifikatprogram',
        'University of Oslo': 'Universitetet i Oslo',
        'University of Oslo (IFI), Norway': 'Universitetet i Oslo (IFI), Norge',
        'Linnaeus University, Sweden': 'Linnéuniversitetet, Sverige',
        'Luleå University of Technology, Sweden': 'Luleå tekniska universitet, Sverige',
        'Uppsala University, Sweden': 'Uppsala universitet, Sverige',
        'Oslo Red Cross': 'Røde Kors Oslo',
        'Anti-trafficking Centre, Belgrade': 'Senter mot menneskehandel, Beograd',
    },
}


def normalize_lang(raw: str | None) -> str:
    key = (raw or 'en').strip().lower()[:2]
    return key if key in SUPPORTED_LANGS else 'en'


def ui(lang: str, key: str) -> str:
    lang = normalize_lang(lang)
    return UI_STRINGS.get(lang, UI_STRINGS['en']).get(key, UI_STRINGS['en'].get(key, ''))


def localized_role_cv(slug: str, *, label: str, description: str, lang: str) -> dict[str, str]:
    """Return translated label/description for a role CV card when available."""
    lang = normalize_lang(lang)
    if lang == 'en':
        return {'label': label, 'description': description}
    entry = ROLE_CV_I18N.get(slug, {}).get(lang, {})
    return {
        'label': entry.get('label') or label,
        'description': entry.get('description') or description,
    }


def picker_context(lang: str) -> dict[str, str]:
    """All UI strings for the CV picker page."""
    lang = normalize_lang(lang)
    keys = (
        'picker_title', 'picker_back', 'picker_lang_label', 'picker_section_base',
        'picker_section_base_hint', 'picker_section_academic',
        'picker_transcript_title', 'picker_transcript_desc', 'tailored_hint',
    )
    return {key: ui(lang, key) for key in keys}


def lang_switcher_html(*, base_path: str, current_lang: str, query: str = '') -> str:
    """Floating language bar for standalone HTML pages."""
    current_lang = normalize_lang(current_lang)
    qs_extra = f'&{query.lstrip("&")}' if query else ''
    links = []
    for code, label in SUPPORTED_LANGS.items():
        active = ' is-active' if code == current_lang else ''
        href = f'{base_path}?lang={code}{qs_extra}'
        links.append(
            f'<a class="cv-lang-link{active}" href="{escape(href)}">{escape(label)}</a>'
        )
    note = escape(ui(current_lang, 'lang_note'))
    return (
        '<div class="cv-lang-bar" role="navigation" aria-label="Document language">'
        + ''.join(links)
        + f'<span class="cv-lang-note">{note}</span>'
        + '</div>'
        + '<style>'
        '.cv-lang-bar{position:sticky;top:0;z-index:9999;display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;'
        'padding:8px 14px;background:#0c4a6e;color:#e0f2fe;font:600 0.8rem/1.3 Inter,system-ui,sans-serif;'
        'border-bottom:1px solid #0369a1;box-shadow:0 2px 8px rgba(12,74,110,.2)}'
        '.cv-lang-link{color:#bae6fd;text-decoration:none;padding:4px 10px;border-radius:999px;'
        'border:1px solid transparent}'
        '.cv-lang-link:hover{background:rgba(255,255,255,.12)}'
        '.cv-lang-link.is-active{color:#fff;background:rgba(255,255,255,.18);border-color:rgba(255,255,255,.35)}'
        '.cv-lang-note{margin-left:auto;color:#7dd3fc;font-weight:500;font-size:0.72rem}'
        '@media(max-width:640px){.cv-lang-note{width:100%;margin-left:0}}'
        '@media print{.cv-lang-bar{display:none!important}}'
        '</style>'
    )


def inject_privacy_meta(html: str) -> str:
    """Add noindex meta to standalone HTML documents."""
    tag = '<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">'
    if 'name="robots"' in html:
        return html
    if '<head' in html:
        idx = html.lower().find('<head')
        end = html.find('>', idx)
        if end != -1:
            return html[: end + 1] + tag + html[end + 1 :]
    return tag + html


def inject_lang_bar(html: str, *, bar_html: str) -> str:
    if 'cv-lang-bar' in html:
        return html
    if '<body' in html:
        idx = html.lower().find('<body')
        end = html.find('>', idx)
        if end != -1:
            return html[: end + 1] + bar_html + html[end + 1 :]
    return bar_html + html


def translate_document_html(html: str, *, lang: str, doc_kind: str) -> str:
    """Translate standalone HTML documents (cached Mistral translations when available)."""
    from .document_translator import translate_html_document

    return translate_html_document(html, lang=lang, doc_kind=doc_kind)
