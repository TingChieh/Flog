"""Executable architecture, security boundary, and query-budget invariants."""
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from lxml import html as lxml_html
from sqlalchemy import event

from app import db
from app.comment_markdown import render_comment
from app.content import render_article, render_content
from app.models import Category, Post, PostComment, User
from app.security import is_local_path, sanitize_html
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / 'app' / 'templates'
APP_DIR = ROOT / 'app'

APPROVED_MARKUP_MODULES = frozenset({
    'app/security.py',
    'app/content.py',
    'app/comment_markdown.py',
    'app/search.py',
})


def test_templates_never_bypass_autoescape_with_safe_filter():
    pattern = re.compile(r'\|\s*safe\b')
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted(TEMPLATES_DIR.rglob('*.html'))
        if pattern.search(path.read_text(encoding='utf-8'))
    ]
    assert offenders == []


def test_templates_never_execute_direct_database_queries():
    pattern = re.compile(r'\b(db\.session|sa\.select)\b|\.query\b')
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted(TEMPLATES_DIR.rglob('*.html'))
        if pattern.search(path.read_text(encoding='utf-8'))
    ]
    assert offenders == []


def test_markup_construction_is_confined_to_sanitizing_modules():
    offenders = []
    for path in sorted(APP_DIR.rglob('*.py')):
        rel = str(path.relative_to(ROOT))
        if rel in APPROVED_MARKUP_MODULES:
            continue
        if 'Markup(' in path.read_text(encoding='utf-8'):
            offenders.append(rel)
    assert offenders == []


def _assert_safe_dom(markup: str) -> None:
    root = lxml_html.fragment_fromstring(markup or '', create_parent='div')
    forbidden_tags = {'script', 'iframe', 'svg', 'form', 'meta', 'object', 'embed', 'style'}
    for el in root.iter():
        assert el.tag not in forbidden_tags, f'Forbidden tag <{el.tag}> in {markup!r}'
        for attr, val in el.attrib.items():
            attr_lower = attr.lower()
            val_lower = (val or '').strip().lower()
            assert not attr_lower.startswith('on'), f'Event handler {attr} in {markup!r}'
            if attr_lower in {'href', 'src', 'action'}:
                assert not val_lower.startswith(('javascript:', 'vbscript:', 'data:')), (
                    f'Dangerous URI {attr}={val!r} in {markup!r}'
                )
            if attr_lower == 'style':
                assert 'javascript:' not in val_lower and 'expression(' not in val_lower


@pytest.mark.parametrize('payload', [
    '<script>alert(1)</script>',
    '<img src="x" onerror="alert(1)">',
    '<svg onload="alert(1)"><circle r="10"/></svg>',
    '<iframe src="https://evil.example"></iframe>',
    '<a href="javascript:alert(1)">click</a>',
    '<a href="vbscript:msgbox(1)">click</a>',
    '<a href="data:text/html,<script>alert(1)</script>">click</a>',
    '<p style="background:url(javascript:alert(1))">styled</p>',
    '<form action="https://evil.example"><input name="pw"></form>',
    '<meta http-equiv="refresh" content="0;url=https://evil.example">',
])
def test_markdown_and_html_sanitization_neutralizes_xss_vectors(application, payload):
    with application.app_context():
        cleaned = sanitize_html(payload)
        md_rendered = str(render_content(payload, 'markdown'))
        article_rendered, _ = render_article(payload, 'markdown')
        comment_rendered = str(render_comment(payload))

    for output in (cleaned, md_rendered, str(article_rendered), comment_rendered):
        _assert_safe_dom(output)


def test_markdown_dangerous_links_and_images_are_stripped(application):
    source = (
        '[bad](javascript:alert(1))\n\n'
        '![img](javascript:alert(2))\n\n'
        '[ok](https://example.com/path?a=1&b=2)\n'
    )
    with application.app_context():
        rendered = str(render_content(source, 'markdown'))
    assert 'javascript:' not in rendered.lower()
    assert 'href="https://example.com/path?a=1&amp;b=2"' in rendered


def test_jinja_autoescapes_hostile_post_and_search_metadata(client, application, users):
    hostile = '<script>window.__xss=1</script>'
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post is not None
        post.title = hostile
        post.body = '<p>safe body</p>'
        db.session.commit()

    for url in ('/', f'/post/{users["post"]}', '/archive', f'/search?q={hostile}'):
        body = client.get(url).get_data(as_text=True)
        assert hostile not in body
        assert '&lt;script&gt;window.__xss=1&lt;/script&gt;' in body


@pytest.mark.parametrize(('target', 'expected'), [
    ('/admin/comments', True),
    ('/admin/comments?status=pending&page=2', True),
    ('//evil.example/admin/comments', False),
    ('/\\evil.example', False),
    ('/admin/comments\r\nSet-Cookie: a=1', False),
    ('https://evil.example', False),
    ('', False),
    (None, False),
])
def test_is_local_path_blocks_open_redirects(target, expected):
    assert is_local_path(target) is expected


def test_admin_comments_redirect_rejects_control_chars_and_external_hosts(client, application, users):
    with application.app_context():
        comment = PostComment(
            post_id=users['post'], name='Reader', email='reader@example.com',
            body='hello', status='pending')
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id

    login(client, 'admin')
    for bad_next in ('//evil.example/admin/comments', '/admin/comments\r\nx:1', '/admin/comments\\evil'):
        resp = client.post(
            f'/admin/comments/{comment_id}/approve',
            data={'next': bad_next},
        )
        assert resp.status_code == 302
        assert resp.headers['Location'] == '/admin/comments'


def test_public_routes_stay_within_sql_query_budgets(client, application):
    with application.app_context():
        author = User(username='perf_author', email='perf@example.com', role='admin')
        author.set_password('password')
        category = Category(name='Engineering')
        db.session.add_all([author, category])
        db.session.flush()
        for i in range(1, 13):
            db.session.add(Post(
                title=f'文章 {i}',
                body='## 第一节\n\n内容测试\n\n## 第二节\n\n更多\n\n## 第三节\n\n结尾',
                body_format='markdown',
                author=author,
                category=category,
                is_published=True,
            ))
        db.session.flush()
        first_post = db.session.scalar(sa.select(Post).order_by(Post.id))
        assert first_post is not None
        first_post_id = first_post.id
        for j in range(3):
            db.session.add(PostComment(
                post_id=first_post_id, name=f'User{j}', email=f'u{j}@example.com',
                body='评论内容', status='approved'))
        db.session.commit()

    def count_queries(path):
        queries: list[str] = []

        def listener(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        with application.app_context():
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                response = client.get(path)
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
        return response.status_code, len(queries)

    budgets = {
        '/': (200, 8),
        f'/post/{first_post_id}': (200, 12),
        '/archive': (200, 6),
        '/search?q=文章': (200, 7),
        '/feed.xml': (200, 3),
        '/sitemap.xml': (200, 4),
        '/nonexistent-page-budget': (404, 6),
    }
    for path, (expected_status, max_queries) in budgets.items():
        status, count = count_queries(path)
        assert status == expected_status, path
        assert count <= max_queries, f'{path} ran {count} queries (budget {max_queries})'

    # Repeat visit with the view cookie skips the view-count UPDATE/refresh path.
    repeat_status, repeat_count = count_queries(f'/post/{first_post_id}')
    assert repeat_status == 200
    assert repeat_count <= 8, f'repeat /post/{first_post_id} ran {repeat_count} queries (budget 8)'
