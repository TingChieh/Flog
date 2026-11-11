import base64
import io
import re
from pathlib import Path

import pytest

from app import db
from app.content import render_content
from app.models import Post
from app.security import sanitize_html
from tests.conftest import login, make_image


def test_sanitize_html_removes_scripts_and_event_handlers():
    value = '<p onclick="alert(1)">hello<script>alert(1)</script></p>'

    cleaned = sanitize_html(value)

    assert '<script' not in cleaned
    assert 'onclick' not in cleaned
    assert '<p>helloalert(1)</p>' == cleaned


def test_render_content_supports_markdown_and_sanitizes_raw_html(application):
    with application.app_context():
        rendered = str(render_content(
            '# Heading\n\n##### Heading five\n\n###### Heading six\n\n'
            '- one\n- two\n\n'
            '[safe link](https://example.com)\n\n'
            '```python\nprint("code")\n```\n\n'
            '| A | B |\n| - | - |\n| 1 | 2 |\n\n'
            '<img src="javascript:alert(1)" onerror="alert(2)">',
            'markdown'))

    assert '<h1>Heading</h1>' in rendered
    assert '<h5>Heading five</h5>' in rendered
    assert '<h6>Heading six</h6>' in rendered
    assert '<li>one</li>' in rendered
    assert 'href="https://example.com"' in rendered
    assert '<pre><code' in rendered
    assert '<table>' in rendered
    assert 'javascript:' not in rendered
    assert 'onerror' not in rendered


def test_render_content_defaults_unknown_formats_to_legacy_html(application):
    with application.app_context():
        rendered = str(render_content('<strong>legacy</strong>', 'unexpected'))

    assert rendered == '<strong>legacy</strong>'


def test_non_owner_cannot_delete_post(client, users):
    login(client, 'other')

    response = client.post(f'/post/delete/{users["post"]}')

    assert response.status_code == 403


def test_author_can_delete_own_post(client, application, users):
    login(client, 'author')

    response = client.post(f'/post/delete/{users["post"]}')

    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(Post, users['post']) is None


def test_non_admin_cannot_manage_categories(client, users):
    login(client, 'author')

    response = client.post('/admin/categories', data={'name': 'Private'})

    assert response.status_code == 403


def test_upload_requires_authentication(client):
    response = client.post('/upload', data={
        'post': (io.BytesIO(b'not an image'), 'image.png'),
    })

    assert response.status_code == 302


def test_csrf_rejects_post_without_token(client, application):
    application.config['WTF_CSRF_ENABLED'] = True

    response = client.post('/login', data={
        'username': 'someone',
        'password': 'password',
    })

    assert response.status_code == 400


def test_upload_rejects_fake_image(client, users):
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(b'not an image'), 'image.png'),
    })

    assert response.status_code == 400
    assert response.get_json() == {
        'uploaded': 0,
        'error': {'message': 'Image only!'},
    }


def test_authenticated_image_upload_preserves_legacy_success_contract(
        client, application, users):
    image_bytes = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
        '+A8AAQUBAScY42YAAAAASUVORK5CYII='
    )
    unauthenticated = client.post('/upload', data={
        'post': (io.BytesIO(image_bytes), 'original.png'),
    })
    assert unauthenticated.status_code == 302

    login(client, 'author')
    response = client.post('/upload', data={
        'post': (io.BytesIO(image_bytes), 'original.png'),
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {'uploaded', 'filename', 'url'}
    assert payload['uploaded'] == 1
    assert payload['filename'] == ''
    assert re.fullmatch(r'/files/[0-9a-f]{32}\.png', payload['url'])

    saved_path = Path(application.config['UPLOAD_FOLDER']) / Path(
        payload['url']).name
    assert saved_path.read_bytes() == image_bytes
    served = client.get(payload['url'])
    assert served.status_code == 200
    assert served.data == image_bytes


def test_authenticated_image_upload_accepts_images_over_legacy_five_mb_limit(
        client, application, users):
    """Catch camera exports and screenshots being rejected by the old 5 MB cap."""
    image_bytes = make_image(size=(1700, 1300), noise=True)
    assert len(image_bytes) > 6 * 1024 * 1024
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(image_bytes), 'large.png'),
    })

    assert response.status_code == 200
    assert response.get_json()['uploaded'] == 1


def test_responses_carry_security_headers(client):
    response = client.get('/')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'


def test_https_site_url_makes_sign_in_cookies_secure(monkeypatch):
    import importlib
    import config
    monkeypatch.setenv('SITE_URL', 'https://blog.example.com')
    try:
        secure = importlib.reload(config).Config
        assert secure.SESSION_COOKIE_SECURE and secure.REMEMBER_COOKIE_SECURE
        monkeypatch.setenv('SITE_URL', '')
        assert not importlib.reload(config).Config.SESSION_COOKIE_SECURE
    finally:
        monkeypatch.undo()
        importlib.reload(config)



@pytest.mark.parametrize('target', [
    '//evil.example', '/\\evil.example', '/\t/evil.example',
    'https://evil.example', 'https:evil.example', 'javascript:alert(1)',
])
def test_sign_in_never_redirects_off_site(client, users, target):
    response = client.post('/login', query_string={'next': target}, data={
        'username': 'author', 'password': 'password'})
    assert response.headers['Location'] == '/index'


def test_sign_in_returns_to_a_local_page(client, users):
    response = client.post('/login', query_string={'next': '/admin/posts?scope=mine'},
                           data={'username': 'author', 'password': 'password'})
    assert response.headers['Location'] == '/admin/posts?scope=mine'


def test_user_without_a_password_cannot_sign_in(client, application, users):
    from app.models import User
    with application.app_context():
        db.session.get(User, users['author']).password_hash = None
        db.session.commit()
    response = client.post('/login', data={'username': 'author', 'password': 'guess'})
    assert response.status_code == 302 and response.headers['Location'] == '/login'
