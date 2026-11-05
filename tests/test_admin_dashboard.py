from lxml import html as lxml_html

from app import db
from app.models import Page, PostComment
from tests.conftest import login


def cards(client):
    page = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    result = {}
    for card in page.xpath('//a[contains(@class,"admin-metric")]'):
        label = card.xpath('string(.//*[contains(@class,"admin-metric__label")])')
        value = card.xpath('string(.//*[contains(@class,"admin-metric__value")])')
        result[label.strip()] = (card.get('href'), value.strip())
    return result


def test_member_sees_only_own_posts_card(client, users):
    login(client, 'author')
    assert cards(client) == {'我的文章': ('/admin/posts?scope=mine', '1')}


def test_admin_sees_linked_metric_cards(client, application, users):
    with application.app_context():
        db.session.add_all([
            Page(title='A', slug='a', kind='content', is_published=True),
            Page(title='B', slug='b', kind='content', is_published=False),
            PostComment(post_id=users['post'], name='n', email='e@e.co',
                        body='b')])
        db.session.commit()
    login(client, 'admin')
    assert cards(client) == {
        '我的文章': ('/admin/posts?scope=mine', '0'),
        '全部文章': ('/admin/posts?scope=all', '1'),
        '页面': ('/admin/pages', '1 / 2'),
        '评论': ('/admin/comments', '1'),
        '用户': ('/admin/users', '3'),
    }
