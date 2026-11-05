from functools import wraps
import re

from pygments.token import STANDARD_TYPES

import bleach
from flask import abort
from flask_login import current_user
from markupsafe import Markup


ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5',
    'h6', 'hr', 'figure', 'figcaption', 'img', 'input', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'table',
    'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
}
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'img': ['alt', 'height', 'src', 'title', 'width'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
}


_TOKEN_CLASSES = frozenset(value for value in STANDARD_TYPES.values() if value)


_TEXT_ALIGN = re.compile(r'text-align:\s*(?:left|center|right);?')
_INPUT_TAG = re.compile(r'<input\b[^>]*>', re.IGNORECASE)


def _allowed_attribute(tag, name, value):
    if name == 'id' and tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
        return True
    if name == 'class':
        if tag == 'span':
            return value in _TOKEN_CLASSES or value == 'math math-inline'
        if tag == 'p':
            return value in {'math math-block', 'hard-break'}
        if tag == 'li':
            return value == 'task-list-item'
        if tag in {'ul', 'ol'}:
            return value == 'task-list'
        if tag == 'code':
            return bool(re.fullmatch(r'language-[A-Za-z0-9_+.-]{1,64}', value))
        return False
    if name == 'style' and tag in {'th', 'td'}:
        return bool(_TEXT_ALIGN.fullmatch(value.strip()))
    if name == 'data-language-label' and tag == 'code':
        return bool(re.fullmatch(r'[A-Za-z0-9_+.-]{1,64}', value))
    if tag == 'input':
        return (name == 'type' and value == 'checkbox') or name in {
            'checked', 'disabled'}
    return name in ALLOWED_ATTRIBUTES.get(tag, ())


def _read_only_checkbox(match):
    """Keep only checkbox inputs, always disabled."""
    tag = match.group(0)
    if 'type="checkbox"' not in tag:
        return ''
    return ('<input type="checkbox" disabled="" checked="">'
            if 'checked' in tag else '<input type="checkbox" disabled="">')


class _AlignOnlyCss:
    """bleach CSS sanitizer that keeps nothing but a text-align value."""

    def sanitize_css(self, style):
        style = style.strip()
        return style if _TEXT_ALIGN.fullmatch(style) else ''


def sanitize_html(value):
    cleaned = bleach.clean(
        value or '', tags=ALLOWED_TAGS, attributes=_allowed_attribute,
        protocols={'http', 'https', 'mailto'}, strip=True,
        css_sanitizer=_AlignOnlyCss())
    cleaned = cleaned.replace(' style=""', '')
    return _INPUT_TAG.sub(_read_only_checkbox, cleaned)


def safe_html(value):
    return Markup(sanitize_html(value))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
