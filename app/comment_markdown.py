"""Comment text is Markdown, narrowed to what a comment needs.

Raw HTML is shown as text (it is escaped before Markdown sees it), bare URLs
outside code and links become anchors, and nh3 drops everything outside a short
tag allowlist while marking every link untrusted.
"""
import re

import markdown
import nh3
from lxml import html as lxml_html
from markupsafe import Markup, escape

ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'li', 'ol', 'p', 'pre', 'strong',
    'ul',
}
ALLOWED_ATTRIBUTES = {'a': {'href', 'title'}}
ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}
LINK_REL = 'nofollow ugc noopener'

# Stop before whitespace, HTML delimiters, and CJK/full-width text so bare URLs
# inside Chinese sentences do not swallow adjacent prose or punctuation.
_BARE_URL = re.compile(r'https?://[^\s<>"\'\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]+')
_TRAILING_PUNCT = '.,;:!?)'
_SKIP_LINKIFY_TAGS = frozenset({'a', 'pre', 'code'})

_CLEANER = nh3.Cleaner(
    tags=ALLOWED_TAGS,
    clean_content_tags={'script', 'style'},
    attributes=ALLOWED_ATTRIBUTES,
    url_schemes=ALLOWED_PROTOCOLS,
    link_rel=LINK_REL,
    set_tag_attribute_values={'a': {'target': '_blank'}},
)


def _split_url_tail(raw: str) -> tuple[str, str]:
    url = raw
    while url and url[-1] in _TRAILING_PUNCT:
        if url[-1] == ')' and url.count('(') >= url.count(')'):
            break
        url = url[:-1]
    return url, raw[len(url):]


def _linkify_text(text: str) -> tuple[str, list[lxml_html.HtmlElement]]:
    matches = list(_BARE_URL.finditer(text))
    if not matches:
        return text, []
    lead = text[:matches[0].start()]
    elements: list[lxml_html.HtmlElement] = []
    for index, match in enumerate(matches):
        url, trailing = _split_url_tail(match.group(0))
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        after = trailing + text[match.end():next_start]
        if url:
            anchor = lxml_html.Element('a')
            anchor.set('href', url)
            anchor.text = url
            anchor.tail = after
            elements.append(anchor)
        elif elements:
            elements[-1].tail = (elements[-1].tail or '') + after
        else:
            lead += after
    return lead, elements


def _linkify_html(rendered: str) -> str:
    if 'http://' not in rendered and 'https://' not in rendered:
        return rendered
    root = lxml_html.fragment_fromstring(rendered, create_parent='div')

    def walk(node: lxml_html.HtmlElement) -> None:
        if node.tag in _SKIP_LINKIFY_TAGS:
            return
        if node.text:
            lead, anchors = _linkify_text(node.text)
            if anchors:
                node.text = lead
                for offset, anchor in enumerate(anchors):
                    node.insert(offset, anchor)
        idx = 0
        while idx < len(node):
            child = node[idx]
            walk(child)
            if child.tail:
                lead, anchors = _linkify_text(child.tail)
                if anchors:
                    child.tail = lead
                    for offset, anchor in enumerate(anchors, start=1):
                        node.insert(idx + offset, anchor)
                    idx += len(anchors)
            idx += 1

    walk(root)
    return str(escape(root.text or '')) + ''.join(
        lxml_html.tostring(child, encoding='unicode', method='html') for child in root
    )


def render_comment(text: str | None) -> Markup:
    source = (text or '').replace('&', '&amp;').replace('<', '&lt;')
    rendered = markdown.markdown(
        source, extensions=['fenced_code', 'nl2br'], output_format='html')
    linked = _linkify_html(rendered)
    return Markup(_CLEANER.clean(linked))
