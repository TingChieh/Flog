"""Emails about comments: who hears about a comment and what they are told.

Nothing here commits; call it after the comment is saved.
"""
import functools

import sqlalchemy as sa
from flask import current_app, render_template, url_for
from itsdangerous import BadData, URLSafeSerializer

from app import db
from app.email import mail_configured, mail_sender, send_email
from app.models import PostComment
from app.site_text import site_text

EXCERPT_LENGTH = 300


def _unsubscribe_signer():
    return URLSafeSerializer(
        current_app.config['SECRET_KEY'], salt='comment-unsubscribe')


def unsubscribe_token(email):
    """Signed, never expires: an unsubscribe link must keep working."""
    return _unsubscribe_signer().dumps(email.strip().lower())


def email_from_unsubscribe_token(token):
    try:
        email = _unsubscribe_signer().loads(token)
    except BadData:
        return None
    return email if isinstance(email, str) else None


def unsubscribe_url(email):
    return url_for('comment_unsubscribe', token=unsubscribe_token(email),
                   _external=True)


def stop_notifications(email):
    """Switch off emails for every comment written with this address.

    Returns how many comments changed; the caller commits.
    """
    result = db.session.execute(
        sa.update(PostComment).where(
            sa.func.lower(PostComment.email) == email.strip().lower(),
            PostComment.notify_replies.is_(True),
        ).values(notify_replies=False))
    return result.rowcount


def _excerpt(body):
    body = (body or '').strip()
    if len(body) <= EXCERPT_LENGTH:
        return body
    return body[:EXCERPT_LENGTH].rstrip() + '……'


def _target(comment):
    return comment.post or comment.page


def _target_title(comment):
    return _target(comment).title or '无标题'


def _comment_url(comment):
    anchor = f'comment-{comment.id}'
    if comment.post is not None:
        return url_for('post', post_id=comment.post.id, _anchor=anchor,
                       _external=True)
    return url_for('public_page', slug=comment.page.slug, _anchor=anchor,
                   _external=True)


def _staff_addresses(comment):
    """Site owners and the post's author, once each, never the commenter."""
    addresses = list(current_app.config['ADMINS'])
    if comment.post is not None:
        addresses.append(comment.post.author.email)
    skip = {comment.email.strip().lower()}
    result = []
    for address in addresses:
        key = address.strip().lower()
        if key and key not in skip:
            skip.add(key)
            result.append(address.strip())
    return result


def _send(subject, recipient, template, unsubscribe_for=None, **context):
    """One email to one person; ``unsubscribe_for`` adds the opt-out link."""
    site_name = site_text()['site_name']
    headers = None
    if unsubscribe_for:
        url = unsubscribe_url(unsubscribe_for)
        context['unsubscribe_url'] = url
        headers = {'List-Unsubscribe': f'<{url}>'}
    context['site_name'] = site_name
    send_email(
        f'[{site_name}] {subject}', sender=(site_name, mail_sender()),
        recipients=[recipient],
        text_body=render_template(f'email/{template}.txt', **context),
        html_body=render_template(f'email/{template}.html', **context),
        headers=headers)


def _tell_staff(comment, pending):
    title = _target_title(comment)
    if pending:
        subject = f'新评论待审核：{title}'
        action_url = url_for('admin.comments', status='pending',
                             _external=True)
    else:
        subject = f'新评论：{title}'
        action_url = _comment_url(comment)
    for address in _staff_addresses(comment):
        _send(subject, address, 'comment_new', comment=comment,
              pending=pending, target_title=title, action_url=action_url,
              excerpt=_excerpt(comment.body))


def _tell_answered(comment):
    answered = comment.answered
    if answered is None or not answered.notify_replies:
        return
    if answered.email.strip().lower() == comment.email.strip().lower():
        return
    _send('有人回复了你的评论', answered.email, 'comment_reply',
          unsubscribe_for=answered.email, comment=comment,
          target_title=_target_title(comment),
          comment_url=_comment_url(comment), excerpt=_excerpt(comment.body))


def _tell_approved(comment):
    if not comment.notify_replies:
        return
    _send('你的评论已通过审核', comment.email, 'comment_approved',
          unsubscribe_for=comment.email, comment=comment,
          target_title=_target_title(comment),
          comment_url=_comment_url(comment), excerpt=_excerpt(comment.body))


def _quietly(function):
    """Mail is optional and must never break the request that triggered it."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        if not mail_configured():
            return None
        try:
            function(*args, **kwargs)
        except Exception:
            current_app.logger.exception('Could not send comment emails')
        return None
    return wrapper


@_quietly
def notify_comment_published(comment):
    """A comment is now public: tell the owners, and whoever it answers."""
    _tell_staff(comment, pending=False)
    _tell_answered(comment)


@_quietly
def notify_comment_pending(comment):
    """A comment waits for review: tell the owners."""
    _tell_staff(comment, pending=True)


@_quietly
def notify_comments_approved(comments):
    """Held comments just went public: tell their authors, and whoever
    each one answers (the owners already knew about it)."""
    for comment in comments:
        _tell_approved(comment)
        _tell_answered(comment)
