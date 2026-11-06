import re
import math
import unicodedata
from urllib.parse import quote, urlsplit

import sqlalchemy as sa
from flask import current_app
from lxml import html
from markdown import markdown
from markupsafe import Markup, escape
from pygments.formatters import HtmlFormatter

from app.markdown_extras import ListIndentExtension, MathExtension, TaskListExtension
from app.security import sanitize_html


LANGUAGE_LABELS = {
    'python': 'Python', 'javascript': 'JavaScript', 'js': 'JavaScript',
    'typescript': 'TypeScript', 'ts': 'TypeScript', 'html': 'HTML',
    'css': 'CSS', 'sql': 'SQL', 'bash': 'Bash', 'sh': 'Bash',
    'shell': 'Bash', 'json': 'JSON', 'mermaid': 'Mermaid',
}


class CodeFormatter(HtmlFormatter):
    """Keep the existing pre/code structure and expose the declared language."""

    def __init__(self, lang_str='', **options):
        super().__init__(**options)
        self.language_class = lang_str

    def wrap(self, source):
        language = self.language_class.removeprefix('language-')
        if language.lower() in ('', 'text'):
            yield 0, '<pre><code>'
        else:
            label = LANGUAGE_LABELS.get(language.lower(), language)
            yield 0, f'<pre><code class="{escape(self.language_class)}" data-language-label="{escape(label)}">'
        yield from source
        yield 0, '</code></pre>'

    def _wrap_div(self, source):
        yield from source


BODY_FORMAT_HTML = 'html'
BODY_FORMAT_MARKDOWN = 'markdown'
CONTENT_FORMATS = frozenset({BODY_FORMAT_HTML, BODY_FORMAT_MARKDOWN})


def normalize_body_format(value):
    return value if value in CONTENT_FORMATS else BODY_FORMAT_HTML


def prepare_content_source(value, body_format):
    source = value or ''
    if normalize_body_format(body_format) == BODY_FORMAT_MARKDOWN:
        return source
    return sanitize_html(source)


def split_hard_breaks(source):
    """Turn "line<br>line" paragraphs into adjacent paragraphs.

    A first-line indent only applies to the first line of a paragraph, so each
    line of a hard-broken paragraph becomes its own paragraph. All but the
    last carry ``hard-break`` so the stylesheet keeps the lines tight.
    """
    if '<br' not in source:
        return source
    root = html.fragment_fromstring(source, create_parent='div')
    for paragraph in root.findall('p'):
        if paragraph.get('class') or paragraph.find('br') is None:
            continue
        parts = [[paragraph.text or '', []]]
        for child in list(paragraph):
            if child.tag == 'br':
                parts.append([(child.tail or '').lstrip(), []])
            else:
                parts[-1][1].append(child)
        parts = [part for part in parts if part[0].strip() or part[1]]
        for index, (text, children) in enumerate(parts):
            line = html.Element('p')
            line.text = text
            for child in children:
                line.append(child)
            if index < len(parts) - 1:
                line.set('class', 'hard-break')
            paragraph.addprevious(line)
        root.remove(paragraph)
    return str(escape(root.text or '')) + ''.join(
        html.tostring(child, encoding='unicode', method='html') for child in root)


UPLOADED_PATH_RE = re.compile(r'^/files/([0-9a-f]{32}\.(?:png|jpe?g|gif))$')


def _wrap_live_photo(image, video_src):
    """Put ``image`` in a ``.live-photo`` box that live-photo.js brings to life."""
    box = html.Element('span')
    box.set('class', 'live-photo')
    box.set('data-live-video', video_src)
    badge = html.Element('span')
    badge.set('class', 'live-photo__badge')
    badge.set('aria-hidden', 'true')
    badge.text = 'LIVE'
    box.tail, image.tail = image.tail, None
    image.getparent().replace(image, box)
    box.extend([image, badge])


def optimize_images(rendered):
    """Let the browser defer and reserve space for sanitized HTML's images.

    Every ``<img>`` becomes lazy and async-decoded; uploaded ones whose pixel
    size is known also get ``width``/``height`` so the page does not jump when
    they arrive, and a ``srcset`` of smaller WebP copies when there are any.
    A Live Photo's still is wrapped so its clip can play over it.
    """
    if '<img' not in rendered:
        return rendered
    root = html.fragment_fromstring(rendered, create_parent='div')
    images = list(root.iter('img'))
    names = {}
    for image in images:
        match = UPLOADED_PATH_RE.match(urlsplit(image.get('src', '')).path)
        if match:
            names[image] = match.group(1)
    rows = {}
    if names:
        # app.content loads before the database exists, so import it late.
        from app import db
        from app.models import Image
        from app.images import VARIANT_SIZES, variant_srcset
        rows = {row.filename: row for row in db.session.execute(
            sa.select(Image.filename, Image.width, Image.height,
                      Image.video_filename)
            .where(Image.filename.in_(set(names.values()))))}
    for image in images:
        image.set('loading', 'lazy')
        image.set('decoding', 'async')
        row = rows.get(names.get(image))
        if row is None:
            continue
        local = not urlsplit(image.get('src')).netloc
        if (row.width and row.height and 'width' not in image.attrib
                and 'height' not in image.attrib):
            image.set('width', str(row.width))
            image.set('height', str(row.height))
            srcset = variant_srcset(row.filename, image.get('src'), row.width) if local else ''
            if srcset:
                image.set('srcset', srcset)
                image.set('sizes', VARIANT_SIZES)
        if row.video_filename and local:
            _wrap_live_photo(image, f'/files/{row.video_filename}')
    return str(escape(root.text or '')) + ''.join(
        html.tostring(child, encoding='unicode', method='html') for child in root)


def _render_html(value, body_format):
    source = value or ''
    if normalize_body_format(body_format) == BODY_FORMAT_MARKDOWN:
        try:
            source = markdown(source, extensions=['extra', 'sane_lists', 'codehilite',
                                        ListIndentExtension(), MathExtension(),
                                        TaskListExtension()],
                              extension_configs={'codehilite': {
                                  'guess_lang': False,
                                  'pygments_formatter': CodeFormatter,
                              }})
        except Exception:
            current_app.logger.exception('Markdown rendering failed')
            return str(escape(value or ''))
    return sanitize_html(split_hard_breaks(source))


def render_content(value, body_format, images=True):
    rendered = _render_html(value, body_format)
    return Markup(optimize_images(rendered) if images else rendered)


def render_article(value, body_format):
    """Render a sanitized article and build links without replacing existing IDs."""
    rendered = _render_html(value, body_format)
    root = html.fragment_fromstring(rendered, create_parent='div')
    used = {element.get('id') for element in root.iter() if element.get('id') is not None}
    entries = []
    for heading in root.iter('h2', 'h3'):
        title = ' '.join(heading.text_content().split())
        anchor = heading.get('id')
        if anchor is None:
            normalized = unicodedata.normalize('NFKC', title).lower()
            slug = ''.join(char if char.isalnum() or char in '_-' else ' ' for char in normalized)
            slug = re.sub(r'[-\s]+', '-', slug).strip('-') or 'section'
            anchor = slug
            suffix = 2
            while anchor in used:
                anchor = f'{slug}-{suffix}'
                suffix += 1
            heading.set('id', anchor)
            used.add(anchor)
        entries.append({'title': title, 'level': heading.tag, 'href': '#' + quote(anchor, safe='')})
    result = str(escape(root.text or '')) + ''.join(
        html.tostring(child, encoding='unicode', method='html') for child in root)
    return (Markup(optimize_images(sanitize_html(result))),
            entries if len(entries) >= 3 else [])


# Count CJK characters separately from whitespace-delimited words.
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af\u3040-\u30ff\uac00-\ud7af]")
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)

def reading_minutes(value, body_format):
    rendered = render_content(value, body_format)
    root = html.fragment_fromstring(str(rendered), create_parent='div')
    text = ' '.join(root.itertext())
    cjk_count = len(_CJK.findall(text))
    words = len(_WORD.findall(_CJK.sub(' ', text)))
    return max(1, math.ceil(cjk_count / 400 + words / 200))
