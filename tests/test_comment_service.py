import pytest

from app import db
from app.comments import (APPROVED, DROPPED, PENDING, CommentRejected,
                          CommentsClosed, approved_threads, count_links,
                          find_reply_target, make_form_token, submit_comment)
from app.models import Page, Post, PostComment, User


def request_context(application, address='10.0.0.1'):
    return application.test_request_context(
        '/', environ_base={'REMOTE_ADDR': address})


def make_comment(post_id, **values):
    values.setdefault('name', 'A')
    values.setdefault('email', 'a@example.com')
    values.setdefault('body', 'hello')
    comment = PostComment(post_id=post_id, **values)
    db.session.add(comment)
    db.session.commit()
    return comment


def send(post, **values):
    values.setdefault('name', 'Reader')
    values.setdefault('email', 'reader@example.com')
    values.setdefault('body', 'A fine post')
    return submit_comment(post, **values)


def test_count_links_counts_urls_and_www():
    assert count_links('no links') == 0
    assert count_links('http://a.com https://b.com www.c.com') == 3
    assert count_links('[x](https://a.com)') == 1


def test_first_comment_from_an_email_waits_for_review(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        result = send(post)
        assert result.outcome == PENDING
        assert result.comment.status == PENDING
        assert result.comment.post_id == post.id
        assert result.comment.email == 'reader@example.com'
        assert result.comment.ip_hash and len(result.comment.ip_hash) == 64


def test_email_with_an_approved_comment_is_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com')
        result = send(post, email='Reader@Example.com')
        assert result.outcome == APPROVED


def test_pending_comment_does_not_make_an_email_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com', status=PENDING)
        assert send(post).outcome == PENDING


def test_many_links_wait_even_for_a_trusted_email(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com')
        two = send(post, body='http://a.com http://b.com')
        assert two.outcome == APPROVED
        three = send(post, body='http://a.com http://b.com http://c.com')
        assert three.outcome == PENDING


def test_site_owner_is_approved_and_recorded(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        result = send(post, author=admin, name='admin',
                      email='admin@example.com',
                      body='http://a.com http://b.com http://c.com')
        assert result.outcome == APPROVED
        assert result.comment.user_id == admin.id


def test_a_site_owners_address_does_not_make_others_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        send(post, author=admin, name='admin', email='admin@example.com')
        guest = send(post, email='admin@example.com', body='A different thought')
        assert guest.outcome == PENDING


def test_non_admin_signed_in_user_is_a_guest(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        author = db.session.get(User, users['author'])
        result = send(post, author=author, email='author@example.com')
        assert result.outcome == PENDING
        assert result.comment.user_id is None


def test_closed_comments_refuse_everyone(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        post.comments_enabled = False
        admin = db.session.get(User, users['admin'])
        with pytest.raises(CommentsClosed):
            send(post)
        with pytest.raises(CommentsClosed):
            send(post, author=admin)


def test_honeypot_is_dropped_without_a_row(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        result = send(post, honeypot='http://spam.example')
        assert result.outcome == DROPPED and result.comment is None
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_form_filled_too_fast_or_without_token_is_dropped(application, users):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        assert send(post, form_token='').outcome == DROPPED
        assert send(post, form_token='garbage').outcome == DROPPED
        assert send(post, form_token=make_form_token()).outcome == DROPPED


def test_form_filled_slowly_enough_is_accepted(application, users, monkeypatch):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        token = make_form_token()
        import app.comments as comments
        real = comments.time.time
        monkeypatch.setattr(comments.time, 'time', lambda: real() + 10)
        post = db.session.get(Post, users['post'])
        assert send(post, form_token=token).outcome == PENDING


def test_site_owner_skips_the_bot_checks(application, users):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        assert send(post, author=admin, form_token='').outcome == APPROVED


def test_per_minute_limit_per_address(application, users):
    application.config['COMMENTS_PER_MINUTE_PER_IP'] = 2
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='one')
        send(post, body='two')
        with pytest.raises(CommentRejected):
            send(post, body='three')
    with application.app_context(), request_context(application, '10.0.0.2'):
        post = db.session.get(Post, users['post'])
        assert send(post, body='four').outcome == PENDING


def test_per_hour_limit_per_address(application, users):
    application.config['COMMENTS_PER_MINUTE_PER_IP'] = 100
    application.config['COMMENTS_PER_HOUR_PER_IP'] = 2
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='one')
        send(post, body='two')
        with pytest.raises(CommentRejected):
            send(post, body='three')


def test_identical_body_from_the_same_address_is_refused(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='Buy now')
        with pytest.raises(CommentRejected):
            send(post, body='  Buy now ')


def test_reply_attaches_to_the_comment(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        top = make_comment(post.id, email='reader@example.com')
        result = send(post, parent_id=top.id)
        assert result.comment.parent_id == top.id
        assert result.comment.body == 'A fine post'


def test_reply_to_a_reply_joins_the_top_comment_with_a_mention(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        top = make_comment(post.id, email='reader@example.com')
        reply = make_comment(post.id, parent_id=top.id, name='Bob',
                             email='bob@example.com')
        result = send(post, parent_id=reply.id)
        assert result.comment.parent_id == top.id
        assert result.comment.body == '@Bob A fine post'


def test_reply_to_a_missing_pending_or_foreign_comment_is_refused(
        application, users):
    application.config['COMMENTS_PER_MINUTE_PER_IP'] = 100
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        other = Post(title='Other', body='x', author=db.session.get(
            User, users['author']), is_published=True)
        db.session.add(other)
        db.session.commit()
        waiting = make_comment(post.id, status=PENDING)
        foreign = make_comment(other.id)
        for parent_id in (9999, waiting.id, foreign.id):
            with pytest.raises(CommentRejected):
                send(post, parent_id=parent_id, body=f'body {parent_id}')


def test_comment_on_a_page(application, users):
    with application.app_context(), request_context(application):
        page = Page(title='About', slug='about', kind='content',
                    is_published=True, comments_enabled=True)
        db.session.add(page)
        db.session.commit()
        result = send(page)
        assert result.comment.page_id == page.id
        assert result.comment.post_id is None
        page.comments_enabled = False
        with pytest.raises(CommentsClosed):
            send(page, body='again')


def test_threads_list_only_approved_comments_with_their_replies(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        first = make_comment(post.id, body='first')
        make_comment(post.id, body='hidden', status=PENDING)
        reply = make_comment(post.id, parent_id=first.id, body='reply')
        make_comment(post.id, parent_id=first.id, body='hidden reply',
                     status=PENDING)
        second = make_comment(post.id, body='second')

        threads, count = approved_threads(post)
        assert [t.comment.id for t in threads] == [first.id, second.id]
        assert [r.id for r in threads[0].replies] == [reply.id]
        assert threads[1].replies == []
        assert count == 3


def test_find_reply_target_only_returns_approved_comments_of_the_target(
        application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        ok = make_comment(post.id)
        waiting = make_comment(post.id, status=PENDING)
        assert find_reply_target(post, ok.id) == ok
        assert find_reply_target(post, waiting.id) is None
        assert find_reply_target(post, 9999) is None
