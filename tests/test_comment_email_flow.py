from app import db
from app.models import PostComment
from tests.conftest import login


def add_comment(**values):
    values.setdefault('name', 'Old')
    values.setdefault('email', 'old@example.com')
    values.setdefault('body', 'earlier')
    comment = PostComment(**values)
    db.session.add(comment)
    db.session.commit()
    return comment.id


def post_comment(client, post_id, **data):
    data.setdefault('name', 'Reader')
    data.setdefault('email', 'reader@example.com')
    data.setdefault('body', 'Nice post')
    return client.post(f'/post/{post_id}', data=data)


def mails_to(outbox, address):
    return [m for m in outbox if m.recipients == [address]]


def comment_id_of(email):
    return db.session.scalar(
        db.select(PostComment.id).where(PostComment.email == email))


def test_first_comment_tells_staff_it_needs_review(client, outbox, users):
    post_comment(client, users['post'])
    assert sorted(m.recipients[0] for m in outbox) == [
        'admin@example.com', 'author@example.com']
    assert all('待审核' in m.subject for m in outbox)


def test_trusted_comment_tells_staff_at_once(client, application, outbox, users):
    with application.app_context():
        add_comment(post_id=users['post'], email='reader@example.com')
    post_comment(client, users['post'])
    assert len(outbox) == 2
    assert all('新评论：Test' in m.subject for m in outbox)


def test_approving_tells_the_commenter_once(client, application, outbox, users):
    post_comment(client, users['post'], notify='y')
    outbox.clear()
    with application.app_context():
        comment_id = comment_id_of('reader@example.com')
    login(client, 'admin')

    client.post(f'/admin/comments/{comment_id}/approve')
    (message,) = outbox
    assert message.recipients == ['reader@example.com']
    assert '通过审核' in message.subject

    client.post(f'/admin/comments/{comment_id}/approve')
    assert len(outbox) == 1


def test_approving_stays_silent_without_the_checkbox(
        client, application, outbox, users):
    post_comment(client, users['post'])
    outbox.clear()
    with application.app_context():
        comment_id = comment_id_of('reader@example.com')
    login(client, 'admin')
    client.post(f'/admin/comments/{comment_id}/approve')
    assert outbox == []


def test_bulk_approve_only_tells_comments_that_changed(
        client, application, outbox, users):
    with application.app_context():
        held = add_comment(post_id=users['post'], status='pending',
                           email='held@example.com', notify_replies=True)
        live = add_comment(post_id=users['post'], status='approved',
                           email='live@example.com', notify_replies=True)
    login(client, 'admin')
    client.post('/admin/comments/bulk',
                data={'action': 'approve', 'ids': [str(held), str(live)]})
    assert [m.recipients for m in outbox] == [['held@example.com']]


def test_admin_reply_tells_the_commenter_and_the_author(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
    login(client, 'admin')
    client.post(f'/admin/comments/{top}/reply', data={'body': 'Thanks!'})

    (to_ann,) = mails_to(outbox, 'ann@example.com')
    assert '回复了你的评论' in to_ann.subject
    assert 'Thanks!' in to_ann.body
    assert mails_to(outbox, 'author@example.com')
    assert mails_to(outbox, 'admin@example.com') == []


def test_published_reply_tells_the_answered_commenter(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
        add_comment(post_id=users['post'], name='Bob',
                    email='bob@example.com')
    post_comment(client, users['post'], name='Bob', email='bob@example.com',
                 body='Agreed', parent_id=top)
    assert len(mails_to(outbox, 'ann@example.com')) == 1


def test_pending_reply_tells_the_answered_commenter_only_once_approved(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
    post_comment(client, users['post'], email='new@example.com', body='hi',
                 parent_id=top, notify='y')
    assert mails_to(outbox, 'ann@example.com') == []
    outbox.clear()

    with application.app_context():
        reply_id = comment_id_of('new@example.com')
    login(client, 'admin')
    client.post(f'/admin/comments/{reply_id}/approve')
    subjects = {m.recipients[0]: m.subject for m in outbox}
    assert '回复了你的评论' in subjects['ann@example.com']
    assert '通过审核' in subjects['new@example.com']


def test_dropped_comment_sends_nothing(client, application, outbox, users):
    post_comment(client, users['post'], website='http://bot.example')
    assert outbox == []
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count(PostComment.id))) == 0


def test_comments_work_when_mail_is_not_configured(
        client, application, outbox, users, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    response = post_comment(client, users['post'])
    assert response.status_code == 302
    assert outbox == []


def test_a_mail_failure_does_not_break_posting(
        client, application, outbox, users, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError('smtp down')

    monkeypatch.setattr('app.comment_mail.send_email', boom)
    response = post_comment(client, users['post'])
    assert response.status_code == 302
    with application.app_context():
        assert comment_id_of('reader@example.com') is not None
