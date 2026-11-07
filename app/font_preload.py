"""Start fetching the article font pieces a page needs before the CSS asks.

Noto Serif SC is split into ~170 range-based files, and the browser only
discovers which ones a page needs after it has parsed the stylesheet and laid
the text out. Until a piece arrives the Chinese text is set in a fallback face,
then swaps and reflows. Naming the needed pieces in ``<link rel="preload">``
tags lets them download alongside the stylesheet, so they are usually there
before the first paint and nothing visibly jumps.
"""
import html
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from flask import url_for

from app import app

FONTS = Path(app.static_folder) / 'fonts'
MAX_PRELOADED = 8
FACE_RE = re.compile(r'@font-face\s*\{([^}]+)\}')
INVISIBLE_RE = re.compile(r'<(script|style)\b.*?</\1\s*>|<[^>]+>', re.DOTALL | re.IGNORECASE)
HEAD_END = '</head>'


def _codepoints(unicode_range):
    for token in unicode_range.split(','):
        start, _, end = token.strip()[2:].partition('-')
        if '?' in start:
            continue
        yield from range(int(start, 16), int(end or start, 16) + 1)


@lru_cache(maxsize=1)
def _pieces():
    """Return (codepoint -> Noto file, codepoints Source Serif already covers)."""
    css = (FONTS / 'article-fonts.css').read_text()
    noto, latin = {}, set()
    for face in FACE_RE.findall(css):
        family = re.search(r"font-family:\s*'([^']+)'", face).group(1)
        points = _codepoints(re.search(r'unicode-range:\s*([^;]+);', face).group(1))
        if family == 'Noto Serif SC':
            filename = re.search(r"url\('([^']+)'\)", face).group(1)
            for point in points:
                noto.setdefault(point, filename)
        else:
            latin.update(points)
    return noto, latin


def needed_files(markup):
    """The Noto Serif SC files for ``markup``'s visible text, most used first."""
    noto, latin = _pieces()
    text = html.unescape(INVISIBLE_RE.sub(' ', markup))
    # Weigh each file by how much text it covers, not by how many glyphs.
    weights = Counter(noto[ord(char)] for char in text
                      if ord(char) > 0x7F and ord(char) not in latin and ord(char) in noto)
    return [name for name, _ in weights.most_common(MAX_PRELOADED)]


@app.after_request
def preload_article_fonts(response):
    if (response.status_code != 200 or response.mimetype != 'text/html'
            or response.direct_passthrough or response.is_streamed):
        return response
    markup = response.get_data(as_text=True)
    head_end = markup.find(HEAD_END)
    if head_end < 0:
        return response
    files = needed_files(markup[head_end:])
    if not files:
        return response
    links = ''.join(
        '<link rel="preload" as="font" type="font/woff2" crossorigin href="%s">'
        % html.escape(url_for('static', filename=f'fonts/{name}'))
        for name in files)
    response.set_data(markup[:head_end] + links + markup[head_end:])
    return response
