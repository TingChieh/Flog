"""Public post search and safe result presentation."""
import re
from html.parser import HTMLParser

import sqlalchemy as sa
import sqlalchemy.orm as so
from markupsafe import Markup, escape
from sqlalchemy.exc import OperationalError
from flask import url_for

from app import db
from app.models import Post
from app.content import render_content


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(source, body_format='html'):
    if body_format == 'markdown':
        source = str(render_content(source, body_format, images=False))
    parser = _Text()
    parser.feed(source or '')
    return ' '.join(' '.join(parser.parts).split())


# A listing shows two lines of a post (about 70 characters at most); more text
# only adds page weight and pulls in more font pieces.
EXCERPT_LENGTH = 120


def excerpt(source, body_format='html', title='', length=EXCERPT_LENGTH):
    """The opening of a post for a list, without the title it often starts with."""
    text = plain_text(source, body_format)
    title = ' '.join((title or '').split())
    # Old posts open with a date line and then the title; skip up to the title.
    index = text.find(title, 0, len(title) + 20) if title else -1
    if index >= 0 and text[index + len(title):].strip():
        text = text[index + len(title):].lstrip(' ：:，,。')
    return text if len(text) <= length else text[:length].rstrip() + '…'


def snippet(body, query, length=180, body_format='html'):
    value = plain_text(body, body_format)
    match = re.search(re.escape(query), value, flags=re.IGNORECASE) if query else None
    index = match.start() if match else -1
    start = max(0, index - 55) if index >= 0 else 0
    if match:
        length = max(length, match.end() - start)
    result = value[start:start + length]
    return ('…' if start else '') + result + ('…' if start + length < len(value) else '')


def highlight(value, query):
    if not query:
        return escape(value)
    parts = re.split('(' + re.escape(query) + ')', value, flags=re.IGNORECASE)
    return Markup('').join(Markup('<mark>') + escape(part) + Markup('</mark>')
                           if i % 2 else escape(part)
                           for i, part in enumerate(parts))


def highlight_segments(value, query):
    parts = re.split('(' + re.escape(query) + ')', value, flags=re.IGNORECASE) if query else [value]
    return [{'text': part, 'highlight': bool(i % 2)} for i, part in enumerate(parts) if part]


def search_posts(query, limit=20, offset=0, count=False):
    if not query:
        return 0 if count else []
    title_match = Post.title.icontains(query, autoescape=True)
    body_match = Post.body.icontains(query, autoescape=True)
    statement = sa.select(Post).where(Post.is_published.is_(True))
    connection = db.session.connection()
    from app.search_index import search_index_available
    use_fts = (len(query) >= 3 and '\x00' not in query
               and search_index_available(connection))
    # LIKE preserves literal substring semantics even when the tokenizer folds text.
    statement = statement.where(sa.or_(title_match, body_match))
    if count:
        statement = statement.with_only_columns(sa.func.count())
    else:
        statement = statement.options(so.selectinload(Post.category)).order_by(
            sa.case((title_match, 0), else_=1), Post.timestamp.desc(), Post.id.desc()
        ).offset(offset).limit(limit)
    if use_fts:
        # A quoted phrase makes operators, quotes and punctuation literal text.
        phrase = '"' + query.replace('"', '""') + '"'
        index_query = sa.text('SELECT rowid FROM post_search WHERE post_search MATCH :fts_query').bindparams(fts_query=phrase)
        try:
            indexed = statement.where(Post.id.in_(index_query))
            return db.session.scalar(indexed) if count else db.session.scalars(indexed).all()
        except OperationalError:
            pass
    return db.session.scalar(statement) if count else db.session.scalars(statement).all()



def result_data(post, query):
    excerpt = snippet(post.body, query, body_format=post.body_format)
    return {'title': post.title, 'title_segments': highlight_segments(post.title or '', query),
            'snippet': highlight(excerpt, query), 'snippet_segments': highlight_segments(excerpt, query),
            'date': post.local_timestamp.strftime('%Y-%m-%d'),
            'url': url_for('post', post_id=post.id)}
