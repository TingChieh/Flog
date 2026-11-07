import re

from app import db
from app.comment_mail import (notify_comment_pending, notify_comment_published,
                              notify_comments_approved)
from app.models import Page, PostComment


def add_comment(**values):
    values.setdefault('name', 'Reader')
    values.setdefault('email', 'reader@example.com')
    values.setdefault('body', 'A fine post')
    comment = PostComment(**values)
    db.session.add(comment)
    db.session.commit()
    return comment


def reply_to(top, **values):
    return add_comment(post_id=top.post_id, page_id=top.page_id,
                       parent_id=top.id, answered_id=top.id, **values)


def mails_to(outbox, address):
    return [m for m in outbox if m.recipients == [address]]


def unsubscribe_link(message):
    return re.search(r'https?://\S+/comments/unsubscribe/\S+',
                     message.body).group(0)


# --- new comment -> site owner and post author ---------------------------

def test_published_comment_goes_to_owner_and_author_separately(
        application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'], body='Great read')
        notify_comment_published(comment)
    assert sorted(m.recipients[0] for m in outbox) == [
        'admin@example.com', 'author@example.com']
    assert all(len(m.recipients) == 1 for m in outbox)
    message = outbox[0]
    assert message.subject == "[Aisaka's Blog] 新评论：Test"
    assert 'Reader' in message.body and 'Great read' in message.body
    assert f'/post/{users["post"]}#comment-{comment.id}' in message.body
    assert 'unsubscribe' not in message.html
    assert 'List-Unsubscribe' not in (message.extra_headers or {})


def test_staff_addresses_are_deduplicated(application, users, outbox,
                                          monkeypatch):
    monkeypatch.setitem(application.config, 'ADMINS',
                        ['Author@Example.com', 'admin@example.com'])
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
    assert sorted(m.recipients[0].lower() for m in outbox) == [
        'admin@example.com', 'author@example.com']


def test_commenter_is_never_told_about_their_own_comment(
        application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'],
                              email='author@example.com')
        notify_comment_published(comment)
    assert [m.recipients[0] for m in outbox] == ['admin@example.com']


def test_page_comment_goes_to_owner_only(application, users, outbox):
    with application.test_request_context():
        page = Page(title='About', slug='about', kind='content',
                    is_published=True, comments_enabled=True)
        db.session.add(page)
        db.session.commit()
        comment = add_comment(page_id=page.id)
        notify_comment_published(comment)
    (message,) = outbox
    assert message.recipients == ['admin@example.com']
    assert '/about#comment-' in message.body
    assert '《About》' in message.body


def test_pending_comment_links_to_the_review_queue(application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'], status='pending')
        notify_comment_pending(comment)
    assert len(outbox) == 2
    message = outbox[0]
    assert message.subject == "[Aisaka's Blog] 新评论待审核：Test"
    assert '/admin/comments?status=pending' in message.html
    assert '前往审核' in message.html


# --- reply -> the commenter who was answered -----------------------------

def test_reply_tells_the_commenter_who_asked_for_it(application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
        reply = reply_to(top, name='Bob', email='bob@example.com',
                         body='@Ann Agreed')
        notify_comment_published(reply)
    (message,) = mails_to(outbox, 'ann@example.com')
    assert message.subject == "[Aisaka's Blog] 有人回复了你的评论"
    assert 'Bob' in message.body and 'Agreed' in message.body
    assert f'#comment-{reply.id}' in message.body
    link = unsubscribe_link(message)
    assert message.extra_headers == {'List-Unsubscribe': f'<{link}>'}
    assert link in message.html


def test_reply_is_not_sent_without_consent_or_to_oneself_or_to_nobody(
        application, users, outbox):
    with application.test_request_context():
        quiet = add_comment(post_id=users['post'], email='quiet@example.com')
        notify_comment_published(reply_to(quiet, email='bob@example.com'))
        eager = add_comment(post_id=users['post'], email='eager@example.com',
                            notify_replies=True)
        notify_comment_published(reply_to(eager, email='Eager@example.com'))
        orphan = add_comment(post_id=users['post'], parent_id=eager.id,
                             email='orphan@example.com')
        notify_comment_published(orphan)
    assert mails_to(outbox, 'quiet@example.com') == []
    assert mails_to(outbox, 'eager@example.com') == []


def test_reply_to_a_reply_tells_that_reply_author(application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], email='ann@example.com')
        first = reply_to(top, name='Bob', email='bob@example.com',
                         notify_replies=True)
        second = add_comment(post_id=users['post'], parent_id=top.id,
                             answered_id=first.id, name='Cy',
                             email='cy@example.com', body='@Bob me too')
        notify_comment_published(second)
    assert len(mails_to(outbox, 'bob@example.com')) == 1
    assert mails_to(outbox, 'ann@example.com') == []


# --- approval -> the commenter -------------------------------------------

def test_approval_tells_a_commenter_who_asked(application, users, outbox):
    with application.test_request_context():
        mine = add_comment(post_id=users['post'], email='ann@example.com',
                           notify_replies=True)
        silent = add_comment(post_id=users['post'], email='bob@example.com')
        notify_comments_approved([mine, silent])
    (message,) = outbox
    assert message.recipients == ['ann@example.com']
    assert message.subject == "[Aisaka's Blog] 你的评论已通过审核"
    assert f'/post/{users["post"]}#comment-{mine.id}' in message.body
    assert unsubscribe_link(message) in message.html


def test_approving_a_reply_also_tells_the_answered_commenter(
        application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], email='ann@example.com',
                          notify_replies=True)
        reply = reply_to(top, email='bob@example.com', notify_replies=True)
        notify_comments_approved([reply])
    subjects = {m.recipients[0]: m.subject for m in outbox}
    assert '通过审核' in subjects['bob@example.com']
    assert '回复了你的评论' in subjects['ann@example.com']


# --- robustness ----------------------------------------------------------

def test_long_comments_are_cut_and_markup_is_escaped(application, users, outbox):
    with application.test_request_context():
        long = add_comment(post_id=users['post'], body='x' * 400)
        notify_comment_published(long)
        evil = add_comment(post_id=users['post'],
                           body='<script>alert(1)</script>')
        notify_comment_published(evil)
    first, second = outbox[0], outbox[2]
    assert ('x' * 300 + '……') in first.body
    assert 'x' * 301 not in first.body
    assert '<script>' not in second.html
    assert '&lt;script&gt;' in second.html


def test_nothing_is_sent_when_mail_is_not_configured(
        application, users, outbox, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
        notify_comment_pending(comment)
        notify_comments_approved([comment])
    assert outbox == []


def test_a_mail_failure_never_reaches_the_caller(
        application, users, outbox, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise OSError('smtp down')

    monkeypatch.setattr('app.comment_mail.send_email', boom)
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
    assert 'Could not send comment emails' in caplog.text
