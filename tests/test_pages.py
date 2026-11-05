from xml.etree import ElementTree

import pytest
import sqlalchemy as sa

from app import db
from app.models import Page, PageRedirect, Post
from app.pages import (
    PageValidationError,
    delete_content_page,
    normalize_slug,
    page_for_public_slug,
    save_page,
    visible_navigation_pages,
)
from tests.conftest import login


@pytest.mark.parametrize(('raw', 'expected'), [
    (' My About ', 'my-about'),
    ('Movie_Notes', 'movie-notes'),
    ('hello---world', 'hello-world'),
])
def test_slug_normalization(raw, expected):
    assert normalize_slug(raw) == expected


def test_removed_following_route_releases_page_slug():
    assert normalize_slug('following') == 'following'


@pytest.mark.parametrize('slug', [
    'admin', 'login', 'logout', 'register', 'post', 'user', 'static',
    'files', 'upload', 'rss',
])
def test_reserved_slugs_are_rejected(slug):
    with pytest.raises(PageValidationError, match='reserved'):
        normalize_slug(slug)


@pytest.mark.parametrize('slug', ['', '---', '中文'])
def test_slug_without_ascii_letters_or_numbers_is_rejected(slug):
    with pytest.raises(PageValidationError, match='letters or numbers'):
        normalize_slug(slug)


def add_content_page(slug='first-slug', title='First', **values):
    page = Page(kind='content')
    save_page(page, {
        'title': title,
        'slug': slug,
        'summary': values.get('summary', ''),
        'body': values.get('body', '<p>Body</p>'),
        'is_published': values.get('is_published', True),
        'show_in_nav': values.get('show_in_nav', True),
        'nav_order': values.get('nav_order', 10),
    })
    return page


MODULE_CASES = (
    pytest.param('todo', 'todo', 'tasks-cms', id='todo'),
    pytest.param('movie', 'movie', 'films-cms', id='movie'),
    pytest.param('links', 'links', 'bookmarks-cms', id='links'),
    pytest.param('guestbook', 'comment', 'guestbook-cms', id='guestbook'),
)


def test_slug_change_creates_flat_redirect(application):
    with application.app_context():
        page = add_content_page()
        db.session.commit()

        save_page(page, {'slug': 'second-slug', 'title': page.title})
        save_page(page, {'slug': 'third-slug', 'title': page.title})
        db.session.commit()

        redirects = db.session.scalars(db.select(PageRedirect).where(
            PageRedirect.page_id == page.id)).all()
        assert {item.slug for item in redirects} == {
            'first-slug', 'second-slug'}
        assert {item.page_id for item in redirects} == {page.id}


def test_slug_conflicts_with_current_and_historical_slugs(application):
    with application.app_context():
        first = add_content_page('first')
        second = add_content_page('second')
        db.session.commit()
        save_page(first, {'slug': 'renamed', 'title': first.title})
        db.session.commit()

        with pytest.raises(PageValidationError, match='already in use'):
            save_page(second, {'slug': 'renamed', 'title': second.title})
        with pytest.raises(PageValidationError, match='already in use'):
            save_page(second, {'slug': 'first', 'title': second.title})


def test_deleting_content_page_cleans_redirects(application):
    with application.app_context():
        page = add_content_page('old-address')
        db.session.commit()
        page_id = page.id
        save_page(page, {'title': page.title, 'slug': 'new-address'})
        db.session.commit()

        delete_content_page(page)
        db.session.commit()

        assert db.session.get(Page, page_id) is None
        assert db.session.scalar(db.select(PageRedirect)) is None


def test_public_lookup_hides_unpublished_pages_and_resolves_redirects(
        application):
    with application.app_context():
        published = add_content_page('published')
        draft = add_content_page('draft', is_published=False)
        db.session.commit()
        save_page(published, {'title': published.title, 'slug': 'canonical'})
        db.session.commit()

        assert page_for_public_slug('draft') is None
        assert page_for_public_slug('canonical') == (published, False)
        assert page_for_public_slug('published') == (published, True)


def test_navigation_contains_only_visible_published_pages_in_stable_order(
        application):
    with application.app_context():
        later = add_content_page('later', title='Later', nav_order=20)
        early_z = add_content_page('early-z', title='Zulu', nav_order=10)
        early_a = add_content_page('early-a', title='Alpha', nav_order=10)
        add_content_page('hidden', show_in_nav=False)
        add_content_page('draft-nav', is_published=False)
        db.session.commit()

        assert visible_navigation_pages() == [early_a, early_z, later]


def test_only_admin_can_open_page_management(client, users):
    login(client, 'author')
    assert client.get('/admin/pages').status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get('/admin/pages').status_code == 200


def test_admin_can_create_markdown_content_page(client, application, users):
    login(client, 'admin')

    response = client.post('/admin/pages/new', data={
        'title': 'Now',
        'slug': 'now',
        'summary': 'Short',
        'body': '# Stored as source',
        'is_published': 'y',
        'show_in_nav': 'y',
        'nav_order': '30',
    })

    assert response.status_code == 302
    with application.app_context():
        page = db.session.scalar(db.select(Page).where(Page.slug == 'now'))
        assert page.title == 'Now'
        assert page.body == '# Stored as source'
        assert page.body_format == 'markdown'
        assert page.is_published is True
        assert page.show_in_nav is True
        assert page.nav_order == 30


@pytest.mark.parametrize(('slug', 'message'), [
    ('admin', 'reserved'),
    ('---', 'letters or numbers'),
])
def test_page_form_displays_slug_errors(client, users, slug, message):
    login(client, 'admin')

    response = client.post('/admin/pages/new', data={
        'title': 'Invalid page',
        'slug': slug,
        'body': '<p>Body</p>',
        'nav_order': '0',
    })

    assert response.status_code == 200
    assert message.encode() in response.data


def test_admin_editing_slug_creates_old_address(client, application, users):
    with application.app_context():
        page = add_content_page('before-edit')
        db.session.commit()
        page_id = page.id
    login(client, 'admin')

    response = client.post(f'/admin/pages/{page_id}/edit', data={
        'title': 'Edited',
        'slug': 'after-edit',
        'body': '<p>Edited</p>',
        'nav_order': '5',
    })

    assert response.status_code == 302
    with application.app_context():
        redirect = db.session.scalar(db.select(PageRedirect).where(
            PageRedirect.slug == 'before-edit'))
        assert redirect.page_id == page_id


def test_admin_page_edit_preserves_legacy_format_and_sanitizes_html(
        client, application, users):
    with application.app_context():
        page = Page(title='Legacy page', slug='legacy-page',
                    kind='content', body='<p>Legacy</p>',
                    body_format='html', is_published=True,
                    show_in_nav=False, nav_order=0)
        db.session.add(page)
        db.session.commit()
        page_id = page.id

    login(client, 'admin')
    response = client.post(f'/admin/pages/{page_id}/edit', data={
        'title': 'Legacy page',
        'slug': 'legacy-page',
        'body': '<p>Updated</p><script>alert(1)</script>',
        'nav_order': '0',
    })

    assert response.status_code == 302
    with application.app_context():
        page = db.session.get(Page, page_id)
        assert page.body == '<p>Updated</p>alert(1)'
        assert page.body_format == 'html'


def test_admin_can_delete_content_page(client, application, users):
    with application.app_context():
        page = add_content_page('delete-me')
        db.session.commit()
        page_id = page.id
    login(client, 'admin')

    response = client.post(f'/admin/pages/{page_id}/delete', data={
        'confirm': 'y',
    })

    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(Page, page_id) is None


def test_unpublished_page_preview_requires_admin(
        client, application, users):
    with application.app_context():
        page = add_content_page('preview-me', is_published=False)
        db.session.commit()
        page_id = page.id

    login(client, 'author')
    assert client.get(f'/admin/pages/{page_id}/preview').status_code == 403
    client.post('/logout')
    login(client, 'admin')
    response = client.get(f'/admin/pages/{page_id}/preview')
    assert response.status_code == 200
    assert b'<p>Body</p>' in response.data


def test_markdown_content_page_preview_renders_without_source_marker(
        client, application, users):
    with application.app_context():
        page = add_content_page(
            'markdown-preview', body='# Preview Heading',
            is_published=False)
        page.body_format = 'markdown'
        db.session.commit()
        page_id = page.id

    login(client, 'admin')
    response = client.get(f'/admin/pages/{page_id}/preview')

    assert response.status_code == 200
    assert b'<h1>Preview Heading</h1>' in response.data
    assert b'# Preview Heading' not in response.data


def test_published_content_page_renders_at_slug(client, application):
    with application.app_context():
        add_content_page('notes', title='Notes', body='<p>Published body</p>')
        db.session.commit()

    response = client.get('/notes')

    assert response.status_code == 200
    assert b'<p>Published body</p>' in response.data


def test_markdown_post_and_page_render_without_source_markers(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '# Heading'
        post.body_format = 'markdown'
        page = add_content_page('markdown-notes', body='# Heading')
        page.body_format = 'markdown'
        db.session.commit()

        post_id = post.id

    post_response = client.get(f'/post/{post_id}')
    page_response = client.get('/markdown-notes')

    assert b'<h1>Heading</h1>' in post_response.data
    assert b'# Heading' not in post_response.data
    assert b'<h1>Heading</h1>' in page_response.data
    assert b'# Heading' not in page_response.data


def test_rss_renders_markdown_post_description_without_source_marker(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '# RSS Heading'
        post.body_format = 'markdown'
        db.session.commit()

    response = client.get('/rss', follow_redirects=True)
    description = ElementTree.fromstring(response.data).findtext(
        './channel/item/description')

    assert response.status_code == 200
    assert '<h1>RSS Heading</h1>' in description
    assert '# RSS Heading' not in description


def test_unpublished_page_is_publicly_not_found(client, application):
    with application.app_context():
        add_content_page('draft-page', is_published=False)
        db.session.commit()

    assert client.get('/draft-page').status_code == 404


def test_old_slug_redirects_directly_to_current_slug(client, application):
    with application.app_context():
        page = add_content_page('first-public')
        db.session.commit()
        save_page(page, {'slug': 'second-public', 'title': page.title})
        save_page(page, {'slug': 'third-public', 'title': page.title})
        db.session.commit()

    response = client.get('/first-public')

    assert response.status_code == 301
    assert response.headers['Location'].endswith('/third-public')


def test_historical_page_redirect_preserves_raw_query_string(
        client, application):
    with application.app_context():
        page = add_content_page('first-public')
        db.session.commit()
        save_page(page, {'slug': 'current-public', 'title': page.title})
        db.session.commit()

    response = client.get(
        '/first-public?filter=first&filter=second&slug=legacy-address')

    assert response.status_code == 301
    assert response.headers['Location'].endswith(
        '/current-public?filter=first&filter=second&slug=legacy-address')


def test_navigation_contains_visible_pages_in_order(client, application):
    with application.app_context():
        add_content_page('later-public', title='Later page', nav_order=20)
        add_content_page('early-public', title='Early page', nav_order=10)
        add_content_page('hidden-public', title='Hidden page',
                         show_in_nav=False)
        add_content_page('draft-public', title='Draft page',
                         is_published=False)
        db.session.commit()

    html = client.get('/').get_data(as_text=True)

    assert html.index('Early page') < html.index('Later page')
    assert 'Hidden page' not in html
    assert 'Draft page' not in html


def test_about_fixed_address_uses_redirect_and_publication_state(
        client, application):
    with application.app_context():
        page = add_content_page('about', title='About CMS')
        db.session.commit()
        save_page(page, {'slug': 'project', 'title': page.title})
        db.session.commit()

    response = client.get('/about')
    assert response.status_code == 301
    assert response.headers['Location'].endswith('/project')

    # End the request's transaction before a separate context updates the page.
    db.session.remove()

    with application.app_context():
        page = db.session.scalar(db.select(Page).where(Page.slug == 'project'))
        save_page(page, {
            'slug': page.slug, 'title': page.title, 'is_published': False,
        })
        db.session.commit()

    assert client.get('/about').status_code == 404
