"""Comment text is Markdown, narrowed to what a comment needs.

Raw HTML is shown as text (it is escaped before Markdown sees it), bleach then
drops everything outside a short tag list, and every link is marked untrusted.
"""
import bleach
import markdown
from markupsafe import Markup

ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'li', 'ol', 'p', 'pre', 'strong',
    'ul',
}
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}
ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}
LINK_REL = 'nofollow ugc noopener'


def _mark_link(attrs, new=False):
    attrs[(None, 'rel')] = LINK_REL
    attrs[(None, 'target')] = '_blank'
    return attrs


def render_comment(text):
    source = (text or '').replace('&', '&amp;').replace('<', '&lt;')
    rendered = markdown.markdown(
        source, extensions=['fenced_code', 'nl2br'], output_format='html')
    cleaned = bleach.clean(
        rendered, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS, strip=True)
    linked = bleach.linkify(
        cleaned, callbacks=[_mark_link], skip_tags={'pre', 'code'},
        parse_email=False)
    return Markup(linked)
