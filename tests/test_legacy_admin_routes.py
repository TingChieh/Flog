import pytest

from app import db
from app.models import Category, Post
from tests.conftest import login


def create_legacy_records(application):
    with application.app_context():
        category = Category(name='Legacy category')
        db.session.add(category)
        db.session.commit()
        return {'category': category.id}


def test_legacy_post_editor_redirects_to_admin_editor(client, users):
    login(client, 'author')

    response = client.get(f'/post/{users["post"]}/edit')

    assert response.status_code == 302
    assert response.headers['Location'].endswith(
        f'/admin/posts/{users["post"]}/edit')


def test_legacy_post_editor_rejects_non_owner(client, users):
    login(client, 'other')
    assert client.get(f'/post/{users["post"]}/edit').status_code == 403


def test_legacy_post_submit_publishes_an_unpublished_post(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = False
        category_id = post.category_id
        db.session.commit()

    login(client, 'author')
    response = client.post(f'/post/{users["post"]}/edit', data={
        'title': 'Published through legacy form',
        'category': str(category_id),
        'post': 'legacy body',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.is_published is True
        assert post.title == 'Published through legacy form'
        assert post.body == 'legacy body'
        assert post.draft is None


def test_legacy_post_submit_rejects_empty_publish_fields(
        client, application, users):
    login(client, 'author')

    response = client.post(f'/post/{users["post"]}/edit', data={
        'title': '', 'category': '1', 'post': '',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.title == 'Test'
        assert post.body == '<p>safe</p>'
        assert post.draft is None


def test_anonymous_legacy_editor_redirects_to_login_with_next(client, users):
    response = client.get(f'/post/{users["post"]}/edit')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert 'next=' in response.headers['Location']


@pytest.mark.parametrize(('path_key', 'path_template'), [
    ('category', '/category/{id}/edit'),
])
def test_legacy_module_editors_require_admin(
        client, application, users, path_key, path_template):
    records = create_legacy_records(application)
    login(client, 'author')
    path = path_template.format(id=records[path_key])
    assert client.get(path).status_code == 403


@pytest.mark.parametrize(('path_key', 'path_template', 'destination'), [
    ('category', '/category/{id}/edit', '/admin/categories'),
])
def test_legacy_module_editors_redirect_admins(
        client, application, users, path_key, path_template, destination):
    records = create_legacy_records(application)
    login(client, 'admin')
    path = path_template.format(id=records[path_key])
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers['Location'].endswith(destination)


def test_legacy_post_delete_preserves_ownership_and_returns_to_admin(
        client, application, users):
    login(client, 'other')
    assert client.post(f'/post/delete/{users["post"]}').status_code == 403
    client.post('/logout')
    login(client, 'author')

    response = client.post(f'/post/delete/{users["post"]}')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/posts')


@pytest.mark.parametrize(
    ('path_key', 'path_template', 'payload', 'model', 'field', 'expected'), [
        ('category', '/category/{id}/edit', {
            'name': 'Updated category',
        }, Category, 'name', 'Updated category'),
    ])
def test_legacy_module_post_editors_use_admin_validation_and_persistence(
        client, application, users, path_key, path_template, payload, model,
        field, expected):
    records = create_legacy_records(application)
    login(client, 'admin')

    response = client.post(
        path_template.format(id=records[path_key]), data=payload)

    assert response.status_code == 302
    with application.app_context():
        item = db.session.get(model, records[path_key])
        assert getattr(item, field) == expected


@pytest.mark.parametrize(('path_key', 'path_template', 'model'), [
    ('category', '/delete_category/{id}', Category),
])
def test_legacy_module_delete_adapters_commit_and_redirect(
        client, application, users, path_key, path_template, model):
    records = create_legacy_records(application)
    login(client, 'admin')

    response = client.post(path_template.format(id=records[path_key]))

    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(model, records[path_key]) is None
