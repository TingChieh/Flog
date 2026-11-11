from lxml import html
import pytest

from app import db
from app.models import Post


def test_home_lists_category_excerpt_and_date_without_reading_time(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '<p>' + '汉' * 401 + '</p>'
        db.session.commit()
    page = html.fromstring(client.get('/').data)
    item = page.xpath('//article[contains(@class, "editorial-post")]')[0]
    assert 'General' in item.text_content()
    assert '阅读需' not in item.text_content()
    assert item.xpath('.//time[@datetime]')
    assert not item.xpath('.//button')
    assert not page.xpath('//aside[contains(@class, "category-rail")]')
    assert not page.xpath('//header[contains(@class, "hero--home")]')
    # The list shows two lines of it, so the page does not carry the rest.
    excerpt = item.xpath('.//a[contains(@class, "editorial-post__link")]/p')[0].text_content()
    assert excerpt.startswith('汉' * 100) and excerpt.endswith('…') and len(excerpt) < 300


def test_sharing_controls_are_on_article_not_list(client, users):
    listing = html.fromstring(client.get('/').data)
    detail = html.fromstring(client.get(f'/post/{users["post"]}').data)
    assert not listing.xpath('//article[contains(@class,"editorial-post")]//button')
    assert not detail.xpath('//*[@data-qr-share]')
    assert not detail.xpath('//button[contains(@onclick,"copyToClipboard")]')


def test_navigation_search_and_theme_are_inside_collapsible_menu(client):
    page = html.fromstring(client.get('/').data)
    menu = page.get_element_by_id('site-navigation')
    toggle = page.xpath('//button[@data-nav-toggle]')[0]
    assert toggle.get('aria-controls') == 'site-navigation'
    assert toggle.get('aria-expanded') == 'false'
    assert menu.xpath('.//*[@data-search-open]')
    assert menu.xpath('.//*[@data-theme-toggle]')


def test_chinese_menu_is_translated(client, users):
    page = html.fromstring(client.get(
        f'/post/{users["post"]}', headers={'Accept-Language': 'zh'}).data)
    assert page.xpath('//button[@data-nav-toggle]')[0].text_content().strip() == '切换导航'
    assert '复制链接' not in page.text_content()


def test_list_excerpt_skips_the_title_the_post_opens_with(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.title = '学之悟道'
        post.body = '<p>2023.04.21 学之悟道 昨日看了一场直播。</p>'
        db.session.commit()
    item = html.fromstring(client.get('/').data).xpath('//article[contains(@class, "editorial-post")]')[0]
    assert item.xpath('.//a[contains(@class, "editorial-post__link")]/p')[0].text_content() == '昨日看了一场直播。'
    # The category reads in the meta line next to the date.
    meta = item.xpath('.//div[contains(@class, "editorial-post__meta")]')[0]
    assert meta.xpath('.//a[@href="/category/1"]') and meta.xpath('.//time')


def test_a_single_page_of_posts_has_no_pagination(client, users):
    page = html.fromstring(client.get('/').data)
    assert not page.xpath('//ul[contains(@class, "pagination")]')
    assert not page.xpath('//a[@href="None"]')


def test_pages_describe_themselves_for_search_engines(client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).body = '<p>Fish and chips by the sea.</p>'
        db.session.commit()
    home = html.fromstring(client.get('/').data)
    assert home.xpath('//meta[@name="description"]/@content')[0].strip()
    post = html.fromstring(client.get(f'/post/{users["post"]}').data)
    assert post.xpath('//meta[@name="description"]/@content') == ['Fish and chips by the sea.']
