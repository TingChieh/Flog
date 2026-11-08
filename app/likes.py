"""Reactions without signing in: a browser is one reader, a network is capped.

A reader picks one emoji per post (picking it again takes it back, picking
another one changes it). A browser gets a random cookie the first time it
reacts; only a keyed hash of it is stored, so a reaction can be taken back from
the same browser. To blunt scripts that simply drop the cookie, a post accepts
only a few reactions from one network address (stored hashed too, never the
address itself).
"""
import hashlib
import hmac
import secrets

import sqlalchemy as sa
from flask import current_app, request
from flask_babel import lazy_gettext as _l
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import PostLike

COOKIE_NAME = 'flog_visitor'
COOKIE_MAX_AGE = 2 * 365 * 24 * 60 * 60

# (emoji, name); the first one is what a plain like becomes.
REACTIONS = (
    ('\u2764\ufe0f', _l('Love')),
    ('\U0001f44d', _l('Agree')),
    ('\U0001f602', _l('Funny')),
    ('\U0001f389', _l('Celebrate')),
    ('\U0001f914', _l('Thinking')),
)
REACTION_EMOJI = tuple(emoji for emoji, _name in REACTIONS)
DEFAULT_REACTION = REACTION_EMOJI[0]

LIKED, CHANGED, UNLIKED, LIMITED = 'liked', 'changed', 'unliked', 'limited'


def _digest(kind, value):
    key = current_app.config['SECRET_KEY'].encode()
    return hmac.new(key, f'{kind}:{value}'.encode(), hashlib.sha256).hexdigest()


def read_visitor_token():
    token = request.cookies.get(COOKIE_NAME, '')
    return token if 16 <= len(token) <= 100 else None


def hash_address():
    """A keyed hash of the requester's network address."""
    return _digest('ip', request.remote_addr or '')


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


def own_reaction(post, token):
    """The emoji this reader picked for the post, or None."""
    own = _own_likes(post.id, token)
    return own[0].emoji if own else None


def reaction_counts(post):
    """{emoji: how many readers picked it} for every offered emoji."""
    rows = db.session.execute(
        sa.select(PostLike.emoji, sa.func.count()).where(PostLike.post_id == post.id)
        .group_by(PostLike.emoji)).all()
    found = dict(rows)
    return {emoji: found.get(emoji, 0) for emoji in REACTION_EMOJI}


def react(post, token, emoji=DEFAULT_REACTION):
    """Pick the emoji, take it back, or change it. Returns LIKED, CHANGED, UNLIKED or LIMITED."""
    existing = _own_likes(post.id, token)
    if existing:
        if all(like.emoji == emoji for like in existing):
            for like in existing:
                db.session.delete(like)
            return UNLIKED
        for like in existing:
            like.emoji = emoji
        return CHANGED
    address = hash_address()
    taken = db.session.scalar(sa.select(sa.func.count()).select_from(PostLike).where(
        PostLike.post_id == post.id, PostLike.ip_hash == address))
    if taken >= current_app.config['LIKES_PER_IP_PER_POST']:
        return LIMITED
    db.session.add(PostLike(
        post_id=post.id, visitor_id=_digest('visitor', token), ip_hash=address,
        emoji=emoji, user_id=current_user.id if current_user.is_authenticated else None))
    try:
        db.session.flush()
    except IntegrityError:
        # A double click got there first; the post is reacted to either way.
        db.session.rollback()
    return LIKED

