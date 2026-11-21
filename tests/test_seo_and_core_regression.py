"""Core regression suite for SEO metadata, articles, and full-text search."""
from datetime import datetime, timezone
import json
from pathlib import Path

from lxml import etree, html as lxml_html

from app import db
from app.models import Category, Image, Page, Post, PostDraft, User
from app.search_index import rebuild_search_index, search_index_available
from tests.conftest import login, make_image


def _parse_html(response):
    return lxml_html.fromstring(response.get_data(as_text=True))


def _meta(doc, *, name=None, prop=None):
    if name is not None:
        nodes = doc.xpath(f'//meta[@name="{name}"]/@content')
    else:
        nodes = doc.xpath(f'//meta[@property="{prop}"]/@content')
    return nodes[0] if nodes else None


def _canonical(doc):
    nodes = doc.xpath('//link[@rel="canonical"]/@href')
    return nodes


def test_post_cover_and_structured_data_use_only_published_content(client, application, users):
    application.config['SITE_URL'] = 'https://canonical.example.org'
    filename = 'a' * 32 + '.png'
    uploads = Path(application.config['UPLOAD_FOLDER'])
    uploads.mkdir()
    (uploads / filename).write_bytes(make_image(size=(1200, 630)))
    post_id = users['post']
    headline = 'Same & </script><script>alert(1)</script>'
    with application.app_context():
        post = db.session.get(Post, post_id)
        post.title = headline
        post.body_format = 'markdown'
        post.body = f'![People & place](/files/{filename})'
        post.timestamp = datetime(2025, 2, 1, tzinfo=timezone.utc)
        post.updated_at = datetime(2025, 2, 5, tzinfo=timezone.utc)
        post.draft = PostDraft(title='Private title', body='![Private](https://private.example/a.png)')
        db.session.add(Image(filename=filename, original_name='cover.png', title='Cover',
                             size=100, width=1200, height=630))
        duplicate = Post(title=headline, author=post.author, body='Different article',
                         category=post.category, is_published=True)
        db.session.add(duplicate)
        db.session.commit()
        duplicate_id = duplicate.id

    response = client.get(f'/post/{post_id}?utm_campaign=example')
    doc = _parse_html(response)
    canonical = f'https://canonical.example.org/post/{post_id}'
    image = f'https://canonical.example.org/files/{filename}'
    assert _canonical(doc) == [canonical]
    assert doc.xpath('//meta[@property="og:image"]/@content') == [image]
    assert _meta(doc, name='twitter:image') == image
    assert _meta(doc, prop='og:image:width') == '1200'
    assert _meta(doc, prop='og:image:height') == '630'
    assert _meta(doc, prop='og:image:alt') == 'People & place'
    [raw] = doc.xpath('//script[@type="application/ld+json"]/text()')
    assert '</script>' not in raw
    data = json.loads(raw)
    assert data['@type'] == 'BlogPosting'
    assert data['headline'] == headline
    assert data['image'] == image
    assert data['url'] == data['mainEntityOfPage']['@id'] == canonical
    assert data['datePublished'] == '2025-02-01T00:00:00+00:00'
    assert data['dateModified'] == '2025-02-05T00:00:00+00:00'
    assert data['author']['name'] == 'author'
    assert data['publisher']['name'] == _meta(doc, prop='og:site_name')
    assert b'Private title' not in response.data

    other = _parse_html(client.get(f'/post/{duplicate_id}'))
    assert _canonical(other) == [f'https://canonical.example.org/post/{duplicate_id}']
    home = _parse_html(client.get('/'))
    fallback = _meta(home, prop='og:image')
    assert fallback and fallback.startswith('https://canonical.example.org/static/')
    assert _meta(other, prop='og:image') == fallback
    assert not home.xpath('//script[@type="application/ld+json"]')

    with application.app_context():
        db.session.get(Post, post_id).is_published = False
        db.session.commit()
    assert not _parse_html(client.get(f'/post/{post_id}')).xpath('//script[@type="application/ld+json"]')
    login(client, 'author')
    preview = client.get(f'/admin/posts/{post_id}/preview')
    assert not _parse_html(preview).xpath('//script[@type="application/ld+json"] | //meta[@property="og:image"]')


def test_page_alias_and_out_of_range_pagination_do_not_create_canonical_pages(client, application, users):
    with application.app_context():
        db.session.add(Page(title='Example', slug='example', body='Body', is_published=True))
        db.session.commit()

    alias = client.get('/Example?utm_source=x')
    assert alias.status_code == 301
    assert alias.location == '/example?utm_source=x'
    assert _canonical(_parse_html(client.get(alias.location))) == ['http://localhost/example']
    for path in ('/?page=2', '/index?page=9999999999999999999999'):
        response = client.get(path)
        assert response.status_code == 404
        assert _canonical(_parse_html(response)) == []
    assert _canonical(_parse_html(client.get('/archive?page=99'))) == ['http://localhost/archive']
    search = _parse_html(client.get('/search?q=Test&page=2'))
    assert _canonical(search) == []
    assert _meta(search, name='robots') == 'noindex, nofollow'


def test_seo_metadata_canonical_and_open_graph_on_public_pages(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post is not None
        post.title = '深入理解 Flask 工程化'
        post.body = '## 概览\n\n这是一篇关于工程质量与自动化验证的文章。'
        post.body_format = 'markdown'
        db.session.add(Page(
            title='关于本站', slug='about', summary='博客简介',
            body='<p>你好</p>', kind='content', is_published=True))
        db.session.commit()

    # Home and /index resolve to the exact same canonical URL.
    home = _parse_html(client.get('/', base_url='https://blog.example.com'))
    index_alias = _parse_html(client.get('/index', base_url='https://blog.example.com'))
    assert _canonical(home) == ['https://blog.example.com/']
    assert _canonical(index_alias) == ['https://blog.example.com/']
    assert _meta(home, prop='og:type') == 'website'
    assert _meta(home, prop='og:url') == 'https://blog.example.com/'
    assert _meta(home, prop='og:site_name')
    assert _meta(home, name='robots') is None
    assert len(home.xpath('//h1')) == 1

    # Article page strips tracking/reply query strings from canonical and uses og:type=article.
    post_resp = client.get(
        f'/post/{users["post"]}?utm_source=feed&reply=12',
        base_url='https://blog.example.com',
    )
    assert post_resp.status_code == 200
    post_doc = _parse_html(post_resp)
    expected_post_url = f'https://blog.example.com/post/{users["post"]}'
    assert _canonical(post_doc) == [expected_post_url]
    assert _meta(post_doc, prop='og:type') == 'article'
    assert _meta(post_doc, prop='og:url') == expected_post_url
    assert '深入理解 Flask 工程化' in (_meta(post_doc, prop='og:title') or '')
    assert '工程质量与自动化验证' in (_meta(post_doc, name='description') or '')
    assert _meta(post_doc, prop='og:description') == _meta(post_doc, name='description')
    assert _meta(post_doc, name='robots') is None
    assert len(post_doc.xpath('//h1')) == 1

    # Custom content page.
    page_doc = _parse_html(client.get('/about', base_url='https://blog.example.com'))
    assert _canonical(page_doc) == ['https://blog.example.com/about']
    assert _meta(page_doc, name='description') == '博客简介'
    assert len(page_doc.xpath('//h1')) == 1


def test_configured_site_url_unifies_canonical_sitemap_feed_and_robots(client, application, users):
    application.config['SITE_URL'] = 'https://canonical.example.org'

    home = _parse_html(client.get('/', base_url='http://127.0.0.1:5000'))
    assert _canonical(home) == ['https://canonical.example.org/']
    assert _meta(home, prop='og:url') == 'https://canonical.example.org/'

    feed = etree.fromstring(client.get('/feed.xml', base_url='http://127.0.0.1:5000').data)
    assert feed.findtext('./channel/link') == 'https://canonical.example.org/'
    assert feed.findtext('./channel/item/link') == f'https://canonical.example.org/post/{users["post"]}'

    sitemap = etree.fromstring(client.get('/sitemap.xml', base_url='http://127.0.0.1:5000').data)
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = [el.text for el in sitemap.findall('.//s:loc', namespaces=ns)]
    assert 'https://canonical.example.org/' in locs
    assert f'https://canonical.example.org/post/{users["post"]}' in locs

    robots = client.get('/robots.txt', base_url='http://127.0.0.1:5000').get_data(as_text=True)
    assert 'Sitemap: https://canonical.example.org/sitemap.xml' in robots


def test_non_indexable_and_404_pages_emit_noindex_without_canonical(client, users):
    for path in ('/search?q=test', '/login', '/reset_password_request'):
        resp = client.get(path)
        assert resp.status_code == 200
        doc = _parse_html(resp)
        assert _meta(doc, name='robots') == 'noindex, nofollow', path
        assert _canonical(doc) == [], path

    missing_post = client.get('/post/999999')
    assert missing_post.status_code == 404
    doc_404 = _parse_html(missing_post)
    assert _meta(doc_404, name='robots') == 'noindex, nofollow'
    assert _canonical(doc_404) == []
    title_text = ''.join(doc_404.xpath('//title/text()')).strip()
    assert ' - ' in title_text
    assert len(doc_404.xpath('//h1')) == 1

    login(client, 'admin')
    admin_doc = _parse_html(client.get('/admin/'))
    assert _meta(admin_doc, name='robots') == 'noindex, nofollow'
    assert _canonical(admin_doc) == []
    assert _meta(admin_doc, prop='og:title') is None


def test_article_lifecycle_pagination_dates_and_update_consistency(client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(db.select(Category))
        assert author is not None and category is not None
        draft = Post(
            title='未发布草稿', body='保密内容', author=author,
            category=category, is_published=False)
        db.session.add(draft)
        for idx in range(1, 13):
            db.session.add(Post(
                title=f'归档文章 #{idx:02d}',
                body=f'正文 {idx}',
                body_format='markdown',
                author=author,
                category=category,
                is_published=True,
                timestamp=datetime(2025, 1, idx, 12, 0, tzinfo=timezone.utc),
            ))
        db.session.commit()
        draft_id = draft.id

    # Draft is inaccessible publicly and excluded from sitemap/feed.
    assert client.get(f'/post/{draft_id}').status_code == 404
    assert f'/post/{draft_id}' not in client.get('/sitemap.xml').get_data(as_text=True)
    assert '未发布草稿' not in client.get('/feed.xml').get_data(as_text=True)

    # Pagination preserves newest-first ordering and canonicalizes page 2.
    page1 = _parse_html(client.get('/'))
    page2 = _parse_html(client.get('/?page=2'))
    assert len(page1.xpath('//article[contains(@class, "editorial-post")]')) == 10
    assert len(page2.xpath('//article[contains(@class, "editorial-post")]')) >= 3
    assert _canonical(page2) == ['http://localhost/?page=2']

    # Updating a published post keeps page metadata, updated_at, feed, and sitemap consistent.
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post is not None
        post.title = '更新后的标题 & 特殊符号'
        post.body = '更新后的正文内容'
        post.body_format = 'markdown'
        post.timestamp = datetime(2025, 2, 1, 2, 0, tzinfo=timezone.utc)
        post.updated_at = datetime(2025, 2, 5, 10, 30, tzinfo=timezone.utc)
        db.session.commit()

    detail_doc = _parse_html(client.get(f'/post/{users["post"]}'))
    assert '更新后的标题 & 特殊符号' in ''.join(detail_doc.xpath('//h1/text()'))
    times = detail_doc.xpath('//header[contains(@class, "article-header")]//time/@datetime')
    assert len(times) == 2
    assert times[0].startswith('2025-02-01T10:00:00+08:00')
    assert times[1].startswith('2025-02-05T18:30:00+08:00')

    sitemap = client.get('/sitemap.xml').get_data(as_text=True)
    assert '2025-02-05T10:30:00' in sitemap
    feed = client.get('/feed.xml').get_data(as_text=True)
    assert '更新后的标题 &amp; 特殊符号' in feed


def test_full_text_search_fts5_and_unicode_edge_cases(client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(db.select(Category))
        assert author is not None and category is not None
        db.session.add_all([
            Post(title='中文全文检索指南', body='介绍 SQLite FTS5 trigram 分词',
                 body_format='markdown', author=author, category=category,
                 is_published=True, timestamp=datetime(2025, 3, 1, tzinfo=timezone.utc)),
            Post(title='普通文章', body='这里在正文里提到了中文全文检索与 "引号" * 100%_test',
                 body_format='markdown', author=author, category=category,
                 is_published=True, timestamp=datetime(2025, 3, 2, tzinfo=timezone.utc)),
            Post(title='中文全文检索草稿', body='草稿不应出现在搜索中',
                 body_format='markdown', author=author, category=category,
                 is_published=False),
        ])
        db.session.commit()
        rebuilt = rebuild_search_index(db.session.connection())
        db.session.commit()
        connection = db.session.connection()
        if connection.dialect.name == 'sqlite':
            assert rebuilt is True
            assert search_index_available(connection) is True
        else:
            assert rebuilt is False
            assert search_index_available(connection) is False

    # Title match ranks before body-only match even when body match is newer; draft excluded.
    api = client.get('/api/search', query_string={'q': '中文全文检索'}).get_json()
    assert [item['title'] for item in api['results']] == ['中文全文检索指南', '普通文章']

    # Special FTS5 operator characters (quotes, wildcards, LIKE metacharacters) behave literally.
    special = client.get('/api/search', query_string={'q': '"引号" * 100%_test'}).get_json()
    assert [item['title'] for item in special['results']] == ['普通文章']

    # Empty query returns no posts; unmatched query returns clean empty state.
    assert client.get('/api/search', query_string={'q': '   '}).get_json() == {'results': []}
    no_hit = client.get('/search', query_string={'q': '绝对不存在的关键词xyz'}).get_data(as_text=True)
    assert 'class="editorial-post"' not in no_hit
    assert '未找到结果' in no_hit
