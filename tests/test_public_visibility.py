import pytest

from app import db
from app.models import Post
from tests.conftest import login


@pytest.mark.parametrize('path', [
    '/', '/search?q=private', '/category/1', '/rss',
])
def test_unpublished_posts_are_absent_from_public_collections(
        client, application, users, path):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = False
        post.body = 'private marker'
        db.session.commit()

    response = client.get(path, follow_redirects=True)

    assert response.status_code == 200
    assert 'private marker' not in response.get_data(as_text=True)


def test_category_page_counts_only_published_posts(client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).is_published = False
        db.session.commit()

    response = client.get('/categories')

    assert '<span>0</span>' in response.get_data(as_text=True)


def test_unpublished_detail_and_like_are_not_available(
        client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).is_published = False
        db.session.commit()

    assert client.get('/post/1').status_code == 404
    login(client, 'author')
    assert client.post('/post/1/like').status_code == 404
