"""Emails about comments: who hears about a comment and what they are told.

Nothing here commits; call it after the comment is saved.
"""
import sqlalchemy as sa
from flask import current_app, url_for
from itsdangerous import BadData, URLSafeSerializer

from app import db
from app.models import PostComment


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
