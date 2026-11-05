import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app import db
from app.models import Post, User


@pytest.fixture
def search_posts(application):
    with application.app_context():
        user = User(username='searcher', email='search@example.com')
        db.session.add(user)
        db.session.flush()
        db.session.add_all([
            Post(title='中文搜索指南', body='学习 Python 和数据库', author=user, is_published=True),
            Post(title='Python notes', body='中文搜索指南 and English', author=user, is_published=True),
            Post(title='Secret 中文搜索指南', body='secret', author=user, is_published=False),
            Post(title='Unsafe', body='<script>alert(1)</script> 中文搜索指南', author=user, is_published=True),
        ])
        db.session.commit()


def test_search_public_title_ranking_and_safe_highlight(client, search_posts):
    response = client.get('/search', query_string={'q': '中文搜索指南'})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    titles = [r['title'] for r in client.get('/api/search', query_string={'q': '中文搜索指南'}).json['results']]
    assert titles.index('中文搜索指南') < titles.index('Python notes')
    assert 'Secret 中文搜索指南' not in html
    assert '<mark>中文搜索指南</mark>' in html
    assert '<script>alert(1)</script>' not in html


@pytest.mark.parametrize('query, expected', [
    ('Python', 'Python notes'), ('中文', '中文搜索指南'),
    ('数据库', '中文搜索指南'), ('中文搜索指南 and English', 'Python notes'),
    ('no-such-result', None), ('" OR * (', None), ('<script>', 'Unsafe'),
])
def test_search_json_queries(client, search_posts, query, expected):
    response = client.get('/api/search', query_string={'q': query})
    assert response.status_code == 200
    titles = [item['title'] for item in response.json['results']]
    assert (expected in titles) if expected else not titles
    assert 'Secret 中文搜索指南' not in titles


def test_index_sync_and_rebuild_command(client, application, search_posts):
    with application.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('SQLite FTS5 index and triggers are unavailable on MySQL')
        from app.search_index import rebuild_search_index
        assert rebuild_search_index(db.session.connection())
        db.session.commit()
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        post = Post(title='新鲜文章', body='original', author=user, is_published=True)
        db.session.add(post)
        db.session.commit()
        post_id = post.id
    assert client.get('/api/search?q=新鲜文章').json['results'][0]['title'] == '新鲜文章'
    with application.app_context():
        post = db.session.get(Post, post_id)
        post.title = '更新文章'
        db.session.commit()
    assert not client.get('/api/search?q=新鲜文章').json['results']
    assert client.get('/api/search?q=更新文章').json['results']
    with application.app_context():
        post = db.session.get(Post, post_id)
        post.is_published = False
        db.session.commit()
    assert not client.get('/api/search?q=更新文章').json['results']
    with application.app_context():
        post = db.session.get(Post, post_id)
        post.is_published = True
        db.session.commit()
    assert client.get('/api/search?q=更新文章').json['results']
    with application.app_context():
        db.session.delete(db.session.get(Post, post_id))
        db.session.commit()
    assert not client.get('/api/search?q=更新文章').json['results']
    result = application.test_cli_runner().invoke(args=['rebuild-search-index'])
    assert result.exit_code == 0, result.output
    assert client.get('/api/search?q=中文搜索指南').json['results']


def test_search_migration_preserves_existing_posts():
    path = Path(__file__).parents[1] / 'migrations/versions/b5e1a7c9d234_add_search_index.py'
    spec = importlib.util.spec_from_file_location('search_migration', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, body TEXT, is_published BOOLEAN)'))
        connection.execute(sa.text('INSERT INTO post VALUES (1, :title, :body, 1)'), {'title': '原有文章', 'body': '<p>Existing</p>'})
        before = connection.execute(sa.text('SELECT * FROM post')).all()
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.execute(sa.text('SELECT * FROM post')).all() == before
        assert connection.execute(sa.text('SELECT rowid FROM post_search WHERE post_search MATCH :q'), {'q': '"原有文章"'}).all() == [(1,)]


def test_trigram_search_handles_literal_punctuation(client, application, search_posts):
    with application.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('SQLite FTS5 trigram index is unavailable on MySQL')
        from app.search_index import rebuild_search_index
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add_all([
            Post(title='Punctuation', body='literal +++ and 100%_done', author=user, is_published=True),
            Post(title='Almost', body='literal xxx and 100ABdone', author=user, is_published=True),
        ])
        db.session.commit()
        rebuild_search_index(db.session.connection())
        db.session.commit()
    assert [r['title'] for r in client.get('/api/search', query_string={'q': '+++'}).json['results']] == ['Punctuation']
    assert [r['title'] for r in client.get('/api/search', query_string={'q': '100%_done'}).json['results']] == ['Punctuation']


def test_search_escapes_hostile_query_and_post_text(client, application, search_posts):
    with application.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add(Post(title='<img src=x onerror=alert(1)>', body='literal <img src=x onerror=alert(1)>', author=user, is_published=True))
        db.session.commit()
    response = client.get('/search', query_string={'q': '<img src=x onerror=alert(1)>'})
    html = response.get_data(as_text=True)
    assert '<img src=x onerror=alert(1)>' not in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html


def test_search_header_is_chinese_whatever_the_browser_language(client, application):
    for language in ('zh', 'en'):
        with application.app_context():
            page = client.get('/', headers={'Accept-Language': language}).get_data(as_text=True)
        assert '<span>搜索</span>' in page


def test_migration_does_not_touch_a_preexisting_table_with_the_index_name():
    path = Path(__file__).parents[1] / 'migrations/versions/b5e1a7c9d234_add_search_index.py'
    spec = importlib.util.spec_from_file_location('search_migration_collision', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, body TEXT, is_published BOOLEAN)'))
        connection.execute(sa.text('CREATE TABLE post_search (rowid INTEGER, title TEXT, body TEXT)'))
        connection.execute(sa.text("INSERT INTO post_search VALUES (7, 'preserve', 'existing data')"))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.execute(sa.text('SELECT * FROM post_search')).all() == [(7, 'preserve', 'existing data')]


def test_migration_preserves_case_insensitive_index_name_collision():
    path = Path(__file__).parents[1] / 'migrations/versions/b5e1a7c9d234_add_search_index.py'
    spec = importlib.util.spec_from_file_location('search_migration_case_collision', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, body TEXT, is_published BOOLEAN)'))
        connection.execute(sa.text('CREATE TABLE Post_Search (rowid INTEGER, title TEXT, body TEXT)'))
        connection.execute(sa.text("INSERT INTO Post_Search VALUES (7, 'preserve', 'existing data')"))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.execute(sa.text('SELECT * FROM Post_Search')).all() == [(7, 'preserve', 'existing data')]


def test_migration_downgrade_preserves_unrelated_existing_objects():
    path = Path(__file__).parents[1] / 'migrations/versions/b5e1a7c9d234_add_search_index.py'
    spec = importlib.util.spec_from_file_location('search_migration_owner_collision', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, body TEXT, is_published BOOLEAN)'))
        connection.execute(sa.text('CREATE TABLE post_search (id INTEGER PRIMARY KEY, contents TEXT)'))
        connection.execute(sa.text('CREATE TABLE flog_search_index_owner (id INTEGER PRIMARY KEY)'))
        connection.execute(sa.text("INSERT INTO post_search VALUES (7, 'preserve')"))
        connection.execute(sa.text('INSERT INTO flog_search_index_owner VALUES (2)'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            revision.downgrade()
        assert connection.execute(sa.text('SELECT * FROM post_search')).all() == [(7, 'preserve')]
        assert connection.execute(sa.text('SELECT * FROM flog_search_index_owner')).all() == [(2,)]


def test_unrelated_index_and_triggers_use_like_fallback(client, application, search_posts):
    with application.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('SQLite FTS5 virtual tables and triggers are unavailable on MySQL')
        connection = db.session.connection()
        for name in ('post_search_insert', 'post_search_update', 'post_search_delete'):
            connection.exec_driver_sql('DROP TRIGGER IF EXISTS ' + name)
        connection.exec_driver_sql('DROP TABLE IF EXISTS post_search')
        connection.exec_driver_sql("CREATE VIRTUAL TABLE post_search USING fts5(title, body, tokenize='trigram')")
        for operation, name in [('INSERT', 'post_search_insert'), ('UPDATE', 'post_search_update'), ('DELETE', 'post_search_delete')]:
            connection.exec_driver_sql(f'CREATE TRIGGER {name} AFTER {operation} ON post BEGIN SELECT 1; END')
        db.session.commit()
    results = client.get('/api/search?q=中文搜索指南').json['results']
    assert any(result['title'] == '中文搜索指南' for result in results)


@pytest.mark.parametrize('query,title,expected', [
    ('中文搜索指南', 'Python notes', '<mark>中文搜索指南</mark> and English'),
    ('English', 'Python notes', '中文搜索指南 and <mark>English</mark>'),
    ('中文', 'Python notes', '<mark>中文</mark>搜索指南 and English'),
])
def test_json_snippet_highlights_matching_text(client, search_posts, query, title, expected):
    results = client.get('/api/search', query_string={'q': query}).json['results']
    assert next(item for item in results if item['title'] == title)['snippet'] == expected


def test_search_highlights_title_and_escapes_json_snippet(client, application, search_posts):
    with application.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add(Post(title='Needle <img src=x onerror=alert(1)>',
                            body='needle &lt;img src=x onerror=alert(1)&gt;', author=user, is_published=True))
        db.session.commit()
    result = next(item for item in client.get('/api/search?q=needle').json['results'] if item['title'].startswith('Needle'))
    assert result['snippet'] == '<mark>needle</mark> &lt;img src=x onerror=alert(1)&gt;'
    assert result['title_segments'][0] == {'text': 'Needle', 'highlight': True}
    html = client.get('/search?q=needle').get_data(as_text=True)
    assert '<mark>Needle</mark>' in html
    assert '<img src=x onerror=alert(1)>' not in html


@pytest.mark.parametrize('indexed', [False, True])
def test_snippet_centers_late_match_with_or_without_trigram_index(client, application, search_posts, indexed):
    with application.app_context():
        if indexed and db.engine.dialect.name != 'sqlite':
            pytest.skip('SQLite FTS5 trigram index is unavailable on MySQL')
        from app.search_index import rebuild_search_index
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add(Post(title='Long body', body='prefix ' * 80 + '中文搜索 needle',
                            author=user, is_published=True))
        db.session.commit()
        if indexed:
            assert rebuild_search_index(db.session.connection())
            db.session.commit()
    result = next(item for item in client.get('/api/search?q=中文搜索').json['results'] if item['title'] == 'Long body')
    assert result['snippet'].startswith('…')
    assert '<mark>中文搜索</mark>' in result['snippet']


def test_snippet_includes_full_long_query(client, application, search_posts):
    query = 'abcdefghij' * 19
    with application.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add(Post(title='Long query', body='prefix ' + query, author=user, is_published=True))
        db.session.commit()
    result = next(item for item in client.get('/api/search', query_string={'q': query}).json['results'] if item['title'] == 'Long query')
    assert '<mark>' + query + '</mark>' in result['snippet']


def test_markdown_excerpts_are_plain_before_highlighting(client, application, search_posts):
    with application.app_context():
        user = db.session.scalar(sa.select(User).where(User.username == 'searcher'))
        db.session.add(Post(title='Markup example', author=user, is_published=True,
            body_format='markdown', body='# Heading\n\n**needle** _emphasis_ `inline` [link](https://example.com) ![alt](image.png)\n\n> quote\n\n- item\n\n```python\ncode\n```\n\n<b>html</b>'))
        db.session.commit()
    result = next(item for item in client.get('/api/search?q=needle').json['results'] if item['title'] == 'Markup example')
    assert result['snippet'] == 'Heading <mark>needle</mark> emphasis inline link quote item code html'
    assert result['snippet_segments'][1] == {'text': 'needle', 'highlight': True}
    html = client.get('/search?q=needle').get_data(as_text=True)
    assert result['snippet'] in html
    home = client.get('/').get_data(as_text=True)
    assert 'Heading needle emphasis inline link quote item code html' in home
