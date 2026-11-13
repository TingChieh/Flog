from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lxml import html as lxml_html

from app import db
from app.models import PostComment, SiteSettings
from tests.conftest import login
from tests.podcast_helpers import add_episode, set_show

ITUNES = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'


pytestmark = pytest.mark.usefixtures('podcast_on')


def uploads(application):
    return Path(application.config['UPLOAD_FOLDER'])


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return lxml_html.fromstring(response.get_data(as_text=True))


def feed(client):
    response = client.get('/podcast/feed.xml')
    assert response.status_code == 200
    assert response.content_type.startswith('application/rss+xml')
    return ET.fromstring(response.data).find('channel')


def test_index_lists_published_episodes_newest_first(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, '第一集')
        add_episode(uploads(application), 2, '第二集',
                    published_at=__import__('datetime').datetime(2022, 3, 6))
        add_episode(uploads(application), 3, '草稿', published=False)

    titles = page(client, '/podcast/').xpath(
        '//span[@class="episode-item__title"]/text()')

    assert titles == ['第二集', '第一集']


def test_index_shows_the_show_text_and_subscribe_links(client, application):
    with application.app_context():
        set_show(title='示例节目', apple_url='https://podcasts.apple.com/x',
                 xiaoyuzhou_url='https://www.xiaoyuzhoufm.com/x')

    tree = page(client, '/podcast/')

    assert tree.xpath('//h1')[0].text_content() == '示例节目'
    links = {a.text_content().strip(): a.get('href')
             for a in tree.xpath('//div[@id="subscribe"]/a')}
    assert links == {'Apple Podcasts': 'https://podcasts.apple.com/x',
                     '小宇宙': 'https://www.xiaoyuzhoufm.com/x',
                     'RSS': '/podcast/feed.xml'}


def test_a_fresh_install_carries_no_ones_show(client, application):
    with application.app_context():
        db.session.get(SiteSettings, 1).site_name = 'Some Blog'
        db.session.commit()

    tree = page(client, '/podcast/')

    # Until the owner writes it, the name comes from the site, and there is no
    # made-up description or author.
    assert tree.xpath('//h1')[0].text_content() == 'Some Blog 播客'
    assert not tree.xpath('//p[@class="podcast-show__description"]')
    assert not tree.xpath('//p[@class="podcast-show__author"]')
    main = tree.xpath('//main')[0].text_content()
    assert '坡道' not in main and 'Aisaka' not in main
    channel = feed(client)
    assert '坡道' not in ET.tostring(channel, encoding='unicode')
    assert channel.findtext('title') == 'Some Blog 播客'
    assert channel.findtext('description') == 'Some Blog 播客'
    assert channel.find(f'{ITUNES}author').text == 'Some Blog'


def test_the_written_description_and_author_are_shown(client, application):
    with application.app_context():
        set_show(title='示例节目', description='一段简介', author='某某')

    tree = page(client, '/podcast/')

    assert tree.xpath('//p[@class="podcast-show__description"]')[0].text_content() == '一段简介'
    assert '某某' in tree.xpath('//p[@class="podcast-show__author"]')[0].text_content()
    assert feed(client).find(f'{ITUNES}author').text == '某某'


def test_subscribe_links_that_are_not_set_are_left_out(client, application):
    tree = page(client, '/podcast/')

    assert [a.text_content().strip()
            for a in tree.xpath('//div[@id="subscribe"]/a')] == ['RSS']


def test_the_episode_page_has_a_player_notes_and_neighbours(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, '第一集')
        add_episode(uploads(application), 2, '第二集')
        add_episode(uploads(application), 3, '第三集')

    tree = page(client, '/podcast/2')

    audio = tree.xpath('//audio[@data-episode-audio]')[0]
    assert audio.get('src').startswith('/files/audio/')
    assert audio.get('src').endswith('.mp3')
    assert '时间轴' in tree.xpath('//div[@data-episode-notes]')[0].text_content()
    nav = [a.get('href') for a in tree.xpath('//nav[@class="podcast-episode__nav"]/a')]
    assert nav == ['/podcast/1', '/podcast/3']


def test_the_player_has_site_controls_and_keeps_the_browser_ones_as_a_fallback(
        client, application):
    with application.app_context():
        add_episode(uploads(application), 1)

    tree = page(client, '/podcast/1')

    player = tree.xpath('//div[@data-podcast-player]')[0]
    assert player.get('data-duration') == '3'
    assert player.xpath('.//audio[@data-episode-audio][@controls]')
    controls = player.xpath('.//div[@data-player-controls][@hidden]')[0]
    assert controls.xpath('.//button[@data-player-play]')
    assert controls.xpath('.//input[@type="range"][@data-player-seek]/@max') == ['3']
    assert controls.xpath('.//*[@data-player-total]')[0].text == '0:03'
    assert [b.get('data-player-skip') for b in controls.xpath('.//button[@data-player-skip]')] == ['-15', '30']
    assert controls.xpath('.//button[@data-player-rate]')
    scripts = [src.split('?')[0] for src in tree.xpath('//script/@src')]
    assert '/static/podcast-controls.js' in scripts and '/static/podcast-player.js' in scripts
    assert player.xpath('.//a[@download]')


def test_an_unpublished_or_missing_episode_is_a_404(client, application):
    with application.app_context():
        add_episode(uploads(application), 5, '草稿', published=False)

    assert client.get('/podcast/5').status_code == 404
    assert client.get('/podcast/99').status_code == 404


def test_the_audio_can_be_fetched_in_ranges(client, application):
    with application.app_context():
        add_episode(uploads(application), 1)
    src = page(client, '/podcast/1').xpath('//audio/@src')[0]

    response = client.get(src, headers={'Range': 'bytes=0-99'})

    assert response.status_code == 206
    assert len(response.data) == 100
    assert response.headers['Content-Range'].startswith('bytes 0-99/')
    assert response.headers['Accept-Ranges'] == 'bytes'
    assert response.mimetype == 'audio/mpeg'


# --- the podcast is a page of the blog ----------------------------------------------

def menu_links(tree):
    return [(a.text_content().strip(), a.get('href'))
            for a in tree.xpath('//ul[@class="site-nav__links"]//a')]


def test_the_blog_menu_links_to_the_podcast_page(client, application, users):
    assert ('播客', '/podcast/') in menu_links(page(client, '/index'))


def test_podcast_pages_keep_the_blogs_menu_name_title_and_footer(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, '第一集')

    index = page(client, '/podcast/')
    episode = page(client, '/podcast/1')

    assert [text for text, _ in menu_links(index)] == ['首页', '归档', '播客']
    assert index.xpath('//a[@class="site-brand"]/@href') == ['/index']
    assert index.xpath('//a[@class="site-brand"]')[0].text_content() == "Aisaka's Blog"
    assert index.xpath('//a[@data-search-open]')
    assert index.xpath('//title')[0].text == "Aisaka's Blog 播客 - Aisaka's Blog"
    assert episode.xpath('//title')[0].text == "第一集 - Aisaka's Blog"
    current = index.xpath('//ul[@class="site-nav__links"]//a[@aria-current="page"]')
    assert [a.get('href') for a in current] == ['/podcast/']


def test_the_footer_rss_link_follows_the_section(client, application, users):
    with application.app_context():
        add_episode(uploads(application), 1)

    def footer_feed(path):
        return page(client, path).xpath(
            '//footer//a[contains(text(), "RSS")]/@href')

    assert footer_feed('/podcast/') == ['/podcast/feed.xml']
    assert footer_feed('/podcast/1') == ['/podcast/feed.xml']
    assert footer_feed('/index') == ['/feed.xml']
    assert footer_feed('/archive') == ['/feed.xml']


def test_podcast_pages_offer_the_podcast_feed_next_to_the_blog_feed(client, application):
    for path in ('/podcast/', '/index'):
        feeds = page(client, path).xpath(
            '//link[@rel="alternate"][@type="application/rss+xml"]/@href')
        assert '/feed.xml' in feeds
        assert ('/podcast/feed.xml' in feeds) == (path == '/podcast/')


# --- feed -----------------------------------------------------------------------

def test_the_feed_describes_the_show_and_published_episodes(client, application):
    with application.app_context():
        set_show(owner_email='me@example.com', cover_filename='c' * 32 + '.png',
                 author='Aisaka')
        add_episode(uploads(application), 1, '第一集', feed_guid='https://old.example.com/?p=36')
        add_episode(uploads(application), 2, '草稿', published=False)

    channel = feed(client)

    assert channel.findtext('title') == "Aisaka's Blog 播客"
    assert channel.findtext('language') == 'zh-cn'
    assert channel.find(f'{ITUNES}owner/{ITUNES}email').text == 'me@example.com'
    assert channel.find(f'{ITUNES}image').get('href').endswith('/files/' + 'c' * 32 + '.png')
    items = channel.findall('item')
    assert [item.findtext('title') for item in items] == ['第一集']
    item = items[0]
    enclosure = item.find('enclosure')
    assert enclosure.get('url').startswith('http://localhost/files/audio/')
    assert enclosure.get('type') == 'audio/mpeg'
    assert int(enclosure.get('length')) > 1000
    assert item.findtext(f'{ITUNES}duration') == '3'
    assert item.findtext(f'{ITUNES}episode') == '1'
    assert item.findtext('pubDate').startswith('Sat, 29 Jan 2022 08:00:00')


def test_an_episode_keeps_the_id_it_had_in_the_old_feed(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, '旧', feed_guid='https://old.example.com/?p=36')
        add_episode(uploads(application), 2, '新')

    guids = {item.findtext('title'): item.find('guid')
             for item in feed(client).findall('item')}

    assert guids['旧'].text == 'https://old.example.com/?p=36'
    assert guids['旧'].get('isPermaLink') == 'false'
    assert guids['新'].text == 'http://localhost/podcast/2'


def test_the_feed_of_an_empty_show_is_still_valid(client, application):
    assert feed(client).findall('item') == []


def test_episodes_are_in_the_sitemap(client, application):
    with application.app_context():
        add_episode(uploads(application), 1)
        add_episode(uploads(application), 2, published=False)

    text = client.get('/sitemap.xml').get_data(as_text=True)

    assert 'http://localhost/podcast/' in text
    assert 'http://localhost/podcast/1<' in text
    assert '/podcast/2<' not in text


# --- comments -------------------------------------------------------------------

def comment(client, number, **data):
    data.setdefault('name', 'Reader')
    data.setdefault('email', 'reader@example.com')
    data.setdefault('body', '好听！')
    return client.post(f'/podcast/{number}', data=data, follow_redirects=True)


def test_a_first_comment_on_an_episode_waits_for_review(client, application):
    with application.app_context():
        add_episode(uploads(application), 1)

    response = comment(client, 1)

    assert '审核通过后显示' in response.get_data(as_text=True)
    with application.app_context():
        saved = db.session.scalar(db.select(PostComment))
        assert saved.status == 'pending'
        assert saved.episode.number == 1
        assert saved.post_id is None and saved.page_id is None


def test_the_site_owner_comments_are_published_at_once(client, application, users):
    with application.app_context():
        add_episode(uploads(application), 1)
    login(client, 'admin')

    response = comment(client, 1, body='谢谢收听')

    tree = lxml_html.fromstring(response.get_data(as_text=True))
    assert '谢谢收听' in ' '.join(
        t.text_content() for t in tree.xpath('//div[@class="post-comment__text"]'))


def test_comments_can_be_switched_off_for_an_episode(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, comments_enabled=False)

    assert client.post('/podcast/1', data={
        'name': 'a', 'email': 'a@example.com', 'body': 'x'}).status_code == 403
    tree = page(client, '/podcast/1')
    assert not tree.xpath('//form[@id="comment-form"]')


def test_deleting_an_episode_deletes_its_comments(application):
    with application.app_context():
        episode_id = add_episode(uploads(application), 1)
        db.session.add(PostComment(
            episode_id=episode_id, name='a', email='a@example.com', body='x'))
        db.session.commit()
        from app.models import Episode
        db.session.delete(db.session.get(Episode, episode_id))
        db.session.commit()

        assert db.session.scalar(db.select(db.func.count()).select_from(PostComment)) == 0


def test_a_comment_must_belong_to_exactly_one_thing(application):
    import pytest
    from sqlalchemy.exc import IntegrityError, OperationalError
    with application.app_context():
        db.session.add(PostComment(name='a', email='a@example.com', body='x'))
        # SQLite raises IntegrityError for CHECK failures; MariaDB raises OperationalError (4025).
        with pytest.raises((IntegrityError, OperationalError)):
            db.session.commit()
        db.session.rollback()


def test_the_owner_is_mailed_a_link_to_the_episode(client, application, users, outbox):
    with application.app_context():
        add_episode(uploads(application), 1, '第一集')
        # A known address is published at once and so announced right away.
        db.session.add(PostComment(
            episode_id=1, name='Reader', email='reader@example.com',
            body='earlier', status='approved'))
        db.session.commit()

    comment(client, 1, body='再来一条')

    assert outbox
    assert 'http://localhost/podcast/1#comment-' in outbox[0].body
    assert '第一集' in outbox[0].subject


def test_feed_answers_conditional_requests_with_304(client, application):
    with application.app_context():
        add_episode(uploads(application), 1, '第一集')
    first = client.get('/podcast/feed.xml')
    assert first.headers['ETag']
    assert 'max-age' in first.headers['Cache-Control']
    again = client.get('/podcast/feed.xml',
                       headers={'If-None-Match': first.headers['ETag']})
    assert again.status_code == 304
