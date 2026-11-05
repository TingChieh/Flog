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
