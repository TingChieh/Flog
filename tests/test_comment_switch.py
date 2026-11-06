from app import db
from app.models import Page, Post
from tests.conftest import login


def page_form(**overrides):
    data = {'title': 'About', 'slug': 'about', 'summary': '', 'body': 'hello',
            'is_published': 'y', 'nav_order': '0', 'submit': '保存'}
    data.update(overrides)
    return data


def test_post_author_can_switch_comments_off_and_on(client, application, users):
    login(client, 'author')
    url = f'/admin/posts/{users["post"]}/comments'

    assert client.post(url).status_code == 302
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is False

    assert client.post(url).status_code == 302
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True


def test_switch_returns_to_the_list_when_asked(client, users):
    login(client, 'author')
    response = client.post(
        f'/admin/posts/{users["post"]}/comments', data={'next': 'list'})
    assert response.headers['Location'].endswith('/admin/posts')


def test_other_members_cannot_switch_someone_elses_post(client, application, users):
    login(client, 'other')
    assert client.post(f'/admin/posts/{users["post"]}/comments').status_code in (403, 404)
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True


def test_switch_needs_a_signed_in_user(client, users):
    response = client.post(f'/admin/posts/{users["post"]}/comments')
    assert response.status_code in (302, 401)
    assert '/login' in response.headers.get('Location', '/login')


def test_post_list_and_editor_show_the_current_state(client, users):
    login(client, 'author')
    listing = client.get('/admin/posts').get_data(as_text=True)
    editor = client.get(f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)
    for html in (listing, editor):
        assert 'data-comments-toggle' in html
        assert '关闭评论' in html

    client.post(f'/admin/posts/{users["post"]}/comments')
    assert '开启评论' in client.get('/admin/posts').get_data(as_text=True)


def test_new_page_defaults_to_comments_off_and_can_turn_them_on(client, application, users):
    login(client, 'admin')
    form = client.get('/admin/pages/new').get_data(as_text=True)
    assert 'name="comments_enabled"' in form
    assert 'name="comments_enabled" type="checkbox" value="y" checked' not in form

    client.post('/admin/pages/new', data=page_form())
    with application.app_context():
        page = db.session.scalar(db.select(Page).where(Page.slug == 'about'))
        assert page.comments_enabled is False
        page_id = page.id

    client.post(f'/admin/pages/{page_id}/edit', data=page_form(comments_enabled='y'))
    with application.app_context():
        assert db.session.get(Page, page_id).comments_enabled is True

    client.post(f'/admin/pages/{page_id}/edit', data=page_form())
    with application.app_context():
        assert db.session.get(Page, page_id).comments_enabled is False
