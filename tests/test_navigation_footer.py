from lxml import html as lxml_html

from tests.conftest import login


def page_for(client, path='/'):
    return lxml_html.fromstring(client.get(path).get_data(as_text=True))


def nav_labels(page):
    return [a.text_content().strip()
            for a in page.xpath('//ul[contains(@class, "site-nav__links")]//a')]


def test_signed_in_menu_has_no_admin_messages_or_profile_links(client, users):
    login(client, 'admin')
    page = page_for(client)
    labels = nav_labels(page)
    assert '管理' not in labels
    assert not any('站内信' in label for label in labels)
    assert '资料' not in labels
    assert not page.xpath('//*[@id="message_count"]')
    assert '首页' in labels and '归档' in labels


def test_admin_link_lives_in_the_footer_for_signed_in_users(client, users):
    login(client, 'admin')
    page = page_for(client)
    links = page.xpath('//footer//a[@href="/admin/"]')
    assert [a.text_content().strip() for a in links] == ['管理']
    assert page.xpath('//footer//form[@action="/logout"]')


def test_signed_out_footer_has_login_and_no_admin_link(client, users):
    page = page_for(client)
    assert not page.xpath('//footer//a[starts-with(@href, "/admin")]')
    assert page.xpath('//footer//a[@href="/login"]')


def test_moment_is_set_to_a_locale_that_exists_in_moment_js(client, users):
    # moment.js ships "zh-cn", not "zh"; an unknown code silently keeps English.
    body = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert 'moment.locale("zh-cn")' in body
    assert 'moment.locale("zh")' not in body


def test_primary_navigation_links_to_categories(client, users):
    page = page_for(client)
    assert '分类' in nav_labels(page)
    assert page.xpath('//ul[contains(@class, "site-nav__links")]//a[@href="/categories"]')


def tab_title(client, path):
    return page_for(client, path).xpath('//title')[0].text_content().strip()


def test_tab_titles_name_the_page(client, users):
    assert tab_title(client, '/') == "Aisaka's Blog"
    assert tab_title(client, f'/post/{users["post"]}') == "Test - Aisaka's Blog"
    assert tab_title(client, '/categories') == "分类 - Aisaka's Blog"
    assert tab_title(client, '/category/1') == "General - Aisaka's Blog"


def test_site_wording_defaults_and_admin_overrides(client, users):
    assert page_for(client).xpath('//a[@class="site-brand"]')[0].text_content() == "Aisaka's Blog"

    login(client, 'admin')
    form = client.get('/admin/settings')
    assert form.status_code == 200
    response = client.post('/admin/settings', data={
        'registration_open': 'y', 'post_revision_limit': '20',
        'site_name': '  Ai 的小站 ', 'home_tab_title': 'Ai 的小站 · 首页',
        'home_heading': '最新文章', 'nav_home_label': '主页',
        'nav_archive_label': '', 'nav_categories_label': '专题',
    })
    assert response.status_code == 302

    home = page_for(client)
    assert home.xpath('//a[@class="site-brand"]')[0].text_content() == 'Ai 的小站'
    assert home.xpath('//title')[0].text_content().strip() == 'Ai 的小站 · 首页'
    assert home.xpath('//h1')[0].text_content().strip() == '最新文章'
    assert nav_labels(home)[:3] == ['主页', '归档', '专题']
    assert tab_title(client, '/categories') == '专题 - Ai 的小站'
    assert tab_title(client, f'/post/{users["post"]}') == 'Test - Ai 的小站'

    client.post('/admin/settings', data={
        'registration_open': 'y', 'post_revision_limit': '20', 'site_name': '',
        'home_tab_title': '', 'home_heading': '', 'nav_home_label': '',
        'nav_archive_label': '', 'nav_categories_label': ''})
    assert tab_title(client, '/') == "Aisaka's Blog"
    assert nav_labels(page_for(client))[:3] == ['首页', '归档', '分类']


def test_home_page_lists_categories_with_published_posts(client, users):
    chips = page_for(client).xpath('//aside[contains(@class, "category-sidebar")]//a')
    assert [(a.get('href'), a.text_content().strip()) for a in chips] == [
        ('/category/1', 'General')]
