from app import db
from app.models import Post, PostComment, PostLike, User
from tests.conftest import login


def test_guest_can_comment_without_exposing_email(client, application, users):
    response = client.post(f'/post/{users["post"]}', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'body': '<script>alert(1)</script>Hello',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Reader' in response.data
    assert b'Hello' in response.data
    assert b'reader@example.com' not in response.data
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;Hello' in response.data
    with application.app_context():
        comment = db.session.scalar(db.select(PostComment))
        assert comment.post_id == users['post']


def test_like_can_be_toggled_without_duplicates(client, application, users):
    login(client, 'other')

    first = client.post(f'/post/{users["post"]}/like')
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostLike)) == 1

    second = client.post(f'/post/{users["post"]}/like')
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostLike)) == 0

    assert first.status_code == 302
    assert second.status_code == 302


def test_unpublished_post_rejects_comments_without_creating_them(
        client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).is_published = False
        db.session.commit()

    response = client.post(f'/post/{users["post"]}', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'body': 'Private comment',
    })

    assert response.status_code == 404
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_deleting_post_removes_comments_and_likes(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        user = db.session.get(User, users['other'])
        db.session.add(PostComment(
            post=post, name='Reader', email='reader@example.com', body='Hi'))
        db.session.add(PostLike(post=post, user=user))
        db.session.commit()

    login(client, 'author')
    response = client.post(f'/post/delete/{users["post"]}')

    assert response.status_code == 302
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostLike)) == 0


def test_like_returns_json_for_fetch_requests(client, application, users):
    login(client, 'other')
    url = f'/post/{users["post"]}/like'

    first = client.post(url, headers={'Accept': 'application/json'})
    second = client.post(url, headers={'Accept': 'application/json'})

    assert first.status_code == 200
    assert first.get_json() == {'liked': True, 'count': 1}
    assert second.get_json() == {'liked': False, 'count': 0}


def test_article_like_form_is_enhanced_by_script(client, users):
    login(client, 'other')
    html = client.get(f'/post/{users["post"]}').get_data(as_text=True)

    assert 'data-like-form' in html
    assert 'data-like-label' in html
    assert 'static/like-button.js' in html
