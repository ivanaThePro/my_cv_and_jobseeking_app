"""Generate CV PDF — prefers Chrome (Playwright), falls back to xhtml2pdf."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from django.template.loader import render_to_string

from .cv_profiles import DEFAULT_CV_SLUG, CVProfile, get_cv_profile

logger = logging.getLogger(__name__)

APP_STATIC_DIR = Path(__file__).resolve().parent / 'static'
CV_PDF_FILENAME = 'Ivana_Jovic_CV.pdf'


def _read_css(*names: str) -> str:
    chunks: list[str] = []
    for name in names:
        path = APP_STATIC_DIR / 'css' / name
        if path.is_file():
            chunks.append(path.read_text(encoding='utf-8'))
    return '\n'.join(chunks)


def cv_render_context(*, for_browser_print: bool = False, profile: CVProfile | None = None) -> dict:
    profile = profile or get_cv_profile(DEFAULT_CV_SLUG)
    return {
        'cv': profile,
        'cv_css_inline': _read_css('style.css', 'cv_print.css'),
        'show_print_hint': for_browser_print,
    }


def _pdf_via_playwright(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until='load')
            return page.pdf(
                format='A4',
                print_background=True,
                margin={'top': '12mm', 'right': '14mm', 'bottom': '12mm', 'left': '14mm'},
            )
        finally:
            browser.close()


def _pdf_via_xhtml2pdf(html: str) -> bytes:
    from xhtml2pdf import pisa

    buffer = BytesIO()
    status = pisa.CreatePDF(
        html,
        dest=buffer,
        encoding='utf-8',
        default_css='@page { size: A4; margin: 12mm 14mm; }',
    )
    if status.err:
        raise RuntimeError('PDF generation failed (xhtml2pdf)')
    return buffer.getvalue()


def build_cv_pdf_bytes(request=None, profile: CVProfile | None = None) -> bytes:
    """Build PDF from the print-optimized template (same look as the web CV)."""
    profile = profile or get_cv_profile(DEFAULT_CV_SLUG)
    html = render_to_string(
        profile.print_template,
        cv_render_context(for_browser_print=False, profile=profile),
        request=request,
    )
    try:
        return _pdf_via_playwright(html)
    except Exception as exc:
        logger.warning('Playwright PDF failed (%s); using xhtml2pdf fallback.', exc)

    fallback_html = render_to_string(
        profile.print_template,
        cv_render_context(for_browser_print=False, profile=profile),
        request=request,
    )
    try:
        return _pdf_via_xhtml2pdf(fallback_html)
    except ImportError as import_exc:
        raise RuntimeError(
            'PDF export needs Playwright (recommended) or xhtml2pdf. '
            'Install: pip install playwright && playwright install chromium'
        ) from import_exc
