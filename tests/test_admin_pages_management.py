import pytest
from lxml import html as lxml_html

from app import db
from app.models import Page, PageRedirect
from tests.conftest import login


def add_page(application, slug='about', title='关于', **fields):
    values = dict(kind='content', body='hi', is_published=True)
    values.update(fields)
    with application.app_context():
        page = Page(title=title, slug=slug, **values)
        db.session.add(page)
        db.session.commit()
        return page.id


def test_admin_has_no_dedicated_about_entry(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    assert not page.xpath('//nav[@aria-label="管理导航"]//a[@href="/admin/about"]')
    assert client.get('/admin/about').status_code == 404


def test_new_page_form_ignores_query_prefill(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        '/admin/pages/new?title=关于&slug=about&show_in_nav=1'
    ).get_data(as_text=True))
    assert page.xpath('//input[@name="title"]/@value') in ([], [''])
    assert page.xpath('//input[@name="slug"]/@value') in ([], [''])
    assert not page.xpath('//input[@name="show_in_nav"][@checked]')


def test_about_is_an_ordinary_page_edited_like_any_other(
        client, application, users):
    page_id = add_page(application, summary='一句话介绍')
    login(client, 'admin')
    response = client.post(f'/admin/pages/{page_id}/edit', data={
        'title': '我是谁', 'slug': 'whoami', 'summary': '新的摘要',
        'body': '# hi', 'is_published': 'y', 'show_in_nav': 'y',
        'nav_order': '3',
    })
    assert response.status_code == 302
    with application.app_context():
        page = db.session.get(Page, page_id)
        assert (page.title, page.slug, page.summary) == (
            '我是谁', 'whoami', '新的摘要')
        # The old address keeps working through the generic redirect.
        assert db.session.query(PageRedirect).filter_by(
            slug='about', page_id=page_id).count() == 1
    old = client.get('/about')
    assert old.status_code == 301
    assert old.headers['Location'].endswith('/whoami')


def test_legacy_about_edit_route_is_gone(client, application, users):
    add_page(application)
    login(client, 'admin')
    assert client.get('/about/edit').status_code == 404
    assert client.post('/about/edit', data={'body': 'x'}).status_code == 404


def test_about_page_has_no_special_label_or_class(client, application):
    add_page(application, summary='摘要')
    html = client.get('/about').get_data(as_text=True)
    assert 'about-page' not in html
    assert 'public-label' not in html
    assert 'public-page' in html
    assert '摘要' in html


def test_about_page_is_unpublished_when_unpublished(client, application):
    add_page(application, is_published=False)
    assert client.get('/about').status_code == 404


def test_page_list_search_matches_title_and_slug(client, application, users):
    add_page(application, slug='alpha', title='第一页')
    add_page(application, slug='beta-notes', title='笔记')
    login(client, 'admin')

    by_title = client.get('/admin/pages?q=笔').get_data(as_text=True)
    assert '笔记' in by_title and '第一页' not in by_title

    by_slug = client.get('/admin/pages?q=ALPHA').get_data(as_text=True)
    assert '第一页' in by_slug and '笔记' not in by_slug


def test_page_list_filters_and_keeps_search(client, application, users):
    add_page(application, slug='live', title='已上线', is_published=True)
    add_page(application, slug='wip', title='草稿页', is_published=False)
    login(client, 'admin')

    published = client.get('/admin/pages?filter=published').get_data(as_text=True)
    assert '已上线' in published and '草稿页' not in published
    unpublished = client.get('/admin/pages?filter=unpublished').get_data(as_text=True)
    assert '草稿页' in unpublished and '已上线' not in unpublished
    assert client.get('/admin/pages?filter=content').status_code == 400
    assert client.get('/admin/pages?filter=bogus').status_code == 400

    page = lxml_html.fromstring(
        client.get('/admin/pages?q=live').get_data(as_text=True))
    hrefs = page.xpath('//nav[@aria-label="页面筛选"]//a/@href')
    assert hrefs and all('q=live' in href for href in hrefs)
    assert not page.xpath('//nav[@aria-label="页面筛选"]//a[contains(., "内容页")]')


def test_page_list_shows_last_updated(client, application, users):
    from datetime import datetime
    add_page(application, updated_at=datetime(2024, 5, 6, 7, 8))
    login(client, 'admin')
    assert '2024-05-06' in client.get('/admin/pages').get_data(as_text=True)


def test_toggle_publication_flips_state_and_keeps_query(
        client, application, users):
    page_id = add_page(application, is_published=True)
    login(client, 'admin')

    response = client.post(
        f'/admin/pages/{page_id}/publish?q=abc&filter=published')
    assert response.status_code == 302
    assert response.headers['Location'].endswith(
        '/admin/pages?q=abc&filter=published')
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is False

    client.post(f'/admin/pages/{page_id}/publish')
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is True


def test_toggle_navigation_flips_state(client, application, users):
    page_id = add_page(application, show_in_nav=False)
    login(client, 'admin')
    assert client.post(f'/admin/pages/{page_id}/nav').status_code == 302
    with application.app_context():
        assert db.session.get(Page, page_id).show_in_nav is True
    client.post(f'/admin/pages/{page_id}/nav')
    with application.app_context():
        assert db.session.get(Page, page_id).show_in_nav is False


@pytest.mark.parametrize('suffix', ['publish', 'nav'])
def test_toggles_require_admin_and_post(client, application, users, suffix):
    page_id = add_page(application)
    url = f'/admin/pages/{page_id}/{suffix}'
    assert client.post(url).status_code == 302          # anonymous → login
    login(client, 'author')
    assert client.post(url).status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get(url).status_code == 405
    assert client.post('/admin/pages/9999/' + suffix).status_code == 404


def test_toggles_reject_missing_csrf(client, application, users):
    page_id = add_page(application, is_published=True)
    login(client, 'admin')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post(f'/admin/pages/{page_id}/publish')
        assert response.status_code == 400
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is True


def nav_slugs(application):
    with application.app_context():
        return [page.slug for page in db.session.scalars(
            db.select(Page).order_by(Page.nav_order, Page.title, Page.id))]


def test_move_page_swaps_neighbours_even_when_orders_tie(
        client, application, users):
    # Every page starts at nav_order 0, so the shown order is by title.
    ids = {slug: add_page(application, slug=slug, title=slug)
           for slug in ('a', 'b', 'c')}
    login(client, 'admin')
    response = client.post(f'/admin/pages/{ids["c"]}/move',
                           data={'direction': 'up'})
    assert response.status_code == 302
    assert nav_slugs(application) == ['a', 'c', 'b']
    client.post(f'/admin/pages/{ids["c"]}/move', data={'direction': 'up'})
    assert nav_slugs(application) == ['c', 'a', 'b']
    client.post(f'/admin/pages/{ids["c"]}/move', data={'direction': 'down'})
    assert nav_slugs(application) == ['a', 'c', 'b']


def test_move_page_at_the_end_changes_nothing(client, application, users):
    ids = {slug: add_page(application, slug=slug, title=slug)
           for slug in ('a', 'b')}
    login(client, 'admin')
    assert client.post(f'/admin/pages/{ids["a"]}/move',
                       data={'direction': 'up'}).status_code == 302
    assert nav_slugs(application) == ['a', 'b']


def test_move_page_rejects_bad_direction_and_non_admin(
        client, application, users):
    page_id = add_page(application)
    assert client.post(f'/admin/pages/{page_id}/move',
                       data={'direction': 'up'}).status_code in (302, 401, 403)
    login(client, 'admin')
    assert client.post(f'/admin/pages/{page_id}/move',
                       data={'direction': 'sideways'}).status_code == 400
    assert client.get(f'/admin/pages/{page_id}/move').status_code == 405


def test_page_list_offers_move_buttons_only_on_the_full_list(
        client, application, users):
    add_page(application, slug='a', title='a')
    add_page(application, slug='b', title='b')
    login(client, 'admin')
    full = lxml_html.fromstring(client.get('/admin/pages').get_data(as_text=True))
    assert len(full.xpath('//button[@name="direction"]')) == 6
    assert len(full.xpath('//button[@name="direction"][@disabled]')) == 2
    filtered = lxml_html.fromstring(client.get(
        '/admin/pages?filter=published').get_data(as_text=True))
    assert not filtered.xpath('//button[@name="direction"]')


def test_podcast_row_in_page_management_filters_and_toggles(
        client, application, users):
    from app.models import get_podcast_show

    add_page(application, slug='about', title='关于')
    login(client, 'admin')

    with application.app_context():
        initial = get_podcast_show()
        db.session.flush()
        assert initial.enabled is False
        assert initial.show_in_nav is True

    all_html = client.get('/admin/pages').get_data(as_text=True)
    assert '播客' in all_html
    assert '未开启' in all_html
    assert '/podcast/' in all_html

    unpublished_html = client.get(
        '/admin/pages?filter=unpublished').get_data(as_text=True)
    assert '/podcast/' in unpublished_html

    published_html = client.get(
        '/admin/pages?filter=published').get_data(as_text=True)
    assert '/podcast/' not in published_html

    search_html = client.get('/admin/pages?q=podcast').get_data(as_text=True)
    assert '/podcast/' in search_html

    resp = client.post('/admin/pages/podcast/publish?filter=unpublished',
                       follow_redirects=False)
    assert resp.status_code == 302
    assert 'filter=unpublished' in resp.headers['Location']

    resp = client.post('/admin/pages/podcast/nav?q=podcast',
                       follow_redirects=False)
    assert resp.status_code == 302
    assert 'q=podcast' in resp.headers['Location']

    with application.app_context():
        show = get_podcast_show()
        assert show.enabled is True
        assert show.show_in_nav is False

    published_after = client.get(
        '/admin/pages?filter=published').get_data(as_text=True)
    assert '/podcast/' in published_after
    assert '导航隐藏' in published_after

    resp = client.post('/admin/pages/podcast/publish')
    assert resp.status_code == 302
    resp = client.post('/admin/pages/podcast/nav')
    assert resp.status_code == 302
    with application.app_context():
        show = get_podcast_show()
        assert show.enabled is False
        assert show.show_in_nav is True


def test_podcast_actions_require_admin_and_post(client, application, users):
    for endpoint in ('publish', 'nav', 'move'):
        resp = client.post(
            f'/admin/pages/podcast/{endpoint}',
            data={'direction': 'up'} if endpoint == 'move' else {},
        )
        assert resp.status_code in (302, 401, 403)

    login(client, 'other')
    for endpoint in ('publish', 'nav', 'move'):
        resp = client.post(
            f'/admin/pages/podcast/{endpoint}',
            data={'direction': 'up'} if endpoint == 'move' else {},
        )
        assert resp.status_code == 403

    client.post('/logout')
    login(client, 'admin')
    for endpoint in ('publish', 'nav', 'move'):
        assert client.get(
            f'/admin/pages/podcast/{endpoint}'
        ).status_code == 405

    assert client.post(
        '/admin/pages/podcast/move', data={'direction': 'sideways'}
    ).status_code == 400


def test_move_podcast_reorders_admin_pages_and_public_nav(
        client, application, users):
    from app.models import get_podcast_show

    add_page(application, slug='about', title='关于')
    add_page(application, slug='links', title='友链')
    with application.app_context():
        for idx, slug in enumerate(('about', 'links')):
            page = db.session.scalar(db.select(Page).filter_by(slug=slug))
            page.is_published = True
            page.show_in_nav = True
            page.nav_order = idx
        show = get_podcast_show()
        show.enabled = True
        show.show_in_nav = True
        db.session.commit()

    def public_nav_hrefs():
        doc = lxml_html.fromstring(client.get('/').get_data(as_text=True))
        hrefs = doc.xpath('//ul[contains(@class, "site-nav__links")]//a/@href')
        return [h for h in hrefs if h in ('/about', '/links', '/podcast/')]

    def admin_row_titles():
        doc = lxml_html.fromstring(
            client.get('/admin/pages').get_data(as_text=True))
        return [
            ' '.join(el.text_content().split())
            for el in doc.xpath(
                '//div[contains(@class, "admin-list__main")]//strong'
            )
        ]

    login(client, 'admin')
    assert admin_row_titles() == ['关于', '友链', '播客']
    assert public_nav_hrefs() == ['/about', '/links', '/podcast/']

    resp = client.post('/admin/pages/podcast/move', data={'direction': 'up'})
    assert resp.status_code == 302
    assert admin_row_titles() == ['关于', '播客', '友链']
    assert public_nav_hrefs() == ['/about', '/podcast/', '/links']

    client.post('/admin/pages/podcast/move', data={'direction': 'up'})
    assert admin_row_titles() == ['播客', '关于', '友链']
    assert public_nav_hrefs() == ['/podcast/', '/about', '/links']

    client.post('/admin/pages/podcast/move', data={'direction': 'down'})
    assert admin_row_titles() == ['关于', '播客', '友链']
    assert public_nav_hrefs() == ['/about', '/podcast/', '/links']


def test_admin_pages_ui_cleanup_matches_editorial_audit(
        client, application, users):
    add_page(application, slug='about', title='About')
    login(client, 'admin')

    dash_html = client.get('/admin/').get_data(as_text=True)
    assert 'admin-workspace__eyebrow' not in dash_html

    pages_html = client.get('/admin/pages').get_data(as_text=True)
    assert 'admin-workspace__eyebrow' not in pages_html
    assert '按标题或路径搜索' in pages_html
    assert 'slug' not in pages_html.lower()
    assert '·' not in pages_html

    doc = lxml_html.fromstring(pages_html)
    assert doc.xpath('//button[contains(@class, "admin-search__submit")]')
    assert doc.xpath('//button[contains(@class, "admin-order-btn")]')
    status_texts = [
        el.text_content().strip()
        for el in doc.xpath('//*[contains(@class, "admin-status")]')
    ]
    assert status_texts == ['已发布', '未开启']
    state_texts = [
        el.text_content().strip()
        for el in doc.xpath('//*[contains(@class, "admin-list__state")]')
    ]
    assert all('100' not in text for text in state_texts)

