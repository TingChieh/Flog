from datetime import datetime, timezone
from lxml import etree, html

from app import db
from app.models import Page, Post, User


def test_feed_and_sitemap_only_expose_public_content(client, application):
    with application.app_context():
        author = User(username='writer', email='writer@example.com')
        db.session.add(author)
        db.session.flush()
        public = Post(title='A & <B> "quoted"', body='<p>Fish &amp; chips</p><script>alert(1)</script>', author=author, is_published=True, timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc))
        draft = Post(title='Secret draft', body='secret', author=author, is_published=False)
        deleted = Post(title='Deleted post', body='gone', author=author, is_published=True)
        db.session.add_all([public, draft, deleted, Page(title='About', slug='about-me', kind='content', is_published=True, updated_at=datetime(2024, 2, 3)), Page(title='Private page', slug='private-page', kind='content', is_published=False)])
        db.session.commit()
        public_id, draft_id, deleted_id = public.id, draft.id, deleted.id
        db.session.delete(deleted)
        db.session.commit()

    response = client.get('/feed.xml')
    assert response.status_code == 200
    assert response.mimetype == 'application/rss+xml'
    root = etree.fromstring(response.data)
    assert root.get('version') == '2.0'
    items = root.findall('./channel/item')
    assert len(items) == 1
    assert items[0].findtext('title') == 'A & <B> "quoted"'
    assert items[0].findtext('link') == f'http://localhost/post/{public_id}'
    assert items[0].findtext('pubDate')
    assert 'Fish &amp; chips' in items[0].findtext('description')
    assert '<script' not in items[0].findtext('description')
    assert b'A &amp; &lt;B&gt;' in response.data

    sitemap = etree.fromstring(client.get('/sitemap.xml').data)
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    entries = {entry.findtext('s:loc', namespaces=ns): entry.findtext('s:lastmod', namespaces=ns) for entry in sitemap.findall('s:url', namespaces=ns)}
    assert 'http://localhost/' in entries
    assert entries[f'http://localhost/post/{public_id}'].startswith('2024-01-02')
    assert entries['http://localhost/about-me'].startswith('2024-02-03')
    assert f'http://localhost/post/{draft_id}' not in entries
    assert f'http://localhost/post/{deleted_id}' not in entries
    assert 'http://localhost/private-page' not in entries
    assert not any('/admin' in url or '/login' in url for url in entries)


def test_feed_channel_links_to_homepage_and_identifies_itself(client):
    root = etree.fromstring(client.get('/feed.xml', base_url='https://example.com').data)
    assert root.findtext('./channel/link') == 'https://example.com/'
    atom_link = root.find('./channel/{http://www.w3.org/2005/Atom}link')
    assert atom_link is not None
    assert atom_link.get('rel') == 'self'
    assert atom_link.get('href') == 'https://example.com/feed.xml'


def test_feed_discovery_legacy_redirect_and_robots(client):
    redirect = client.get('/rss')
    assert redirect.status_code == 301
    assert redirect.headers['Location'].endswith('/feed.xml')
    document = html.fromstring(client.get('/').data)
    assert document.xpath('//link[@rel="alternate"][@type="application/rss+xml"][@href="/feed.xml"]')
    assert document.xpath('//footer//a[@href="/feed.xml"]')
    response = client.get('/robots.txt')
    assert response.status_code == 200
    assert 'Sitemap: http://localhost/sitemap.xml' in response.get_data(as_text=True)


def test_robots_disallows_admin_and_authentication_routes(client):
    response = client.get('/robots.txt', base_url='https://example.com')
    assert response.status_code == 200
    assert response.mimetype == 'text/plain'
    lines = response.get_data(as_text=True).splitlines()
    assert 'User-agent: *' in lines
    for path in ('/admin', '/login', '/logout', '/register',
                 '/reset_password_request', '/reset_password/'):
        assert f'Disallow: {path}' in lines
    assert 'Sitemap: https://example.com/sitemap.xml' in lines


def test_feed_orders_latest_first_and_subscription_is_translated(client, application):
    with application.app_context():
        author = User(username='chronicle', email='chronicle@example.com')
        db.session.add_all([
            Post(title='Older', body='old', author=author, is_published=True,
                 timestamp=datetime(2023, 1, 1)),
            Post(title='Newer', body='new', author=author, is_published=True,
                 timestamp=datetime(2024, 1, 1)),
        ])
        db.session.commit()
    root = etree.fromstring(client.get('/feed.xml').data)
    assert [item.findtext('title') for item in root.findall('./channel/item')] == ['Newer', 'Older']
    assert '订阅 RSS' in client.get('/').get_data(as_text=True)
