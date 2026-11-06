import pytest
from sqlalchemy.exc import DBAPIError

from app import db
from app.models import Page, Post, PostComment


def make_page(**values):
    page = Page(title='About', slug='about', kind='content',
                is_published=True, **values)
    db.session.add(page)
    db.session.commit()
    return page


def test_comment_can_belong_to_a_page(application, users):
    with application.app_context():
        page = make_page()
        comment = PostComment(
            page=page, name='R', email='r@example.com', body='Hi')
        db.session.add(comment)
        db.session.commit()

        assert comment.post_id is None
        assert comment.page_id == page.id
        assert comment.status == 'approved'
        assert page.comments == [comment]


# MySQL reports a violated CHECK as an OperationalError, SQLite as an IntegrityError.
def test_comment_needs_exactly_one_target(application, users):
    with application.app_context():
        page = make_page()
        db.session.add(PostComment(name='R', email='r@example.com', body='Hi'))
        with pytest.raises(DBAPIError):
            db.session.commit()
        db.session.rollback()

        db.session.add(PostComment(
            post_id=users['post'], page_id=page.id,
            name='R', email='r@example.com', body='Hi'))
        with pytest.raises(DBAPIError):
            db.session.commit()


def test_status_rejects_unknown_values(application, users):
    with application.app_context():
        db.session.add(PostComment(
            post_id=users['post'], name='R', email='r@example.com',
            body='Hi', status='spam'))
        with pytest.raises(DBAPIError):
            db.session.commit()


def test_replies_are_deleted_with_their_parent(application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        top = PostComment(post=post, name='A', email='a@example.com', body='top')
        reply = PostComment(
            post=post, parent=top, name='B', email='b@example.com', body='re')
        db.session.add_all([top, reply])
        db.session.commit()
        assert top.replies == [reply]

        db.session.delete(top)
        db.session.commit()
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_deleting_a_page_removes_its_comments(application, users):
    with application.app_context():
        page = make_page()
        db.session.add(PostComment(
            page=page, name='R', email='r@example.com', body='Hi'))
        db.session.commit()

        db.session.delete(page)
        db.session.commit()
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_comments_are_open_on_posts_and_closed_on_pages_by_default(
        application, users):
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True
        assert make_page().comments_enabled is False
