import sqlalchemy as sa
from lxml import html as lxml_html

from app import db
from app.models import Post, PostLike, User, get_site_settings
from tests.conftest import login


def user_id(application, username):
    with application.app_context():
        return db.session.scalar(
            sa.select(User.id).where(User.username == username))


def test_list_search_and_role_filter(client, users):
    login(client, 'admin')
    by_name = client.get('/admin/users?q=AUTH').get_data(as_text=True)
    assert 'author@example.com' in by_name and 'other@example.com' not in by_name

    by_email = client.get('/admin/users?q=other@').get_data(as_text=True)
    assert 'other@example.com' in by_email and 'author@example.com' not in by_email

    admins = client.get('/admin/users?role=admin').get_data(as_text=True)
    assert 'admin@example.com' in admins and 'author@example.com' not in admins
    plain = client.get('/admin/users?role=user').get_data(as_text=True)
    assert 'author@example.com' in plain and 'admin@example.com' not in plain
    assert client.get('/admin/users?role=owner').status_code == 400


def test_list_rows_link_to_edit(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/users').get_data(as_text=True))
    author = user_id(application, 'author')
    assert page.xpath(f'//a[@href="/admin/users/{author}/edit"]')
    assert page.xpath('//a[@href="/admin/users/new"]')
    assert not page.xpath('//select[@name="role"]')  # role is edited on the form page


def test_create_user(client, application, users):
    login(client, 'admin')
    response = client.post('/admin/users/new', data={
        'username': 'newbie', 'email': 'newbie@example.com',
        'password': 'secret-pass', 'role': 'user'})
    assert response.status_code == 302
    with application.app_context():
        created = db.session.scalar(sa.select(User).where(
            User.username == 'newbie'))
        assert created.role == 'user'
        assert created.check_password('secret-pass')
        assert created.password_hash != 'secret-pass'


def test_create_user_works_while_registration_is_closed(
        client, application, users):
    with application.app_context():
        get_site_settings().registration_open = False
        db.session.commit()
    login(client, 'admin')
    assert client.post('/admin/users/new', data={
        'username': 'closed', 'email': 'closed@example.com',
        'password': 'x', 'role': 'admin'}).status_code == 302
    with application.app_context():
        assert db.session.scalar(sa.select(User.role).where(
            User.username == 'closed')) == 'admin'


def test_create_user_rejects_duplicates_and_bad_input(client, application, users):
    login(client, 'admin')
    base = {'username': 'fresh', 'email': 'fresh@example.com',
            'password': 'pw', 'role': 'user'}
    for override in ({'username': 'author'}, {'email': 'author@example.com'},
                     {'email': 'not-an-email'}, {'password': ''},
                     {'role': 'owner'}, {'username': ''}):
        response = client.post('/admin/users/new', data={**base, **override})
        assert response.status_code == 200, override
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            User)) == 3


def test_edit_user_fields_and_blank_password_keeps_hash(
        client, application, users):
    author = users['author']
    with application.app_context():
        old_hash = db.session.get(User, author).password_hash
    login(client, 'admin')
    response = client.post(f'/admin/users/{author}/edit', data={
        'username': 'writer', 'email': 'writer@example.com',
        'role': 'user', 'password': ''})
    assert response.status_code == 302
    with application.app_context():
        edited = db.session.get(User, author)
        assert (edited.username, edited.email) == ('writer', 'writer@example.com')
        assert edited.password_hash == old_hash


def test_edit_user_sets_new_password_and_role(client, application, users):
    author = users['author']
    login(client, 'admin')
    client.post(f'/admin/users/{author}/edit', data={
        'username': 'author', 'email': 'author@example.com',
        'role': 'admin', 'password': 'brand-new'})
    with application.app_context():
        edited = db.session.get(User, author)
        assert edited.role == 'admin'
        assert edited.check_password('brand-new')


def test_edit_user_uniqueness_ignores_self_but_not_others(
        client, application, users):
    author = users['author']
    login(client, 'admin')
    same = client.post(f'/admin/users/{author}/edit', data={
        'username': 'author', 'email': 'author@example.com', 'role': 'user'})
    assert same.status_code == 302
    clash = client.post(f'/admin/users/{author}/edit', data={
        'username': 'other', 'email': 'author@example.com', 'role': 'user'})
    assert clash.status_code == 200
    with application.app_context():
        assert db.session.get(User, author).username == 'author'


def test_editing_yourself_never_changes_your_role(
        client, application, role_users):
    login(client, 'role-admin')
    admin_id = role_users['admin']
    response = client.post(f'/admin/users/{admin_id}/edit', data={
        'username': 'role-admin-renamed', 'email': 'role-admin@example.com',
        'role': 'user'})
    assert response.status_code == 302
    with application.app_context():
        edited = db.session.get(User, admin_id)
        assert edited.role == 'admin'
        assert edited.username == 'role-admin-renamed'


def test_edit_form_disables_own_role_select(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        f'/admin/users/{users["admin"]}/edit').get_data(as_text=True))
    assert page.xpath('//select[@name="role"][@disabled]')
    other = lxml_html.fromstring(client.get(
        f'/admin/users/{users["author"]}/edit').get_data(as_text=True))
    assert not other.xpath('//select[@name="role"][@disabled]')


def test_user_routes_require_admin(client, users):
    paths = (('get', '/admin/users/new'), ('post', '/admin/users/new'),
             ('get', f'/admin/users/{users["author"]}/edit'),
             ('post', f'/admin/users/{users["author"]}/edit'))
    for method, path in paths:
        assert getattr(client, method)(path).status_code == 302
    login(client, 'author')
    for method, path in paths:
        assert getattr(client, method)(path).status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get('/admin/users/9999/edit').status_code == 404


def test_list_links_to_delete_except_for_yourself(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/users').get_data(as_text=True))
    assert page.xpath(f'//a[@href="/admin/users/{users["author"]}/delete"]')
    assert not page.xpath(f'//a[@href="/admin/users/{users["admin"]}/delete"]')


def test_delete_confirmation_shows_post_count_and_receivers(
        client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        f'/admin/users/{users["author"]}/delete').get_data(as_text=True))
    assert '1' in page.text_content()
    options = page.xpath('//select[@name="receiver"]/option')
    values = {o.get('value') for o in options}
    assert str(users['author']) not in values
    assert {str(users['admin']), str(users['other'])} <= values
    selected = page.xpath('//select[@name="receiver"]/option[@selected]/@value')
    assert selected == [str(users['admin'])]


def test_delete_user_transfers_articles_and_removes_account(
        client, application, users):
    login(client, 'admin')
    response = client.post(f'/admin/users/{users["author"]}/delete', data={
        'receiver': str(users['other'])})
    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(User, users['author']) is None
        assert db.session.get(Post, users['post']).user_id == users['other']


def test_delete_user_without_posts_needs_no_receiver(client, application, users):
    login(client, 'admin')
    response = client.post(f'/admin/users/{users["other"]}/delete', data={})
    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(User, users['other']) is None


def test_delete_user_removes_their_likes_but_keeps_others(
        client, application, users):
    with application.app_context():
        db.session.add_all([
            PostLike(post_id=users['post'], user_id=users['author']),
            PostLike(post_id=users['post'], user_id=users['other'])])
        db.session.commit()
    login(client, 'admin')
    client.post(f'/admin/users/{users["author"]}/delete', data={
        'receiver': str(users['admin'])})
    with application.app_context():
        remaining = db.session.scalars(sa.select(PostLike.user_id)).all()
        assert remaining == [users['other']]


def test_delete_user_rejects_bad_receivers(client, application, users):
    login(client, 'admin')
    url = f'/admin/users/{users["author"]}/delete'
    for data in ({}, {'receiver': str(users['author'])},
                 {'receiver': '9999'}, {'receiver': 'abc'}):
        response = client.post(url, data=data)
        assert response.status_code == 200, data
    with application.app_context():
        assert db.session.get(User, users['author']) is not None
        assert db.session.get(Post, users['post']).user_id == users['author']


def test_cannot_delete_yourself(client, application, users):
    login(client, 'admin')
    assert client.get(f'/admin/users/{users["admin"]}/delete').status_code == 400
    assert client.post(f'/admin/users/{users["admin"]}/delete',
                       data={'receiver': str(users['other'])}).status_code == 400
    with application.app_context():
        assert db.session.get(User, users['admin']) is not None


def test_delete_user_requires_admin_and_existing_user(client, users):
    url = f'/admin/users/{users["other"]}/delete'
    assert client.post(url).status_code == 302
    login(client, 'author')
    assert client.get(url).status_code == 403
    assert client.post(url).status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get('/admin/users/9999/delete').status_code == 404
    assert client.post('/admin/users/9999/delete').status_code == 404


def test_delete_user_rejects_missing_csrf(client, application, users):
    login(client, 'admin')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post(f'/admin/users/{users["other"]}/delete')
        assert response.status_code == 400
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        assert db.session.get(User, users['other']) is not None
