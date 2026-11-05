from tests.conftest import login
import pytest
import sqlalchemy as sa

from app import db
from app.models import PostRevision, get_site_settings


def test_anonymous_admin_redirects_to_login(client):
    response = client.get('/admin')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert 'next=' in response.headers['Location']


def test_member_sees_only_member_admin_navigation(client, users):
    login(client, 'author')
    html = client.get('/admin').get_data(as_text=True)
    assert 'Aisaka 管理' in html
    assert '我的文章' in html
    assert '新建文章' in html
    assert '用户与角色' not in html


def test_admin_sees_complete_admin_navigation(client, users):
    login(client, 'admin')
    html = client.get('/admin').get_data(as_text=True)
    assert '页面管理' in html
    assert '模块数据' not in html
    assert '用户与角色' in html
    assert '网站设置' in html


def test_only_administrator_can_change_site_settings(client, users):
    login(client, 'author')
    assert client.get('/admin/settings').status_code == 403
    client.post('/logout')
    login(client, 'admin')

    response = client.post('/admin/settings', data={
        'registration_open': '', 'post_revision_limit': '7'})

    assert response.status_code == 302
    with client.application.app_context():
        settings = get_site_settings()
        assert settings.registration_open is False
        assert settings.post_revision_limit == 7


@pytest.mark.parametrize('limit', ['0', '101'])
def test_settings_rejects_revision_limits_outside_allowed_range(
        client, application, users, limit):
    login(client, 'admin')

    response = client.post('/admin/settings', data={
        'registration_open': 'y', 'post_revision_limit': limit})

    assert response.status_code == 200
    with application.app_context():
        assert get_site_settings().post_revision_limit == 20


def test_settings_trim_revisions_immediately_when_limit_is_reduced(
        client, application, users):
    with application.app_context():
        db.session.add_all([
            PostRevision(post_id=users['post'], title='one', body='one'),
            PostRevision(post_id=users['post'], title='two', body='two'),
            PostRevision(post_id=users['post'], title='three', body='three'),
        ])
        db.session.commit()

    login(client, 'admin')
    response = client.post('/admin/settings', data={
        'registration_open': 'y', 'post_revision_limit': '1'})

    assert response.status_code == 302
    with application.app_context():
        revisions = db.session.scalars(
            sa.select(PostRevision).where(PostRevision.post_id == users['post'])
        ).all()
        assert [revision.body for revision in revisions] == ['three']


@pytest.mark.parametrize('method, path', [
    ('post', '/admin/posts/draft'),
    ('post', '/admin/posts/draft/leave'),
    ('put', '/admin/posts/1/draft'),
    ('post', '/admin/posts/1/leave'),
    ('post', '/admin/posts/1/publish'),
    ('post', '/admin/posts/1/unpublish'),
    ('post', '/admin/posts/1/discard-draft'),
    ('post', '/admin/posts/1/revisions/1/restore'),
])
def test_post_draft_mutations_reject_missing_csrf(
        client, application, users, monkeypatch, method, path):
    login(client, 'author')
    monkeypatch.setitem(application.config, 'WTF_CSRF_ENABLED', True)

    response = getattr(client, method)(path, json={
        'title': '', 'body': '', 'category_id': 1,
    })

    assert response.status_code == 400


@pytest.mark.parametrize('path', [
    '/admin', '/admin/posts', '/admin/posts/new', '/admin/pages',
    '/admin/categories', '/admin/comments', '/admin/users', '/admin/settings',
])
def test_anonymous_admin_get_matrix_redirects_to_login_with_return_address(
        client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert 'next=' in response.headers['Location']


@pytest.mark.parametrize('path', [
    '/admin/pages', '/admin/categories', '/admin/comments', '/admin/users', '/admin/settings',
])
def test_member_admin_module_matrix_returns_403(client, users, path):
    login(client, 'author')
    assert client.get(path).status_code == 403


@pytest.mark.parametrize('path', [
    '/admin', '/admin/posts', '/admin/posts/new', '/admin/pages',
    '/admin/categories', '/admin/comments', '/admin/users', '/admin/settings',
])
def test_admin_get_matrix_is_accessible(client, users, path):
    login(client, 'admin')
    assert client.get(path).status_code == 200
