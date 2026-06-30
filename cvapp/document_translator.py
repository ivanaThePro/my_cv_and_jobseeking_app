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
COURSE_CODE_RE = re.compile(r'\b(?:\d[A-Z]{2}\d{3,4}[A-Z]?|UTVB\d{4})\b')
COL_CODE_CELL_RE = re.compile(
    r'(<td[^>]*class="[^"]*col-code[^"]*"[^>]*>)(.*?)(</td>)',
    re.IGNORECASE | re.DOTALL,
)


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
    """Replace course codes and program-code cells with placeholders."""
    mapping: dict[str, str] = {}
    counter = 0

    def stash(text: str) -> str:
        nonlocal counter
        key = f'[[KEEP_{counter}]]'
        mapping[key] = text
        counter += 1
        return key

    def col_code_repl(match: re.Match[str]) -> str:
        return match.group(1) + stash(match.group(2)) + match.group(3)

    protected = COL_CODE_CELL_RE.sub(col_code_repl, html)
    protected = COURSE_CODE_RE.sub(lambda m: stash(m.group(0)), protected)
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


def mistral_translate_html(api_key: str, html: str, target_lang: str, *, retries: int = 3) -> str:
    """Translate an HTML document via Mistral while preserving structure."""
    lang_name = LANG_NAMES.get(target_lang, target_lang)
    protected, mapping = protect_non_translatable(html)
    system = (
        f'You translate HTML documents into {lang_name}. '
        'Preserve every HTML tag, attribute, class, id, href, and the overall structure exactly. '
        'Only translate visible human-readable text (headings, paragraphs, labels, table headers, status text). '
        'Do not translate or modify placeholder tokens like [[KEEP_0]], [[KEEP_1]], etc. '
        'Do not translate email addresses, phone numbers, URLs, or personal names. '
        'Return only the full translated HTML document with no markdown fences or commentary.'
    )
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
        return restore_protected(translated, mapping)
    raise RuntimeError(f'Mistral translation failed: {last_error}')


def _read_cached_html(doc_kind: str, lang: str) -> str | None:
    """Return on-disk translation if present (even when source hash changed)."""
    html_path, _ = _cache_paths(doc_kind, lang)
    if not html_path.is_file():
        return None
    try:
        return html_path.read_text(encoding='utf-8')
    except OSError:
        return None


def _fallback_replacements(doc_kind: str, lang: str) -> dict[str, str]:
    from .cv_i18n import PROFESSIONAL_REPLACEMENTS, TRANSCRIPT_REPLACEMENTS

    if doc_kind == 'professional':
        return PROFESSIONAL_REPLACEMENTS.get(lang, {})
    if doc_kind == 'transcript':
        return TRANSCRIPT_REPLACEMENTS.get(lang, {})
    return {}


def _apply_replacements(html: str, replacements: dict[str, str]) -> str:
    out = html
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _doc_marker_present(html: str, doc_kind: str) -> bool:
    """Only reuse saved translations for the matching source document."""
    markers = {
        'transcript': 'Consolidated Academic Record',
        'professional': 'Courses & Skills Record',
    }
    marker = markers.get(doc_kind)
    return bool(marker and marker in html)


def translate_html_document(
    html: str,
    *,
    lang: str,
    doc_kind: str,
    api_key: str | None = None,
    allow_live: bool | None = None,
) -> str:
    """Return translated HTML from saved files, optional live Mistral, or heading fallbacks."""
    from .cv_i18n import normalize_lang

    lang = normalize_lang(lang)
    if lang == 'en':
        return html

    html_hash = source_hash(html)
    cached = _read_cache(doc_kind, lang, html_hash)
    if cached is not None:
        return cached

    if allow_live is None:
        allow_live = os.getenv('DOCUMENT_I18N_ALLOW_LIVE', 'false').strip().lower() in (
            '1', 'true', 'yes', 'on',
        )

    key = (api_key or os.getenv('MISTRAL_API_KEY', '')).strip()
    if allow_live and key:
        translated = mistral_translate_html(key, html, lang)
        _write_cache(doc_kind, lang, html_hash, translated)
        return translated

    return _apply_replacements(html, _fallback_replacements(doc_kind, lang))


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
