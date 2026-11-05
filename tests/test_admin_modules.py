import pytest

from app import db
from app.models import Category, Post, PostComment
from tests.conftest import login


@pytest.mark.parametrize('path', ['/admin/categories', '/admin/comments'])
def test_module_management_requires_admin(client, users, path):
    login(client, 'author')
    assert client.get(path).status_code == 403


def test_category_duplicate_and_in_use_delete_are_rejected(
        client, application, users):
    login(client, 'admin')
    duplicate = client.post('/admin/categories', data={'name': 'General'})
    assert duplicate.status_code == 200
    assert b'already in use' in duplicate.data

    with application.app_context():
        category_id = db.session.scalar(db.select(Category.id).where(
            Category.name == 'General'))
    response = client.post(f'/admin/categories/{category_id}/delete', data={
        'confirm': 'y',
    })
    assert response.status_code == 400


def test_admin_can_delete_article_comments(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        article = PostComment(
            post=post, name='Reader', email='reader@example.com', body='Hello')
        db.session.add(article)
        db.session.commit()
        article_id = article.id
    login(client, 'admin')

    assert client.post(
        f'/admin/comments/posts/{article_id}/delete',
        data={'confirm': 'y'}).status_code == 302
    with application.app_context():
        assert db.session.get(PostComment, article_id) is None


def test_public_categories_page_has_no_management_actions(client, users):
    login(client, 'admin')
    response = client.get('/categories')
    assert response.status_code == 200
    assert '/delete_category/' not in response.get_data(as_text=True)


@pytest.mark.parametrize('path', [
    '/admin/posts/new',
    '/admin/pages/new',
    '/admin/pages/999/delete',
    '/admin/categories',
    '/admin/users/new',
    '/admin/users/999/edit',
    '/admin/users/999/delete',
    '/admin/pages/999/publish',
    '/admin/pages/999/nav',
])
def test_admin_mutation_groups_reject_missing_csrf(
        client, application, users, monkeypatch, path):
    login(client, 'admin')
    monkeypatch.setitem(application.config, 'WTF_CSRF_ENABLED', True)
    assert client.post(path).status_code == 400
