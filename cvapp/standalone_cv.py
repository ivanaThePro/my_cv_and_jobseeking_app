"""Standalone HTML CV files — role CVs built from the polished timeline template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.http import Http404

from .standalone_cv_builder import (
    ROLE_CVS,
    build_role_cv_html,
    build_role_cv_html_by_slug,
    rewrite_legacy_public_links,
)


@dataclass(frozen=True)
class StandaloneCV:
    slug: str
    label: str
    description: str
    filename: str = ''
    generated: bool = True


PROFESSIONAL_CV = StandaloneCV(
    slug='professional',
    label='Professional CV (detailed courses)',
    description='Full education record with linked course syllabi — print-ready standalone page.',
    filename='ivana_cv.html',
    generated=False,
)

STANDALONE_CVS: dict[str, StandaloneCV] = {
    cv.slug: StandaloneCV(
        slug=cv.slug,
        label=cv.label,
        description=cv.description,
        generated=True,
    )
    for cv in ROLE_CVS.values()
}
STANDALONE_CVS[PROFESSIONAL_CV.slug] = PROFESSIONAL_CV


def list_standalone_cvs() -> list[StandaloneCV]:
    """Role CVs first (job-specific), professional detailed CV last."""
    role_items = [STANDALONE_CVS[s] for s in ROLE_CVS if s in STANDALONE_CVS]
    role_items.sort(key=lambda c: c.label)
    if PROFESSIONAL_CV.slug in STANDALONE_CVS:
        role_items.append(STANDALONE_CVS[PROFESSIONAL_CV.slug])
    return role_items


def get_standalone_cv(slug: str) -> StandaloneCV:
    key = (slug or '').strip().lower()
    cv = STANDALONE_CVS.get(key)
    if cv is None:
        raise Http404(f'Standalone CV not found: {key}')
    return cv


def read_standalone_cv_html(slug: str) -> str:
    cv = get_standalone_cv(slug)
    if cv.generated:
        html = build_role_cv_html_by_slug(slug)
        if not html:
            raise Http404(f'CV builder missing: {slug}')
        return rewrite_legacy_public_links(html)
    path = Path(settings.BASE_DIR) / cv.filename
    if not path.is_file():
        raise Http404(f'CV file missing: {cv.filename}')
    return rewrite_legacy_public_links(path.read_text(encoding='utf-8'))


def write_standalone_cv_files(target_dir: Path | None = None) -> list[Path]:
    """Export generated role CV HTML to disk (optional backup — not used at runtime)."""
    root = target_dir or Path(settings.BASE_DIR)
    written: list[Path] = []
    for slug, cv in ROLE_CVS.items():
        html = build_role_cv_html(cv)
        path = root / f'ivana_cv_{slug.replace("-", "_")}.html'
        path.write_text(html, encoding='utf-8')
        written.append(path)
    return written


def remove_role_cv_exports(target_dir: Path | None = None) -> int:
    """Remove on-disk role CV exports; runtime serves them from the builder."""
    root = target_dir or Path(settings.BASE_DIR)
    removed = 0
    for path in root.glob('ivana_cv_*.html'):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed
