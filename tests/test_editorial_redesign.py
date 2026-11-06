from lxml import html
import pytest

from app import db
from app.models import Post


@pytest.mark.parametrize(('body', 'body_format', 'minutes'), [
    ('汉' * 400, 'html', 1),
    ('汉' * 401, 'html', 2),
    ('word ' * 200, 'html', 1),
    ('汉' * 200 + ' ' + 'word ' * 100, 'html', 1),
    ('<p>' + '汉' * 400 + '</p>', 'html', 1),
    ('# Heading\n\n' + '汉' * 400, 'markdown', 2),
    ('', 'html', 1),
])
def test_reading_time_counts_visible_cjk_and_latin_content(application, body, body_format, minutes):
    from app.content import reading_minutes
    with application.app_context():
        assert reading_minutes(body, body_format) == minutes


@pytest.mark.parametrize(('locale', 'label'), [('en', '阅读需 2 分钟'), ('zh', '阅读需 2 分钟')])
def test_home_lists_category_excerpt_date_and_chinese_reading_time(client, application, users, locale, label):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '<p>' + '汉' * 401 + '</p>'
        db.session.commit()
    page = html.fromstring(client.get('/', headers={'Accept-Language': locale}).data)
    item = page.xpath('//article[contains(@class, "editorial-post")]')[0]
    assert 'General' in item.text_content()
    assert label in item.text_content()
    assert item.xpath('.//time[@datetime]')
    assert not item.xpath('.//button')
    assert not page.xpath('//aside[contains(@class, "category-rail")]')
    assert not page.xpath('//header[contains(@class, "hero--home")]')


def test_sharing_controls_are_on_article_not_list(client, users):
    listing = html.fromstring(client.get('/').data)
    detail = html.fromstring(client.get(f'/post/{users["post"]}').data)
    assert not listing.xpath('//article[contains(@class,"editorial-post")]//button')
    assert detail.xpath('//div[@data-qr-share]//button[contains(@class,"qr-share__toggle")]')
    assert not detail.xpath('//button[contains(@onclick,"copyToClipboard")]')


def test_navigation_search_and_theme_are_inside_collapsible_menu(client):
    page = html.fromstring(client.get('/').data)
    menu = page.get_element_by_id('site-navigation')
    toggle = page.xpath('//button[@data-nav-toggle]')[0]
    assert toggle.get('aria-controls') == 'site-navigation'
    assert toggle.get('aria-expanded') == 'false'
    assert menu.xpath('.//*[@data-search-open]')
    assert menu.xpath('.//*[@data-theme-toggle]')


def test_chinese_menu_and_sharing_controls_are_translated(client, users):
    page = html.fromstring(client.get(
        f'/post/{users["post"]}', headers={'Accept-Language': 'zh'}).data)
    assert page.xpath('//button[@data-nav-toggle]')[0].text_content().strip() == '切换导航'
    assert page.xpath('//button[contains(@class, "qr-share__toggle")]')[0].text_content().strip() == '生成二维码'
    assert page.xpath('//*[@data-qr-share]//*[@role="dialog"]')[0].get('aria-label') == '文章二维码'
    assert page.xpath('//p[contains(@class, "qr-share__hint")]')[0].text_content().strip() == '扫码，在手机上阅读'
    assert '复制链接' not in page.text_content()
