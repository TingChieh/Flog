from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from click.testing import CliRunner

from app import app, db
from app.models import Episode
from tests.conftest import make_mp3
from tests.podcast_helpers import add_episode

pytestmark = pytest.mark.usefixtures('podcast_on')


@pytest.fixture()
def old_domain(application):
    application.config.update(
        SITE_URL='https://blog.example.com',
        PODCAST_REDIRECT_HOSTS=frozenset({'podcast.example.com'}))
    return application


def get(client, path, host='podcast.example.com', **kwargs):
    return client.get(path, headers={'Host': host}, **kwargs)


def test_the_old_domain_goes_to_the_podcast(client, old_domain):
    response = get(client, '/')

    assert response.status_code == 301
    assert response.headers['Location'] == 'https://blog.example.com/podcast/'


def test_the_host_is_matched_ignoring_case_and_port(client, old_domain):
    response = get(client, '/', host='Podcast.Example.com:443')

    assert response.status_code == 301


def test_the_old_feed_addresses_go_to_the_new_feed(client, old_domain):
    for path in ('/feed/podcast/', '/feed/podcast', '/feed/', '/feed'):
        response = get(client, path)
        assert response.headers['Location'] == (
            'https://blog.example.com/podcast/feed.xml'), path
    assert get(client, '/', query_string={'feed': 'podcast'}
               ).headers['Location'].endswith('/podcast/feed.xml')


def test_an_old_episode_address_goes_to_the_episode(client, old_domain):
    with old_domain.app_context():
        add_episode(Path(old_domain.config['UPLOAD_FOLDER']), 2, 'EP2',
                    legacy_path='/2022/01/29/ep-002-虚假的年终总结真实的随意吹水/')
    path = '/2022/01/29/ep-002-' + quote('虚假的年终总结真实的随意吹水') + '/'

    response = get(client, path)

    assert response.headers['Location'] == 'https://blog.example.com/podcast/2'
    assert get(client, path.rstrip('/')).status_code == 301


def test_other_old_addresses_land_on_the_podcast_home(client, old_domain):
    for path in ('/author/tingchieh/', '/wp-login.php', '/2021/12/19/hello-world/'):
        assert get(client, path).headers['Location'] == (
            'https://blog.example.com/podcast/'), path


def test_the_main_site_is_not_affected(client, old_domain, users):
    assert client.get('/podcast/').status_code == 200
    assert client.get('/index').status_code == 200


def test_nothing_redirects_until_both_settings_exist(client, application):
    application.config.update(
        SITE_URL='', PODCAST_REDIRECT_HOSTS=frozenset({'podcast.example.com'}))
    assert get(client, '/podcast/').status_code == 200
    application.config.update(
        SITE_URL='https://blog.example.com', PODCAST_REDIRECT_HOSTS=frozenset())
    assert get(client, '/podcast/').status_code == 200


# --- flask podcast add ------------------------------------------------------------

def run_add(application, tmp_path, *args):
    audio = tmp_path / 'EP.mp3'
    audio.write_bytes(make_mp3(2))
    notes = tmp_path / 'notes.md'
    notes.write_text('[00:05] 开场', encoding='utf-8')
    return CliRunner().invoke(app.cli, [
        'podcast', 'add', '--number', '4', '--title', 'EP-004 标题',
        '--audio', str(audio), '--notes', str(notes),
        '--published', '2022-11-19 23:49', '--feed-guid',
        'https://podcast.example.com/?p=98', '--legacy-path', '/2022/11/19/x/',
        *args])


def test_the_cli_adds_an_episode_from_files(application, tmp_path):
    result = run_add(application, tmp_path)

    assert result.exit_code == 0, result.output
    assert 'EP-004' in result.output
    with application.app_context():
        episode = db.session.scalar(db.select(Episode))
        assert episode.number == 4 and episode.is_published
        assert episode.audio_duration == 2
        assert episode.body == '[00:05] 开场'
        assert episode.feed_guid == 'https://podcast.example.com/?p=98'
        # 23:49 in China is 15:49 UTC.
        assert episode.published_at == datetime(2022, 11, 19, 15, 49)


def test_the_cli_can_leave_the_episode_as_a_draft(application, tmp_path):
    run_add(application, tmp_path, '--draft')
    with application.app_context():
        assert not db.session.scalar(db.select(Episode)).is_published


def test_the_cli_refuses_a_file_that_is_not_audio(application, tmp_path):
    bad = tmp_path / 'bad.mp3'
    bad.write_bytes(b'nope' * 50)

    result = CliRunner().invoke(app.cli, [
        'podcast', 'add', '--number', '1', '--title', 't', '--audio', str(bad),
        '--published', '2022-01-01 10:00'])

    assert result.exit_code != 0
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Episode)) == 0
