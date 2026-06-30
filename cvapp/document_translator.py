"""Mistral-powered HTML document translation with on-disk cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'
TRANSLATE_MODEL = os.getenv('MISTRAL_TRANSLATE_MODEL', 'mistral-small-latest')

LANG_NAMES = {
    'de': 'German',
    'no': 'Norwegian Bokmål',
}

I18N_DIR = Path(__file__).resolve().parent / 'data' / 'document_i18n'

# Swedish/Norwegian university course codes (e.g. 1DV501, 2MA402) and OsloMet UTVB modules.
COURSE_CODE_RE = re.compile(r'\b(?:\d[A-Z]{2}\d{3,4}[A-Z]?|UTVB\d{4}|QUTV2ÅR\d|UTVIÅR-OVERG|KRIM\d{4})\b')
COL_CODE_CELL_RE = re.compile(
    r'(<td[^>]*class="[^"]*col-code[^"]*"[^>]*>)(.*?)(</td>)',
    re.IGNORECASE | re.DOTALL,
)
TITLE_LINK_RE = re.compile(
    r'(<(?:h4)\b[^>]*>\s*<a\b[^>]*\bhref="[^"]*"[^>]*>)(.*?)(</a>\s*</h4>)',
    re.IGNORECASE | re.DOTALL,
)
CERT_TITLE_LINK_RE = re.compile(
    r'(<div class="course-header"><h4><a\b[^>]*\bhref="/assets/[^"]*"[^>]*>)(.*?)(</a></h4>)',
    re.IGNORECASE | re.DOTALL,
)
CLASS_TEXT_RE = re.compile(
    r'(<[^>]+class="[^"]*course-code[^"]*"[^>]*>)(.*?)(</[^>]+>)',
    re.IGNORECASE | re.DOTALL,
)
EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w.-]+\.\w+\b')
PHONE_RE = re.compile(r'\+\d[\d\s]{6,}\d')


def source_hash(html: str) -> str:
    return hashlib.sha256(html.encode('utf-8')).hexdigest()


def _cache_paths(doc_kind: str, lang: str) -> tuple[Path, Path]:
    safe = re.sub(r'[^\w.-]+', '_', doc_kind.strip().lower())
    return (
        I18N_DIR / f'{safe}.{lang}.html',
        I18N_DIR / f'{safe}.{lang}.meta.json',
    )


def _read_cache(doc_kind: str, lang: str, html_hash: str) -> str | None:
    html_path, meta_path = _cache_paths(doc_kind, lang)
    if not html_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    if meta.get('source_sha256') != html_hash:
        return None
    try:
        return html_path.read_text(encoding='utf-8')
    except OSError:
        return None


def _write_cache(doc_kind: str, lang: str, html_hash: str, translated: str) -> None:
    html_path, meta_path = _cache_paths(doc_kind, lang)
    I18N_DIR.mkdir(parents=True, exist_ok=True)
    html_path.write_text(translated, encoding='utf-8')
    meta_path.write_text(
        json.dumps(
            {
                'doc_kind': doc_kind,
                'lang': lang,
                'source_sha256': html_hash,
                'model': TRANSLATE_MODEL,
            },
            indent=2,
        ),
        encoding='utf-8',
    )


def protect_non_translatable(html: str) -> tuple[str, dict[str, str]]:
    """Replace course codes, official titles, and contact data with placeholders."""
    mapping: dict[str, str] = {}
    counter = 0

    def stash(text: str) -> str:
        nonlocal counter
        key = f'[[KEEP_{counter}]]'
        mapping[key] = text
        counter += 1
        return key

    def repl_title_link(match: re.Match[str]) -> str:
        return match.group(1) + stash(match.group(2)) + match.group(3)

    def repl_cert_title_link(match: re.Match[str]) -> str:
        return match.group(1) + stash(match.group(2)) + match.group(3)

    def col_code_repl(match: re.Match[str]) -> str:
        return match.group(1) + stash(match.group(2)) + match.group(3)

    def class_text_repl(match: re.Match[str]) -> str:
        return match.group(1) + stash(match.group(2)) + match.group(3)

    protected = COL_CODE_CELL_RE.sub(col_code_repl, html)
    protected = TITLE_LINK_RE.sub(repl_title_link, protected)
    protected = CERT_TITLE_LINK_RE.sub(repl_cert_title_link, protected)
    protected = CLASS_TEXT_RE.sub(class_text_repl, protected)
    protected = COURSE_CODE_RE.sub(lambda m: stash(m.group(0)), protected)
    protected = EMAIL_RE.sub(lambda m: stash(m.group(0)), protected)
    protected = PHONE_RE.sub(lambda m: stash(m.group(0)), protected)
    protected = protected.replace('Ivana Jovic', stash('Ivana Jovic'))
    protected = protected.replace('UTVBA', stash('UTVBA'))
    return protected, mapping


def restore_protected(html: str, mapping: dict[str, str]) -> str:
    out = html
    for key, value in mapping.items():
        out = out.replace(key, value)
    return out


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('```'):
        lines = stripped.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        stripped = '\n'.join(lines)
    return stripped.strip()


def _translation_system_prompt(target_lang: str) -> str:
    lang_name = LANG_NAMES.get(target_lang, target_lang)
    return (
        f'You translate HTML documents into {lang_name}. '
        'The result must read as a single, consistent language throughout — no mixed English fragments. '
        'Preserve every HTML tag, attribute, class, id, href, and the overall structure exactly. '
        'Translate all navigation labels, section headings, introductory paragraphs, skill summaries, '
        'footer text, syllabus button labels (Course page, Syllabus, PDF backup, Programme plan), '
        'and descriptive sentences in timeline-desc and course-desc blocks. '
        'Do NOT translate or modify placeholder tokens like [[KEEP_0]], [[KEEP_1]], etc. — copy them unchanged. '
        'Placeholders hide official degree/course titles, university names, course codes, emails, and personal names; '
        'leave those tokens exactly as given — never mix a translated word into a placeholder title. '
        f'Set <html lang="{target_lang}"> to the target language code ({target_lang}, not nb). '
        'Return only the full translated HTML document with no markdown fences or commentary.'
    )


def _normalize_doc_lang(html: str, lang: str) -> str:
    """Keep html lang aligned with site language codes."""
    if lang == 'no':
        html = re.sub(r'<html\s+lang="nb"', '<html lang="no"', html, count=1, flags=re.IGNORECASE)
    return html


def _finalize_translation(html: str, lang: str) -> str:
    from .cv_i18n import DOC_UI_LABELS

    html = _normalize_doc_lang(html, lang)
    for src, dst in DOC_UI_LABELS.get(lang, {}).items():
        html = html.replace(src, dst)
    return html


def mistral_translate_html(api_key: str, html: str, target_lang: str, *, retries: int = 3) -> str:
    """Translate an HTML document via Mistral while preserving structure."""
    protected, mapping = protect_non_translatable(html)
    system = _translation_system_prompt(target_lang)
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    payload = {
        'model': TRANSLATE_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': protected},
        ],
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        response = requests.post(MISTRAL_URL, json=payload, headers=headers, timeout=180)
        try:
            result = response.json()
        except ValueError as exc:
            last_error = exc
            time.sleep(1)
            continue
        if 'choices' not in result:
            is_rate_limit = response.status_code == 429 or result.get('code') == '1300'
            if is_rate_limit and attempt < retries:
                time.sleep(min(60, 5 * (2**attempt)))
                continue
            raise RuntimeError(f'Mistral translation error: {result}')
        translated = _strip_markdown_fences(result['choices'][0]['message']['content'])
        return _finalize_translation(restore_protected(translated, mapping), target_lang)
    raise RuntimeError(f'Mistral translation failed: {last_error}')


def translate_html_document(
    html: str,
    *,
    lang: str,
    doc_kind: str,
    api_key: str | None = None,
    allow_live: bool | None = None,
) -> str:
    """Return translated HTML from saved cache, optional live Mistral, or English source."""
    from .cv_i18n import normalize_lang

    lang = normalize_lang(lang)
    if lang == 'en':
        return html

    html_hash = source_hash(html)
    cached = _read_cache(doc_kind, lang, html_hash)
    if cached is not None:
        return _finalize_translation(cached, lang)

    if allow_live is None:
        allow_live = os.getenv('DOCUMENT_I18N_ALLOW_LIVE', 'false').strip().lower() in (
            '1', 'true', 'yes', 'on',
        )

    key = (api_key or os.getenv('MISTRAL_API_KEY', '')).strip()
    if allow_live and key:
        translated = mistral_translate_html(key, html, lang)
        _write_cache(doc_kind, lang, html_hash, translated)
        return translated

    # Never serve partially translated pages — English only until a full cache exists.
    return html


def iter_documents_for_translation() -> list[tuple[str, str]]:
    """Yield (doc_kind, html) pairs for all translatable standalone documents."""
    from django.conf import settings

    from .standalone_cv import read_standalone_cv_html
    from .standalone_cv_builder import ROLE_CVS

    docs: list[tuple[str, str]] = []
    docs.append(('professional', read_standalone_cv_html('professional')))
    transcript_path = Path(settings.BASE_DIR) / 'academic_transcript_improved.html'
    if transcript_path.is_file():
        from .standalone_cv_builder import rewrite_legacy_public_links

        docs.append(('transcript', rewrite_legacy_public_links(transcript_path.read_text(encoding='utf-8'))))
    for slug in sorted(ROLE_CVS):
        docs.append((slug, read_standalone_cv_html(slug)))
    return docs


def refresh_all_translations(
    *,
    langs: tuple[str, ...] = ('de', 'no'),
    force: bool = False,
    doc_kinds: tuple[str, ...] | None = None,
) -> list[str]:
    """Regenerate cached translations for documents. Returns status lines."""
    api_key = os.getenv('MISTRAL_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('MISTRAL_API_KEY missing — add it to .env and retry.')

    lines: list[str] = []
    docs = iter_documents_for_translation()
    if doc_kinds:
        wanted = {d.strip().lower() for d in doc_kinds}
        docs = [(k, h) for k, h in docs if k in wanted]
    for doc_kind, html in docs:
        html_hash = source_hash(html)
        for lang in langs:
            if not force:
                cached = _read_cache(doc_kind, lang, html_hash)
                if cached is not None:
                    lines.append(f'skip {doc_kind}.{lang} (cache valid)')
                    continue
            lines.append(f'translate {doc_kind} -> {lang} ...')
            translated = mistral_translate_html(api_key, html, lang)
            _write_cache(doc_kind, lang, html_hash, translated)
            lines.append(f'ok {doc_kind}.{lang}')
    return lines
