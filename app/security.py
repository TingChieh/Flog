from functools import wraps
import re
from urllib.parse import urlsplit

import nh3
from flask import abort
from flask_login import current_user
from markupsafe import Markup
from pygments.token import STANDARD_TYPES


ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5',
    'h6', 'hr', 'figure', 'figcaption', 'img', 'input', 'li', 'ol', 'p', 'pre',
    'span', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
}
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    'a': {'href', 'title'},
    'code': {'class', 'data-language-label'},
    'h1': {'id'},
    'h2': {'id'},
    'h3': {'id'},
    'h4': {'id'},
    'h5': {'id'},
    'h6': {'id'},
    'img': {'alt', 'height', 'src', 'title', 'width'},
    'input': {'checked', 'disabled', 'type'},
    'li': {'class'},
    'ol': {'class'},
    'p': {'class'},
    'span': {'class'},
    'td': {'colspan', 'rowspan', 'style'},
    'th': {'colspan', 'rowspan', 'style'},
    'ul': {'class'},
}

_TOKEN_CLASSES = frozenset(value for value in STANDARD_TYPES.values() if value)
_TEXT_ALIGN = re.compile(r'text-align:\s*(?:left|center|right);?')
_LANG_CLASS = re.compile(r'language-[A-Za-z0-9_+.-]{1,64}')
_LANG_LABEL = re.compile(r'[A-Za-z0-9_+.-]{1,64}')
_INPUT_TAG = re.compile(r'<input\b[^>]*>', re.IGNORECASE)


def _filter_attribute(tag: str, name: str, value: str) -> str | None:
    if name == 'class':
        if tag == 'span':
            return value if value in _TOKEN_CLASSES or value == 'math math-inline' else None
        if tag == 'p':
            return value if value in {'math math-block', 'hard-break'} else None
        if tag == 'li':
            return value if value == 'task-list-item' else None
        if tag in {'ul', 'ol'}:
            return value if value == 'task-list' else None
        if tag == 'code':
            return value if _LANG_CLASS.fullmatch(value) else None
        return None
    if name == 'style' and tag in {'th', 'td'}:
        trimmed = value.strip()
        return trimmed if _TEXT_ALIGN.fullmatch(trimmed) else None
    if name == 'data-language-label' and tag == 'code':
        return value if _LANG_LABEL.fullmatch(value) else None
    if tag == 'input' and name == 'type':
        return value if value == 'checkbox' else None
    return value


_CLEANER = nh3.Cleaner(
    tags=ALLOWED_TAGS,
    clean_content_tags={'script', 'style'},
    attributes=ALLOWED_ATTRIBUTES,
    attribute_filter=_filter_attribute,
    url_schemes={'http', 'https', 'mailto'},
    link_rel=None,
)


def _read_only_checkbox(match: re.Match[str]) -> str:
    """Keep only checkbox inputs, always disabled."""
    tag = match.group(0)
    if 'type="checkbox"' not in tag:
        return ''
    return ('<input type="checkbox" disabled="" checked="">'
            if 'checked' in tag else '<input type="checkbox" disabled="">')


def sanitize_html(value: str | None) -> str:
    cleaned = _CLEANER.clean(value or '')
    return _INPUT_TAG.sub(_read_only_checkbox, cleaned)


def safe_html(value: str | None) -> Markup:
    return Markup(sanitize_html(value))


def is_local_path(target: str | None) -> bool:
    """Whether ``target`` is a path on this site, safe to redirect to.

    Browsers read ``//host`` and ``/\\host`` as other sites, and drop control
    characters before parsing.
    """
    if (not target or not target.startswith('/') or '\\' in target
            or any(ord(char) < 0x20 for char in target)):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and not target.startswith('//')


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
