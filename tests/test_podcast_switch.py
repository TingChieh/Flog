from pathlib import Path

from lxml import html as lxml_html

from app import db
from app.models import Episode, PodcastShow
from tests.conftest import login
from tests.podcast_helpers import add_episode


def uploads(application):
    return Path(application.config['UPLOAD_FOLDER'])


def show(application):
    with application.app_context():
        return db.session.get(PodcastShow, 1)


def menu_has_podcast(client):
    tree = lxml_html.fromstring(client.get('/index').get_data(as_text=True))
    return bool(tree.xpath('//ul[@class="site-nav__links"]//a[@href="/podcast/"]'))


def admin_page(client):
    return lxml_html.fromstring(client.get('/admin/podcast').get_data(as_text=True))


def test_the_podcast_is_off_until_it_is_switched_on(client, application, users):
    with application.app_context():
        add_episode(uploads(application), 1)

    for path in ('/podcast/', '/podcast/1', '/podcast/feed.xml'):
        assert client.get(path).status_code == 404, path
    assert not menu_has_podcast(client)
    assert 'podcast' not in client.get('/sitemap.xml').get_data(as_text=True)


def test_the_podcast_admin_is_in_the_site_management_menu(client, users):
    login(client, 'admin')
    tree = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))

    groups = tree.xpath('//nav[@class="admin-nav"]')[0]
    labels = [a.text_content().strip() for a in groups.xpath('.//a')]
    assert '播客' in labels
    assert labels.index('播客') > labels.index('全部文章')


def test_the_switch_is_inside_the_podcast_admin(client, users):
    login(client, 'admin')

    tree = admin_page(client)

    assert '播客已关闭' in tree.text_content()
    assert tree.xpath('//form[contains(@action, "/admin/podcast/enable")]//button')[0]\
        .text_content().strip() == '开启播客'
    assert not tree.xpath('//form[contains(@action, "/admin/podcast/nav")]')


def test_switching_it_on_opens_the_pages_and_adds_the_menu_link(client, application, users):
    with application.app_context():
        add_episode(uploads(application), 1)
    login(client, 'admin')

    response = client.post('/admin/podcast/enable', follow_redirects=True)

    assert '播客已开启' in response.get_data(as_text=True)
    assert show(application).enabled
    assert client.get('/podcast/').status_code == 200
    assert client.get('/podcast/1').status_code == 200
    assert client.get('/podcast/feed.xml').status_code == 200
    assert menu_has_podcast(client)
    assert 'http://localhost/podcast/1<' in client.get('/sitemap.xml').get_data(as_text=True)
    tree = admin_page(client)
    assert tree.xpath('//form[contains(@action, "/admin/podcast/enable")]//button')[0]\
        .text_content().strip() == '关闭播客'


def test_switching_it_off_again_keeps_episodes_and_audio(client, application, users):
    with application.app_context():
        add_episode(uploads(application), 1)
    login(client, 'admin')
    client.post('/admin/podcast/enable')

    response = client.post('/admin/podcast/enable', follow_redirects=True)

    assert '播客已关闭' in response.get_data(as_text=True)
    assert client.get('/podcast/').status_code == 404
    assert not menu_has_podcast(client)
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        assert (uploads(application) / 'audio' / episode.audio_filename).is_file()


def test_the_menu_link_can_be_hidden_while_the_pages_stay_up(client, application, users):
    login(client, 'admin')
    client.post('/admin/podcast/enable')
    assert menu_has_podcast(client)

    client.post('/admin/podcast/nav')

    assert not menu_has_podcast(client)
    assert client.get('/podcast/').status_code == 200
    assert '显示在导航' in lxml_html.tostring(admin_page(client), encoding='unicode')
    client.post('/admin/podcast/nav')
    assert menu_has_podcast(client)


def test_the_admin_can_still_manage_episodes_while_it_is_off(client, application, users):
    login(client, 'admin')

    assert client.get('/admin/podcast/new').status_code == 200
    assert client.get('/admin/podcast/show').status_code == 200


def test_only_admins_can_use_the_switch(client, application, users):
    assert client.post('/admin/podcast/enable').status_code in (302, 401)
    login(client, 'author')

    assert client.post('/admin/podcast/enable').status_code == 403
    assert client.post('/admin/podcast/nav').status_code == 403
    assert show(application) is None or not show(application).enabled


def test_no_ordinary_page_can_take_the_podcast_address(client, users):
    login(client, 'admin')
    response = client.post('/admin/pages/new', data={
        'title': 'x', 'slug': 'podcast', 'nav_order': '1', 'is_published': 'y'})

    assert response.status_code == 200
    assert 'reserved' in response.get_data(as_text=True) or '保留' in response.get_data(as_text=True)
