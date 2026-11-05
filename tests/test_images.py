import io

import sqlalchemy as sa

from app import db
from app.models import Image
from tests.conftest import login

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20


def upload(client, name='photo.png', data=PNG):
    return client.post('/upload', data={'post': (io.BytesIO(data), name)},
                       content_type='multipart/form-data')


def test_upload_creates_an_image_row_and_keeps_the_json_contract(
        client, application, users):
    login(client, 'author')
    response = upload(client, 'My Holiday.PNG')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['uploaded'] == 1 and payload['filename'] == ''
    assert payload['url'].startswith('/files/') and payload['url'].endswith('.png')
    with application.app_context():
        image = db.session.scalar(sa.select(Image))
        assert payload['url'] == f'/files/{image.filename}'
        assert image.original_name == 'My_Holiday.PNG'
        assert image.title == 'My_Holiday'
        assert image.size == len(PNG)
        assert image.user_id == users['author']
        assert image.created_at is not None


def test_upload_rejects_non_images_without_a_row(client, application, users):
    login(client, 'author')
    response = upload(client, 'fake.png', b'not an image at all')
    assert response.status_code == 400
    assert response.get_json() == {
        'uploaded': 0, 'error': {'message': 'Image only!'}}
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Image)) == 0


def test_upload_without_a_file_is_rejected(client, users):
    login(client, 'author')
    response = client.post('/upload', data={},
                           content_type='multipart/form-data')
    assert response.status_code == 400
    assert response.get_json()['error']['message'] == 'No file selected.'


def test_upload_requires_login(client):
    assert upload(client).status_code == 302


# --- sync, usage and visibility -------------------------------------------

import os
import uuid

from app.images import (image_usage, sync_untracked_images, visible_images)
from app.models import Page, Post, PostDraft, PostRevision, User


def make_file(application, name=None, data=PNG, ext='.png'):
    name = name or f'{uuid.uuid4().hex}{ext}'
    folder = application.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), 'wb') as handle:
        handle.write(data)
    return name


def test_sync_registers_valid_unknown_files_once(application):
    with application.app_context():
        good = make_file(application)
        make_file(application, 'notes.txt', b'hello')
        make_file(application, 'short.png')
        assert sync_untracked_images() == 1
        assert sync_untracked_images() == 0
        rows = db.session.scalars(sa.select(Image)).all()
        assert [r.filename for r in rows] == [good]
        assert rows[0].user_id is None
        assert rows[0].title == good.rsplit('.', 1)[0]
        assert rows[0].size == len(PNG)
        assert rows[0].created_at is not None


def test_sync_keeps_existing_rows_untouched(application, users):
    with application.app_context():
        name = make_file(application)
        db.session.add(Image(filename=name, original_name='mine.png',
                             title='Mine', size=1, user_id=users['author']))
        db.session.commit()
        assert sync_untracked_images() == 0
        image = db.session.scalar(sa.select(Image))
        assert (image.title, image.user_id) == ('Mine', users['author'])


def test_sync_survives_a_missing_upload_folder(application):
    with application.app_context():
        assert sync_untracked_images() == 0


def _name():
    return f'{uuid.uuid4().hex}.png'


def test_usage_is_found_in_posts_drafts_and_pages(application, users):
    a, b, c, d = _name(), _name(), _name(), _name()
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'text ![x](/files/{a}) and ![y](http://example.com/files/{b})'
        db.session.add(PostDraft(post_id=post.id, title='T',
                                 body=f'![z](/files/{c})'))
        db.session.add(Page(title='About', slug='about', kind='content',
                            body=f'![p](/files/{d})', is_published=False))
        db.session.add(PostRevision(post_id=post.id, title='old',
                                    body=f'![old](/files/{_name()})'))
        db.session.commit()

        usage = image_usage([a, b, c, d, 'f' * 32 + '.png'])

        assert [(u.kind, u.id) for u in usage[a]] == [('post', post.id)]
        assert [(u.kind, u.id) for u in usage[b]] == [('post', post.id)]
        assert [(u.kind, u.id) for u in usage[c]] == [('draft', post.id)]
        assert [u.kind for u in usage[d]] == ['page']
        assert usage['f' * 32 + '.png'] == []
        assert usage[a][0].title == post.title


def test_usage_ignores_unrelated_text(application, users):
    name = _name()
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'mentions {name} without the files prefix'
        db.session.commit()
        assert image_usage([name])[name] == []


def test_usage_lists_a_post_once_even_if_it_repeats_the_image(
        application, users):
    name = _name()
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'/files/{name} and again /files/{name}'
        db.session.commit()
        assert len(image_usage([name])[name]) == 1


def test_visible_images_depends_on_the_role(application, users):
    with application.app_context():
        for owner in (users['author'], users['other'], None):
            db.session.add(Image(filename=_name(), original_name='a.png',
                                 title=f'img-{owner}', size=1, user_id=owner))
        db.session.commit()
        admin = db.session.get(User, users['admin'])
        author = db.session.get(User, users['author'])

        everything = db.session.scalars(visible_images(admin)).all()
        own = db.session.scalars(visible_images(author)).all()
        assert len(everything) == 3
        assert [i.user_id for i in own] == [users['author']]
