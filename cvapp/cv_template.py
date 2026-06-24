"""HTML helpers for the polished 2-page role CV template."""

from __future__ import annotations

from html import escape
from pathlib import Path

_STYLES_PATH = Path(__file__).with_name('cv_role_styles.css')


def load_cv_role_styles() -> str:
    return _STYLES_PATH.read_text(encoding='utf-8')


def _split_date_range(date_range: str) -> tuple[str, str]:
    text = date_range.replace('–', '-').replace('—', '-').strip()
    if ' - ' in text:
        start, end = text.split(' - ', 1)
        return start.strip(), end.strip()
    if '-' in text:
        start, end = text.split('-', 1)
        return start.strip(), end.strip()
    return text, text


def date_badge(date_range: str) -> str:
    start, end = _split_date_range(date_range)
    safe = escape(date_range)
    return (
        f'<span aria-label="{safe}" class="date-badge">'
        f'<span class="date-range">'
        f'<span class="date-start">{escape(start)}</span>'
        f'<span aria-hidden="true" class="date-separator">-</span>'
        f'<span class="date-end">{escape(end)}</span>'
        f'</span></span>'
    )


def tag_list(items: tuple[str, ...] | list[str], *, link_url: str = '', linkable: bool = False) -> str:
  tags: list[str] = []
  for item in items:
    label = escape(item.strip())
    if not label:
      continue
    if linkable and link_url:
      tags.append(
        f'<a class="tag skill-link" href="{escape(link_url)}" rel="noopener noreferrer" '
        f'target="_blank" title="View detailed education and course record">{label}</a>'
      )
    else:
      tags.append(f'<span class="tag">{label}</span>')
  return f'<div class="tag-list">{"".join(tags)}</div>'


def skill_card(heading: str, items: tuple[str, ...] | list[str], *, link_url: str = '', linkable: bool = False) -> str:
    return (
        f'<article class="skill-card"><h3>{escape(heading)}</h3>'
        f'{tag_list(items, link_url=link_url, linkable=linkable)}</article>'
    )


def edu_card(badge: str, title: str, body: str, tags: tuple[str, ...] = (), *, link_url: str = '') -> str:
    tags_html = tag_list(tags, link_url=link_url, linkable=bool(link_url and tags)) if tags else ''
    return (
        f'<article class="edu-card"><h3>{escape(title)}</h3><p>{body}</p>{tags_html}</article>'
    )


def timeline_row(
    date_range: str,
    title: str,
    entry_tag: str,
    *,
    org: str = '',
    location: str = '',
    status: str = '',
    bullets_html: str = '',
    card_class: str = '',
    extra_body_html: str = '',
) -> str:
    details: list[str] = []
    if org:
        details.append(f'<span class="detail-pill detail-org"><b>Organization</b> {escape(org)}</span>')
    if location:
        details.append(f'<span class="detail-pill detail-location"><b>Location</b> {escape(location)}</span>')
    if status:
        details.append(f'<span class="detail-pill detail-status"><b>Status</b> {escape(status)}</span>')
    details_html = f'<div class="entry-details">{"".join(details)}</div>' if details else ''
    body = bullets_html or extra_body_html
    if body and not body.lstrip().startswith('<ul'):
        body = f'<ul class="entry-body">{body}</ul>'
    elif body and 'entry-body' not in body:
        body = body.replace('<ul>', '<ul class="entry-body">', 1)
    card_classes = 'timeline-card three-part-card'
    if card_class:
        card_classes += f' {card_class}'
    return (
        f'<article class="timeline-row"><div class="date-col" data-date="{escape(date_range)}">'
        f'{date_badge(date_range)}</div>'
        f'<div class="{card_classes}">'
        f'<div class="row-head"><h3>{escape(title)}</h3>'
        f'<span class="entry-tag">{escape(entry_tag)}</span></div>'
        f'{details_html}{body}</div></article>'
    )


def timeline_separator() -> str:
    return '<div class="full-timeline-separator"></div>'


def skills_from_role_pairs(skills: tuple[tuple[str, str], ...], *, courses_url: str = '') -> str:
    cards: list[str] = []
    for heading, content in skills:
        items = tuple(part.strip() for part in content.replace(';', ',').split(',') if part.strip())
        linkable = 'language' not in heading.lower() and bool(courses_url)
        cards.append(skill_card(heading, items, link_url=courses_url, linkable=linkable))
    return ''.join(cards)
