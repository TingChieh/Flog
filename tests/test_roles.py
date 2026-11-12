import sqlalchemy as sa
import pytest
from werkzeug.exceptions import Forbidden

from app import db
from app.authorization import (
    RoleChangeError,
    change_user_role,
    delete_user,
    owned_post_or_404,
)
from app.models import Category, Image, Post, PostLike, User, get_site_settings
from tests.conftest import login


def test_role_is_database_authoritative(application, monkeypatch):
    with application.app_context():
        user = User(username='stored-admin', email='not-configured@example.com',
                    role='admin')
        db.session.add(user)
        db.session.commit()
        monkeypatch.setitem(application.config, 'ADMIN_EMAILS', [])

        assert user.is_admin is True


def test_new_user_defaults_to_user_role(application):
    with application.app_context():
        user = User(username='member', email='member@example.com')
        db.session.add(user)
        db.session.commit()

        assert user.role == 'user'


def test_registration_defaults_to_user_role(client, application):
    with application.app_context():
        get_site_settings().registration_open = True
        db.session.commit()
    response = client.post('/register', data={
        'username': 'registered-member',
        'email': 'registered-member@example.com',
        'password': 'password',
        'password2': 'password',
    })

    assert response.status_code == 302
    with application.app_context():
        user = db.session.scalar(sa.select(User).where(
            User.username == 'registered-member'))
        assert user.role == 'user'


def test_closed_registration_rejects_a_valid_submission(client, application):
    response = client.post('/register', data={
        'username': 'blocked',
        'email': 'blocked@example.com',
        'password': 'password',
        'password2': 'password',
    })

    assert response.status_code == 403
    with application.app_context():
        assert db.session.scalar(sa.select(User).where(
            User.username == 'blocked')) is None


def test_admin_can_promote_and_demote_another_user(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])

        change_user_role(admin, member, 'admin')
        assert member.role == 'admin'
        change_user_role(admin, member, 'user')
        assert member.role == 'user'


def test_non_admin_cannot_change_roles(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])

        with pytest.raises(RoleChangeError, match='Administrator access'):
            change_user_role(member, admin, 'user')


def test_unknown_role_is_rejected(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])

        with pytest.raises(RoleChangeError, match='Unknown role'):
            change_user_role(admin, member, 'owner')


def test_admin_cannot_demote_self_when_another_admin_exists(application,
                                                            role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        second_admin = db.session.get(User, role_users['member'])
        second_admin.role = 'admin'
        db.session.commit()

        with pytest.raises(RoleChangeError, match='own administrator role'):
            change_user_role(admin, admin, 'user')


def test_final_admin_cannot_be_demoted(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])

        with pytest.raises(RoleChangeError, match='final administrator'):
            change_user_role(admin, admin, 'user')


def test_member_can_access_only_their_own_post(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        category = Category(name='Authorization')
        post = Post(title='Private', body='content', author=admin,
                    category=category)
        db.session.add_all([category, post])
        db.session.commit()

        with pytest.raises(Forbidden):
            owned_post_or_404(post.id, member)


def test_admin_can_access_any_post(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        category = Category(name='Administrator')
        post = Post(title='Member post', body='content', author=member,
                    category=category)
        db.session.add_all([category, post])
        db.session.commit()

        assert owned_post_or_404(post.id, admin) == post


def test_user_management_requires_admin_and_lists_post_counts(
        client, users):
    login(client, 'author')
    assert client.get('/admin/users').status_code == 403
    client.post('/logout')
    login(client, 'admin')

    response = client.get('/admin/users')

    assert response.status_code == 200
    assert b'author@example.com' in response.data
    assert b'>1<' in response.data


def post_role(client, application, user_id, role):
    with application.app_context():
        target = db.session.get(User, user_id)
        data = {'username': target.username, 'email': target.email,
                'role': role}
    return client.post(f'/admin/users/{user_id}/edit', data=data)


def test_admin_can_promote_and_demote_another_user_through_route(
        client, application, role_users):
    login(client, 'role-admin')
    member_id = role_users['member']

    assert post_role(client, application, member_id, 'admin').status_code == 302
    with application.app_context():
        assert db.session.get(User, member_id).role == 'admin'

    assert post_role(client, application, member_id, 'user').status_code == 302
    with application.app_context():
        assert db.session.get(User, member_id).role == 'user'


def test_non_admin_role_change_returns_403(client, application, role_users):
    login(client, 'role-member')
    response = post_role(client, application, role_users['admin'], 'user')
    assert response.status_code == 403


def test_invalid_role_does_not_change_user(
        client, application, role_users):
    login(client, 'role-admin')
    response = post_role(client, application, role_users['member'], 'owner')

    assert response.status_code == 200
    with application.app_context():
        assert db.session.get(User, role_users['member']).role == 'user'


def test_role_change_for_missing_user_returns_404(client, role_users):
    login(client, 'role-admin')
    assert client.get('/admin/users/9999/edit').status_code == 404


def make_post(author, title='T'):
    category = db.session.scalar(sa.select(Category)) or Category(name='C')
    post = Post(title=title, body='b', author=author, category=category)
    db.session.add_all([category, post])
    db.session.commit()
    return post


def test_delete_user_transfers_posts_and_removes_likes(
        application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        mine = make_post(member, 'mine')
        theirs = make_post(admin, 'theirs')
        db.session.add_all([PostLike(post_id=theirs.id, user_id=member.id),
                            PostLike(post_id=mine.id, user_id=admin.id)])
        db.session.commit()
        mine_id, member_id, admin_id = mine.id, member.id, admin.id

        delete_user(admin, member, admin)
        db.session.commit()

        assert db.session.get(User, member_id) is None
        assert db.session.get(Post, mine_id).user_id == admin_id
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostLike).where(PostLike.user_id == member_id)) == 0
        # The like the admin gave to the transferred post stays.
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostLike)) == 1


def test_delete_user_without_posts_needs_no_receiver(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        member_id = member.id
        delete_user(admin, member, None)
        db.session.commit()
        assert db.session.get(User, member_id) is None


def test_delete_user_with_posts_requires_a_receiver(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        make_post(member)
        with pytest.raises(RoleChangeError, match='receive'):
            delete_user(admin, member, None)
        with pytest.raises(RoleChangeError, match='receive'):
            delete_user(admin, member, member)


def test_delete_user_guards(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        with pytest.raises(RoleChangeError, match='Administrator access'):
            delete_user(member, admin, member)
        with pytest.raises(RoleChangeError, match='yourself'):
            delete_user(admin, admin, member)

        # Another administrator can be deleted by an administrator.
        member.role = 'admin'
        db.session.commit()
        delete_user(admin, member, None)
        db.session.commit()


def add_image_for(user, name):
    image = Image(filename=f'{name * 32}.png', original_name='a.png',
                  title=name, size=1, user_id=user.id)
    db.session.add(image)
    db.session.commit()
    return image


def test_delete_user_hands_images_to_the_receiver(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        make_post(member)
        image = add_image_for(member, 'a')
        image_id = image.id

        delete_user(admin, member, admin)
        db.session.commit()

        assert db.session.get(Image, image_id).user_id == admin.id


def test_delete_user_without_receiver_leaves_images_ownerless(
        application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        image_id = add_image_for(member, 'b').id

        delete_user(admin, member, None)
        db.session.commit()

        assert db.session.get(Image, image_id).user_id is None
