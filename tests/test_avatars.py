import io
import os

from PIL import Image as PILImage

from app import db
from app.models import User
from tests.conftest import login, make_image

PNG = make_image()
JPG = make_image('JPEG')


def upload(client, data=PNG, filename='me.png', **extra):
    return client.post('/admin/account/avatar', data={
        'avatar': (io.BytesIO(data), filename), **extra,
    }, content_type='multipart/form-data')


def avatar_filename(application, user_id):
    with application.app_context():
        return db.session.get(User, user_id).avatar_filename


def avatar_dir(application):
    return os.path.join(application.config['UPLOAD_FOLDER'], 'avatars')


def test_avatar_page_requires_login(client):
    assert client.get('/admin/account/avatar').status_code in (302, 401)


def test_member_can_open_the_avatar_page(client, users):
    login(client, 'author')
    response = client.get('/admin/account/avatar')
    assert response.status_code == 200
    assert 'cravatar.cn' in response.get_data(as_text=True)


def test_upload_stores_the_file_and_uses_it_as_the_avatar(
        client, application, users):
    login(client, 'author')
    response = upload(client)
    assert response.status_code == 302
    name = avatar_filename(application, users['author'])
    assert name and name.endswith('.png')
    assert os.path.isfile(os.path.join(avatar_dir(application), name))
    with application.test_request_context():
        user = db.session.get(User, users['author'])
        assert user.avatar(70) == f'/files/avatars/{name}'
    assert client.get(f'/files/avatars/{name}').data == PNG


def test_post_page_shows_the_uploaded_avatar(client, application, users):
    login(client, 'author')
    upload(client)
    name = avatar_filename(application, users['author'])
    html = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert f'/files/avatars/{name}' in html


def test_new_upload_replaces_and_deletes_the_old_file(
        client, application, users):
    login(client, 'author')
    upload(client)
    first = avatar_filename(application, users['author'])
    upload(client, JPG, 'me.jpg')
    second = avatar_filename(application, users['author'])
    assert second != first and second.endswith('.jpg')
    assert sorted(os.listdir(avatar_dir(application))) == [second]


def test_remove_restores_the_default_avatar(client, application, users):
    login(client, 'author')
    upload(client)
    assert client.post('/admin/account/avatar/remove').status_code == 302
    assert avatar_filename(application, users['author']) is None
    assert os.listdir(avatar_dir(application)) == []
    with application.test_request_context():
        assert 'cravatar.cn' in db.session.get(User, users['author']).avatar(70)


def test_rejects_non_images_and_wrong_signatures(client, application, users):
    login(client, 'author')
    for data, name in ((b'<script>alert(1)</script>', 'x.png'),
                       (b'plain text', 'me.txt'), (JPG, 'fake.png')):
        response = upload(client, data, name)
        assert response.status_code == 302
    assert avatar_filename(application, users['author']) is None
    assert not os.path.isdir(avatar_dir(application)) \
        or os.listdir(avatar_dir(application)) == []


def test_rejects_files_over_two_megabytes(client, application, users):
    login(client, 'author')
    upload(client, PNG + b'0' * (2 * 1024 * 1024), 'big.png')
    assert avatar_filename(application, users['author']) is None


def test_avatars_are_per_user(client, application, users):
    login(client, 'author')
    upload(client)
    assert avatar_filename(application, users['other']) is None


def test_avatar_actions_require_csrf(client, application, users):
    application.config['WTF_CSRF_ENABLED'] = True
    login(client, 'author')
    assert upload(client).status_code == 400
    assert client.post('/admin/account/avatar/remove').status_code == 400


def test_deleting_a_user_removes_their_avatar_file(client, application, users):
    login(client, 'other')
    upload(client)
    name = avatar_filename(application, users['other'])
    client.post('/logout')
    login(client, 'admin')
    client.post(f'/admin/users/{users["other"]}/delete',
                data={'receiver': users['author']})
    assert not os.path.exists(os.path.join(avatar_dir(application), name))


def test_large_avatars_are_shrunk_to_256_pixels(client, application, users):
    login(client, 'author')
    upload(client, make_image('JPEG', (1200, 600), photo=True), 'me.jpg')
    name = avatar_filename(application, users['author'])
    with PILImage.open(os.path.join(avatar_dir(application), name)) as stored:
        assert stored.size == (256, 128)


def test_signature_only_avatars_are_rejected(client, application, users):
    login(client, 'author')
    upload(client, b'\x89PNG\r\n\x1a\n' + b'0' * 20)
    assert avatar_filename(application, users['author']) is None
