"""Likes without signing in: a browser is one reader, a network is capped.

A browser gets a random cookie the first time it likes something; only a keyed
hash of it is stored, so a like can be taken back from the same browser. To
blunt scripts that simply drop the cookie, a post accepts only a few likes from
one network address (stored hashed too, never the address itself).
"""
import hashlib
import hmac
import secrets

import sqlalchemy as sa
from flask import current_app, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import PostLike

COOKIE_NAME = 'flog_visitor'
COOKIE_MAX_AGE = 2 * 365 * 24 * 60 * 60

LIKED, UNLIKED, LIMITED = 'liked', 'unliked', 'limited'


def _digest(kind, value):
    key = current_app.config['SECRET_KEY'].encode()
    return hmac.new(key, f'{kind}:{value}'.encode(), hashlib.sha256).hexdigest()


def read_visitor_token():
    token = request.cookies.get(COOKIE_NAME, '')
    return token if 16 <= len(token) <= 100 else None


def new_visitor_token():
    return secrets.token_urlsafe(32)


def attach_visitor_cookie(response, token):
    response.set_cookie(
        COOKIE_NAME, token, max_age=COOKIE_MAX_AGE, path='/',
        secure=bool(current_app.config.get('SESSION_COOKIE_SECURE', False)),
        httponly=True, samesite='Lax')


def _own_likes(post_id, token):
    """This reader's likes of the post: the browser's, and the signed-in user's."""
    who = []
    if token:
        who.append(PostLike.visitor_id == _digest('visitor', token))
    if current_user.is_authenticated:
        who.append(PostLike.user_id == current_user.id)
    if not who:
        return []
    return db.session.scalars(sa.select(PostLike).where(
        PostLike.post_id == post_id, sa.or_(*who))).all()


def is_liked(post, token):
    return bool(_own_likes(post.id, token))


def toggle_like(post, token):
    """Like the post, or take the like back. Returns LIKED, UNLIKED or LIMITED."""
    existing = _own_likes(post.id, token)
    if existing:
        for like in existing:
            db.session.delete(like)
        return UNLIKED
    address = _digest('ip', request.remote_addr or '')
    taken = db.session.scalar(sa.select(sa.func.count()).select_from(PostLike).where(
        PostLike.post_id == post.id, PostLike.ip_hash == address))
    if taken >= current_app.config['LIKES_PER_IP_PER_POST']:
        return LIMITED
    db.session.add(PostLike(
        post_id=post.id, visitor_id=_digest('visitor', token), ip_hash=address,
        user_id=current_user.id if current_user.is_authenticated else None))
    try:
        db.session.flush()
    except IntegrityError:
        # A double click got there first; the post is liked either way.
        db.session.rollback()
    return LIKED
