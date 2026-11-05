import pytest
import sqlalchemy as sa

from app import db
from app.models import Category, Post
from tests.conftest import login


def add_post(users, legacy_id=None, published=True, title='Old'):
    category = db.session.scalar(sa.select(Category))
    post = Post(title=title, body='b', user_id=users['admin'],
                category=category, is_published=published,
                legacy_id=legacy_id)
    db.session.add(post)
    db.session.commit()
    return post.id


def test_old_archive_address_redirects_permanently_to_the_new_post(
        client, application, users):
    with application.app_context():
        post_id = add_post(users, legacy_id=5)
    response = client.get('/archives/5/')
    assert response.status_code == 301
    assert response.headers['Location'].endswith(f'/post/{post_id}')


def test_old_address_without_trailing_slash_still_works(client, application, users):
    with application.app_context():
        post_id = add_post(users, legacy_id=8)
    response = client.get('/archives/8', follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == f'/post/{post_id}'


def test_unknown_old_address_is_not_found(client, users):
    assert client.get('/archives/12345/').status_code == 404


def test_unpublished_posts_are_not_reachable_through_the_old_address(
        client, application, users):
    with application.app_context():
        add_post(users, legacy_id=9, published=False)
    assert client.get('/archives/9/').status_code == 404
    login(client, 'admin')
    assert client.get('/archives/9/').status_code == 404


def test_old_slug_style_addresses_are_not_captured(client, users):
    assert client.get('/archives/csswaf.html').status_code == 404


def test_legacy_ids_are_unique(application, users):
    with application.app_context():
        add_post(users, legacy_id=7)
        with pytest.raises(sa.exc.IntegrityError):
            add_post(users, legacy_id=7, title='Duplicate')
        db.session.rollback()


def test_posts_without_a_legacy_id_can_coexist(application, users):
    with application.app_context():
        add_post(users, title='One')
        add_post(users, title='Two')
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post).where(
            Post.legacy_id.is_(None))) == 3  # the fixture post plus these two
