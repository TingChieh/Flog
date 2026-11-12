"""Start fetching the article font pieces a page needs before the CSS asks.

Noto Serif SC is split into ~170 range-based files, and the browser only
discovers which ones a page needs after it has parsed the stylesheet and laid
the text out. Until a piece arrives the Chinese text is set in a fallback face,
then swaps and reflows. Naming the needed pieces in ``<link rel="preload">``
tags lets them download alongside the stylesheet, so they are usually there
before the first paint and nothing visibly jumps.

A page's pieces are fetched whether or not they are preloaded, so the cap only
guards against a pathological page, not bandwidth.

The full ``article-fonts.css`` is 70 KB even compressed, and a stylesheet
holds back the first paint until it arrives. So the page carries its own
``@font-face`` rules inline: the Source Serif faces, and one rule per needed
Noto piece whose ``unicode-range`` lists only the characters on the page. The
full stylesheet then loads without blocking, for text that appears later
(search results, a comment being typed). Responses this hook leaves alone keep
the blocking stylesheet. The faces use
``font-display: block``: text a piece has not yet delivered stays invisible
for a moment instead of showing in a fallback face and then changing shape.
"""
import html
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from flask import url_for

from app import app

FONTS = Path(app.static_folder) / 'fonts'
MAX_PRELOADED = 32
FACE_RE = re.compile(r'@font-face\s*\{([^}]+)\}')
STYLESHEET_RE = re.compile(r'<link rel="stylesheet" href="([^"]*/fonts/article-fonts\.css[^"]*)">')
NOTO_FACE = ("@font-face{font-family:'Noto Serif SC';font-style:normal;"
             "font-weight:400 700;font-display:block;src:url('%s') format('woff2');"
             "unicode-range:%s}")
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
    noto, latin, _ = _faces()
    return noto, latin


@lru_cache(maxsize=1)
def _faces():
    """The pieces as _pieces() gives them, plus the Source Serif rules as CSS."""
    css = (FONTS / 'article-fonts.css').read_text()
    noto, latin, serif = {}, set(), []
    for face in FACE_RE.findall(css):
        family = re.search(r"font-family:\s*'([^']+)'", face).group(1)
        points = _codepoints(re.search(r'unicode-range:\s*([^;]+);', face).group(1))
        filename = re.search(r"url\('([^']+)'\)", face).group(1)
        if family == 'Noto Serif SC':
            for point in points:
                noto.setdefault(point, filename)
        else:
            latin.update(points)
            serif.append(' '.join(face.split()))
    return noto, latin, serif


def _characters(markup):
    """{Noto file: [codepoints of ``markup``'s visible text it covers]}, most used first."""
    noto, latin = _pieces()
    text = html.unescape(INVISIBLE_RE.sub(' ', markup))
    # Weigh each file by how much text it covers, not by how many glyphs.
    weights = Counter()
    points = {}
    for char in text:
        point = ord(char)
        if point > 0x7F and point not in latin and point in noto:
            weights[noto[point]] += 1
            points.setdefault(noto[point], set()).add(point)
    return {name: sorted(points[name]) for name, _ in weights.most_common()}


def needed_files(markup):
    """The Noto Serif SC files for ``markup``'s visible text, most used first."""
    return list(_characters(markup))[:MAX_PRELOADED]


def _unicode_range(points):
    """U+ ranges covering exactly ``points`` (sorted), consecutive ones merged."""
    runs = []
    for point in points:
        if runs and point == runs[-1][1] + 1:
            runs[-1][1] = point
        else:
            runs.append([point, point])
    return ','.join(f'U+{start:x}' if start == end else f'U+{start:x}-{end:x}'
                    for start, end in runs)


def inline_faces(characters):
    """The @font-face rules a page needs, for its own <style>."""
    # The stylesheet's urls are relative to the fonts folder; a page's are not.
    folder = url_for('static', filename='fonts/')
    _, _, serif = _faces()
    rules = ['@font-face{%s}' % face.replace("url('", f"url('{folder}") for face in serif]
    rules += [NOTO_FACE % (folder + name, _unicode_range(points))
              for name, points in characters.items()]
    return ''.join(rules)


def _load_later(match):
    """The full font stylesheet, loaded without holding back the first paint."""
    href = match.group(1)
    return (f'<link rel="stylesheet" href="{href}" media="print" '
            f'onload="this.media=\'all\'">'
            f'<noscript><link rel="stylesheet" href="{href}"></noscript>')


@app.after_request
def preload_article_fonts(response):
    if (response.status_code != 200 or response.mimetype != 'text/html'
            or response.direct_passthrough or response.is_streamed):
        return response
    markup = response.get_data(as_text=True)
    head_end = markup.find(HEAD_END)
    if head_end < 0:
        return response
    characters = _characters(markup[head_end:])
    if not characters:
        return response
    links = ''.join(
        '<link rel="preload" as="font" type="font/woff2" crossorigin href="%s">'
        % html.escape(url_for('static', filename=f'fonts/{name}'))
        for name in list(characters)[:MAX_PRELOADED])
    head = STYLESHEET_RE.sub(_load_later, markup[:head_end], count=1)
    style = f'<style>{inline_faces(characters)}</style>'
    response.set_data(head + style + links + markup[head_end:])
    return response
