from http.cookies import SimpleCookie
import re

import pytest
from flask import Response
from itsdangerous import TimestampSigner
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Category, Post, User
from app.post_views import (
    attach_view_cookie, has_recent_view, record_view, view_cookie_name,
)
from tests.conftest import login


def _cookie_from_response(response, post_id):
    jar = SimpleCookie()
    jar.load(response.headers['Set-Cookie'])
    return jar[view_cookie_name(post_id)]


def _view_count(application, post_id):
    with application.app_context():
        return db.session.get(Post, post_id).view_count


@pytest.mark.parametrize('secure', [False, True])
def test_view_cookie_is_signed_scoped_and_accepted(application, secure):
    application.config['SESSION_COOKIE_SECURE'] = secure

    with application.test_request_context('/post/42'):
        response = Response('article')
        attach_view_cookie(response, 42)
        cookie = _cookie_from_response(response, 42)

        assert cookie['max-age'] == '86400'
        assert cookie['path'] == '/post/42'
        assert ('; Secure' in response.headers['Set-Cookie']) is secure
        assert cookie['httponly'] is True
        assert cookie['samesite'] == 'Lax'
        assert has_recent_view(42, cookie.value) is True
        assert has_recent_view(43, cookie.value) is False
        assert has_recent_view(42, f'{cookie.value}tampered') is False


def test_expired_view_cookie_is_rejected(application, monkeypatch):
    with application.test_request_context('/post/42'):
        monkeypatch.setattr(
            TimestampSigner, 'get_timestamp', lambda self: 1_000)
        response = Response('article')
        attach_view_cookie(response, 42)
        marker = _cookie_from_response(response, 42).value

        monkeypatch.setattr(
            TimestampSigner, 'get_timestamp', lambda self: 87_401)
        assert has_recent_view(42, marker) is False


def test_record_view_uses_database_arithmetic(application, users):
    statements = []
    with application.app_context():
        engine = db.engine

        def capture_statement(conn, cursor, statement, parameters, context,
                              executemany):
            statements.append(statement)

        event.listen(engine, 'before_cursor_execute', capture_statement)
        try:
            post = db.session.get(Post, users['post'])
            assert record_view(post) is True
            assert post.view_count == 1
        finally:
            event.remove(engine, 'before_cursor_execute', capture_statement)

    update_sql = next(statement for statement in statements
                      if statement.lstrip().upper().startswith('UPDATE POST'))
    normalized = ' '.join(update_sql.lower().split())
    assert re.search(r'view_count=\(post\.view_count \+ (?:\?|%s|%\([a-zA-Z0-9_]+\)s)\)', normalized)


def test_record_view_rolls_back_and_logs(application, users, monkeypatch):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        rollback_calls = []
        log_calls = []
        monkeypatch.setattr(
            db.session, 'execute',
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError('counter unavailable')))
        monkeypatch.setattr(db.session, 'rollback',
                            lambda: rollback_calls.append(True))
        monkeypatch.setattr(application.logger, 'exception',
                            lambda *args, **kwargs: log_calls.append(args))

        assert record_view(post) is False
        assert rollback_calls == [True]
        assert len(log_calls) == 1


def test_record_view_refresh_failure_rolls_back_increment(
        application, users, monkeypatch):
    with application.app_context():
        post_id = users['post']
        post = db.session.get(Post, post_id)
        monkeypatch.setattr(
            db.session, 'refresh',
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError('refresh unavailable')))

        assert record_view(post) is False

        db.session.expire_all()
        assert db.session.get(Post, post_id).view_count == 0


def test_record_view_logs_captured_post_id_after_rollback(
        application, users, monkeypatch):
    with application.app_context():
        rollback_calls = []
        log_calls = []
        post_id = users['post']

        class PostReference:
            @property
            def id(self):
                if rollback_calls:
                    raise SQLAlchemyError('post unavailable after rollback')
                return post_id

        monkeypatch.setattr(
            db.session, 'execute',
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError('counter unavailable')))
        monkeypatch.setattr(db.session, 'rollback',
                            lambda: rollback_calls.append(True))
        monkeypatch.setattr(application.logger, 'exception',
                            lambda *args, **kwargs: log_calls.append(args))

        assert record_view(PostReference()) is False
        assert log_calls == [(
            'Failed to increment view count for post %s', post_id)]


def test_new_post_defaults_view_count_to_zero(application):
    with application.app_context():
        author = User(username='counter-author', email='counter@example.com')
        category = Category(name='Counter')
        post = Post(title='Counter', body='Body', author=author,
                    category=category)
        db.session.add_all([author, category, post])
        db.session.flush()

        assert post.view_count == 0


def test_first_detail_get_counts_and_refresh_does_not(
        client, application, users):
    first = client.get(f'/post/{users["post"]}')
    second = client.get(f'/post/{users["post"]}')

    assert first.status_code == 200
    assert view_cookie_name(users['post']) in first.headers['Set-Cookie']
    assert second.status_code == 200
    assert 'Set-Cookie' not in second.headers
    assert _view_count(application, users['post']) == 1


def test_invalid_marker_counts_again(client, application, users):
    path = f'/post/{users["post"]}'
    client.set_cookie(
        view_cookie_name(users['post']), 'invalid', path=path)

    response = client.get(path)

    assert response.status_code == 200
    assert view_cookie_name(users['post']) in response.headers['Set-Cookie']
    assert _view_count(application, users['post']) == 1


def test_different_articles_count_independently(client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.get(Category, 1)
        second = Post(title='Second', body='Second', author=author,
                      category=category, is_published=True)
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    client.get(f'/post/{users["post"]}')
    client.get(f'/post/{second_id}')

    assert _view_count(application, users['post']) == 1
    assert _view_count(application, second_id) == 1


@pytest.mark.parametrize('username', ['author', 'admin', 'other'])
def test_authenticated_roles_follow_the_same_rule(
        client, application, users, username):
    login(client, username)

    first = client.get(f'/post/{users["post"]}')
    second = client.get(f'/post/{users["post"]}')

    assert view_cookie_name(users['post']) in first.headers['Set-Cookie']
    assert 'Set-Cookie' not in second.headers
    assert _view_count(application, users['post']) == 1


def test_comment_post_does_not_count(client, application, users):
    response = client.post(f'/post/{users["post"]}', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'body': 'Comment only',
    })

    assert response.status_code == 302
    assert all(
        view_cookie_name(users['post']) not in value
        for value in response.headers.getlist('Set-Cookie')
    )
    assert _view_count(application, users['post']) == 0


@pytest.mark.parametrize('path', ['/', '/categories', '/rss'])
def test_non_detail_surfaces_do_not_count(
        client, application, users, path):
    response = client.get(path, follow_redirects=True)

    assert response.status_code in (200, 404)
    assert _view_count(application, users['post']) == 0


def test_category_detail_does_not_increment_article_view_count(
        client, application, users):
    response = client.get('/category/1')

    assert response.status_code == 200
    assert _view_count(application, users['post']) == 0


def test_search_does_not_increment_article_view_count(
        client, application, users):
    response = client.get('/search?q=safe')

    assert response.status_code == 200
    assert _view_count(application, users['post']) == 0


def test_legacy_post_editor_does_not_increment_article_view_count(
        client, application, users):
    login(client, 'author')

    response = client.get(f'/post/{users["post"]}/edit')

    assert response.status_code == 302
    assert response.headers['Location'].endswith(
        f'/admin/posts/{users["post"]}/edit')
    assert _view_count(application, users['post']) == 0


def test_admin_post_editor_does_not_increment_article_view_count(
        client, application, users):
    login(client, 'author')

    response = client.get(f'/admin/posts/{users["post"]}/edit')

    assert response.status_code == 200
    assert _view_count(application, users['post']) == 0


def test_missing_post_does_not_set_view_cookie(client):
    response = client.get('/post/999999')

    assert response.status_code == 404
    assert 'Set-Cookie' not in response.headers


def test_unpublished_post_does_not_increment_view_count(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = False
        db.session.commit()

    response = client.get(f'/post/{users["post"]}')

    assert response.status_code == 404
    assert 'Set-Cookie' not in response.headers
    assert _view_count(application, users['post']) == 0


def test_counter_update_failure_serves_article_without_marker(
        client, application, users, caplog):
    failed_updates = []
    with application.app_context():
        engine = db.engine

    def fail_counter_update(conn, cursor, statement, parameters, context,
                            executemany):
        if statement.lstrip().upper().startswith('UPDATE POST'):
            failed_updates.append(statement)
            raise SQLAlchemyError('counter unavailable')

    event.listen(engine, 'before_cursor_execute', fail_counter_update)
    caplog.set_level('ERROR', logger=application.logger.name)
    try:
        response = client.get(f'/post/{users["post"]}')
    finally:
        event.remove(engine, 'before_cursor_execute', fail_counter_update)

    assert response.status_code == 200
    assert b'Test' in response.data
    assert 'Set-Cookie' not in response.headers
    assert _view_count(application, users['post']) == 0
    with application.app_context():
        assert db.session.scalar(sa.select(Post.id).where(
            Post.id == users['post'])) == users['post']
    assert len(failed_updates) == 1
    assert any(
        'Failed to increment view count for post' in record.message
        for record in caplog.records
    )
