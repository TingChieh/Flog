from lxml import html as lxml_html

from app import db
from app.models import Category, Post
from tests.conftest import login


def add_admin_post(application, users, title='Admin own post'):
    with application.app_context():
        category = db.session.scalar(db.select(Category))
        db.session.add(Post(title=title, body='b', user_id=users['admin'],
                            category=category, is_published=True))
        db.session.commit()


def page(client, path):
    return lxml_html.fromstring(client.get(path).get_data(as_text=True))


def titles(document):
    return [t.strip() for t in document.xpath(
        '//div[contains(@class,"admin-list")]//strong/text()')]


def test_admin_defaults_to_all_posts_and_mine_shows_only_own(
        client, application, users):
    add_admin_post(application, users)
    login(client, 'admin')

    assert set(titles(page(client, '/admin/posts'))) == {
        'Test', 'Admin own post'}
    assert set(titles(page(client, '/admin/posts?scope=all'))) == {
        'Test', 'Admin own post'}
    assert titles(page(client, '/admin/posts?scope=mine')) == ['Admin own post']


def test_member_always_sees_only_their_own_posts(client, application, users):
    add_admin_post(application, users)
    login(client, 'author')
    for path in ('/admin/posts', '/admin/posts?scope=mine',
                 '/admin/posts?scope=all'):
        assert titles(page(client, path)) == ['Test'], path


def test_unknown_scope_is_rejected(client, users):
    login(client, 'admin')
    assert client.get('/admin/posts?scope=everyone').status_code == 400


def test_scope_sets_the_page_title(client, users):
    login(client, 'admin')
    assert page(client, '/admin/posts?scope=mine').xpath(
        'string(//h1)').strip() == '我的文章'
    assert page(client, '/admin/posts').xpath(
        'string(//h1)').strip() == '全部文章'


def test_admin_navigation_has_two_different_post_links_and_marks_one(
        client, users):
    login(client, 'admin')
    nav = '//nav[@aria-label="管理导航"]'

    mine = page(client, '/admin/posts?scope=mine')
    assert mine.xpath(f'{nav}//a[normalize-space()="我的文章"]/@href')[0] == \
        '/admin/posts?scope=mine'
    assert mine.xpath(f'{nav}//a[normalize-space()="全部文章"]/@href')[0] == \
        '/admin/posts?scope=all'
    assert {a.text_content().strip() for a in mine.xpath(
        f'{nav}//a[@aria-current="page"]')} == {'我的文章'}

    everyone = page(client, '/admin/posts')
    assert {a.text_content().strip() for a in everyone.xpath(
        f'{nav}//a[@aria-current="page"]')} == {'全部文章'}


def test_member_navigation_marks_my_posts(client, users):
    login(client, 'author')
    document = page(client, '/admin/posts')
    assert {a.text_content().strip() for a in document.xpath(
        '//nav[@aria-label="管理导航"]//a[@aria-current="page"]')} == {'我的文章'}


def test_dashboard_cards_link_to_their_own_scope(client, users):
    login(client, 'admin')
    document = page(client, '/admin/')
    hrefs = {a.xpath('string(.//*[contains(@class,"admin-metric__label")])').strip():
             a.get('href')
             for a in document.xpath('//a[contains(@class,"admin-metric")]')}
    assert hrefs['我的文章'] == '/admin/posts?scope=mine'
    assert hrefs['全部文章'] == '/admin/posts?scope=all'
