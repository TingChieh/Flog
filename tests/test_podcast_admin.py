import io
from pathlib import Path

import pytest
from lxml import html as lxml_html

from app import db
from app.models import Episode, PodcastShow, PostComment
from tests.conftest import login, make_image, make_mp3
from tests.podcast_helpers import add_episode, set_show


@pytest.fixture()
def admin(client, users):
    login(client, 'admin')
    return client


def uploads(application):
    return Path(application.config['UPLOAD_FOLDER'])


def audio_names(application):
    folder = uploads(application) / 'audio'
    return sorted(p.name for p in folder.glob('*')) if folder.is_dir() else []


def form_data(**overrides):
    data = {'number': '1', 'title': '第一集', 'summary': '摘要',
            'body': '[00:10] 开场', 'published_at': '2022-01-29T16:04',
            'is_published': 'y', 'comments_enabled': 'y',
            'audio': (io.BytesIO(make_mp3(2)), 'ep.mp3')}
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def create(client, **overrides):
    return client.post('/admin/podcast/new', data=form_data(**overrides),
                       content_type='multipart/form-data')


def test_only_admins_reach_the_podcast_pages(client, users):
    paths = ['/admin/podcast', '/admin/podcast/show', '/admin/podcast/new']
    assert all(client.get(p).status_code in (302, 401) for p in paths)
    login(client, 'author')
    assert all(client.get(p).status_code == 403 for p in paths)


def test_the_list_says_what_the_feed_still_needs(admin):
    text = admin.get('/admin/podcast').get_data(as_text=True)

    assert '联系邮箱' in text and '节目封面' in text and '已发布的单集' in text
    tree = lxml_html.fromstring(text)
    links = {a.text_content().strip(): a.get('href')
             for a in tree.xpath('//div[@class="admin-notice"]//a')}
    assert links == {'去节目设置填写': '/admin/podcast/show',
                     '去节目设置上传': '/admin/podcast/show',
                     '新建单集': '/admin/podcast/new'}


def test_a_complete_show_has_nothing_left_to_fix(admin, application):
    with application.app_context():
        set_show(owner_email='me@example.com', cover_filename='c' * 32 + '.png')
        add_episode(uploads(application), 1)

    assert 'RSS 还差几项' not in admin.get('/admin/podcast').get_data(as_text=True)


def test_a_new_episode_is_saved_with_its_audio_and_local_release_time(admin, application):
    response = create(admin)

    assert response.status_code == 302
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        assert (episode.number, episode.title) == (1, '第一集')
        assert episode.audio_duration == 2
        assert episode.audio_size == len(make_mp3(2))
        assert episode.is_published and episode.comments_enabled
        # 16:04 in Asia/Shanghai is 08:04 UTC, which is what is stored.
        assert (episode.published_at.hour, episode.published_at.minute) == (8, 4)
    assert audio_names(application) == [episode.audio_filename]


def test_the_form_suggests_the_next_number(admin, application):
    with application.app_context():
        add_episode(uploads(application), 4)

    tree = lxml_html.fromstring(admin.get('/admin/podcast/new').get_data(as_text=True))

    assert tree.xpath('//input[@name="number"]/@value') == ['5']


def test_an_episode_needs_audio(admin, application):
    response = create(admin, audio=None)

    assert response.status_code == 400
    assert '请选择音频文件' in response.get_data(as_text=True)
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Episode)) == 0


def test_bad_audio_is_refused_with_a_reason(admin, application):
    response = create(admin, audio=(io.BytesIO(b'nope' * 100), 'ep.mp3'))

    assert response.status_code == 400
    assert '无法识别' in response.get_data(as_text=True)
    assert audio_names(application) == []


def test_numbers_cannot_repeat(admin, application):
    create(admin)
    response = create(admin, audio=(io.BytesIO(make_mp3(1)), 'again.mp3'))

    assert response.status_code == 400
    assert '这个期号已经有节目了' in response.get_data(as_text=True)
    assert len(audio_names(application)) == 1


def test_a_rejected_cover_does_not_leave_the_audio_behind(admin, application):
    response = create(admin, cover=(io.BytesIO(b'not an image'), 'c.png'))

    assert response.status_code == 400
    assert audio_names(application) == []
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Episode)) == 0


def test_a_cover_is_stored_as_an_image(admin, application):
    create(admin, cover=(io.BytesIO(make_image('PNG', (40, 40))), 'cover.png'))

    with application.app_context():
        name = db.session.scalar(db.select(Episode)).cover_filename
    assert name and (uploads(application) / name).is_file()


def test_editing_without_a_file_keeps_the_audio(admin, application):
    create(admin)
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        episode_id, filename = episode.id, episode.audio_filename

    response = admin.post(
        f'/admin/podcast/{episode_id}/edit',
        data=form_data(title='改名了', audio=None),
        content_type='multipart/form-data')

    assert response.status_code == 302
    with application.app_context():
        episode = db.session.get(Episode, episode_id)
        assert (episode.title, episode.audio_filename) == ('改名了', filename)
    assert audio_names(application) == [filename]


def test_replacing_the_audio_removes_the_old_file(admin, application):
    create(admin)
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        episode_id, old = episode.id, episode.audio_filename

    admin.post(f'/admin/podcast/{episode_id}/edit',
               data=form_data(audio=(io.BytesIO(make_mp3(5)), 'new.mp3')),
               content_type='multipart/form-data')

    with application.app_context():
        episode = db.session.get(Episode, episode_id)
        assert episode.audio_filename != old and episode.audio_duration == 5
    assert audio_names(application) == [episode.audio_filename]


def test_a_bad_replacement_changes_nothing(admin, application):
    create(admin)
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        episode_id, filename = episode.id, episode.audio_filename

    response = admin.post(
        f'/admin/podcast/{episode_id}/edit',
        data=form_data(title='不该保存', audio=(io.BytesIO(b'x' * 50), 'bad.mp3')),
        content_type='multipart/form-data')

    assert response.status_code == 400
    with application.app_context():
        episode = db.session.get(Episode, episode_id)
        assert (episode.title, episode.audio_filename) == ('第一集', filename)
    assert audio_names(application) == [filename]


def test_publishing_can_be_toggled(admin, application, podcast_on):
    create(admin)
    with application.app_context():
        episode_id = db.session.scalar(db.select(Episode)).id

    admin.post(f'/admin/podcast/{episode_id}/publish')

    with application.app_context():
        assert not db.session.get(Episode, episode_id).is_published
    assert admin.get('/podcast/1').status_code == 404


def test_deleting_removes_the_audio_and_the_comments(admin, application):
    create(admin)
    with application.app_context():
        episode_id = db.session.scalar(db.select(Episode)).id
        db.session.add(PostComment(episode_id=episode_id, name='a',
                                   email='a@example.com', body='x'))
        db.session.commit()

    response = admin.post(f'/admin/podcast/{episode_id}/delete',
                          data={'confirm': 'y'})

    assert response.status_code == 302
    assert audio_names(application) == []
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Episode)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(PostComment)) == 0


def test_a_file_over_the_limit_is_turned_away_with_a_message(admin, application):
    application.config['PODCAST_AUDIO_MAX_MB'] = 1
    big = io.BytesIO(make_mp3(2) + b'\0' * (1024 * 1024 + 10))

    response = admin.post('/admin/podcast/new',
                          data=form_data(audio=(big, 'big.mp3')),
                          content_type='multipart/form-data',
                          follow_redirects=True)

    assert '音频最大 1 MB' in response.get_data(as_text=True)
    assert audio_names(application) == []


def test_large_audio_is_allowed_here_but_not_elsewhere(admin, application):
    assert application.config['MAX_CONTENT_LENGTH'] == 20 * 1024 * 1024
    assert application.config['PODCAST_AUDIO_MAX_MB'] >= 100


def test_show_settings_are_saved_and_used(admin, application, podcast_on):
    response = admin.post('/admin/podcast/show', data={
        'title': '新节目名', 'description': '一段简介', 'author': '阿丁',
        'owner_email': 'me@example.com', 'category': 'Technology',
        'apple_url': 'https://podcasts.apple.com/x', 'xiaoyuzhou_url': '',
        'cover': (io.BytesIO(make_image('PNG', (30, 30))), 'show.png'),
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    with application.app_context():
        show = db.session.get(PodcastShow, 1)
        assert (show.title, show.owner_email) == ('新节目名', 'me@example.com')
        assert show.xiaoyuzhou_url is None
        assert show.cover_filename
    public = admin.get('/podcast/').get_data(as_text=True)
    assert '新节目名' in public and '一段简介' in public
    assert 'Apple Podcasts' in public and '小宇宙' not in public


def test_show_links_must_be_web_addresses(admin, podcast_on):
    response = admin.post('/admin/podcast/show', data={
        'apple_url': 'javascript:alert(1)'}, content_type='multipart/form-data')

    assert response.status_code == 200
    assert 'http://' in response.get_data(as_text=True)
    assert 'javascript:alert' not in admin.get('/podcast/').get_data(as_text=True)


def test_episode_comments_appear_in_the_comment_admin_and_can_be_answered(
        admin, application):
    with application.app_context():
        episode_id = add_episode(uploads(application), 1, '第一集')
        db.session.add(PostComment(
            episode_id=episode_id, name='Reader', email='r@example.com',
            body='好听', status='approved'))
        db.session.commit()
        comment_id = db.session.scalar(db.select(PostComment)).id

    tree = lxml_html.fromstring(admin.get('/admin/comments').get_data(as_text=True))
    assert tree.xpath('//a[@data-comment-target]/@href') == ['/podcast/1']
    only_here = admin.get('/admin/comments?target=episode:%d' % episode_id)
    assert only_here.status_code == 200 and '好听' in only_here.get_data(as_text=True)

    admin.post(f'/admin/comments/{comment_id}/reply', data={'body': '谢谢'})
    with application.app_context():
        reply = db.session.scalars(db.select(PostComment).where(
            PostComment.parent_id == comment_id)).one()
        assert reply.episode_id == episode_id


# --- the size limit with CSRF switched on, as in production -------------------------

def csrf_token(client, path='/admin/podcast/new'):
    tree = lxml_html.fromstring(client.get(path).get_data(as_text=True))
    return tree.xpath('//input[@name="csrf_token"]/@value')[0]


def test_an_admin_can_upload_audio_over_the_general_limit(admin, application):
    application.config['WTF_CSRF_ENABLED'] = True
    big = make_mp3(1400)
    assert len(big) > application.config['MAX_CONTENT_LENGTH']

    response = admin.post('/admin/podcast/new', data=form_data(
        csrf_token=csrf_token(admin), audio=(io.BytesIO(big), 'big.mp3')),
        content_type='multipart/form-data')

    assert response.status_code == 302
    with application.app_context():
        assert db.session.scalar(db.select(Episode)).audio_size == len(big)


def test_the_higher_limit_is_for_admins_on_the_upload_pages_only(
        client, application, users):
    application.config['WTF_CSRF_ENABLED'] = True
    over = application.config['MAX_CONTENT_LENGTH'] + 1024

    def post(path, field):
        return client.post(path, data={field: (io.BytesIO(b'\0' * over), 'f.bin')},
                           content_type='multipart/form-data')

    # Signed out: the general limit applies even on the upload page.
    assert post('/admin/podcast/new', 'audio').status_code == 303

    # A signed-in admin does not get the higher limit on other pages.
    login(client, 'admin')
    assert post('/admin/podcast/show', 'cover').status_code == 303
    with application.app_context():
        assert db.session.get(PodcastShow, 1) is None
    assert not (uploads(application) / 'audio').exists()
