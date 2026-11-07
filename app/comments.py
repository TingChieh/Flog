"""Taking comments in: who is trusted, what waits for review, what is refused.

Nothing here commits; the caller owns the transaction.
"""
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from flask import current_app, request
from itsdangerous import BadData, URLSafeTimedSerializer

from app import db
from app.likes import hash_address
from app.models import Episode, Post, PostComment

APPROVED, PENDING, DROPPED = 'approved', 'pending', 'dropped'
MAX_LINKS_FOR_AUTO_APPROVAL = 2
FORM_TOKEN_MAX_AGE = 24 * 60 * 60
_LINK = re.compile(r'https?://|www\.', re.IGNORECASE)


class CommentsClosed(Exception):
    """The post, page or episode does not take comments."""


class CommentRejected(Exception):
    """Refused; the message is shown to the reader."""


@dataclass(frozen=True)
class Submission:
    outcome: str
    comment: PostComment | None = None


@dataclass(frozen=True)
class Thread:
    comment: PostComment
    replies: list


def _signer():
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'], salt='comment-form')


def make_form_token():
    """Stamped when the form is shown; a bot that posts at once is too quick."""
    return _signer().dumps(time.time())


def _filled_too_fast(token):
    minimum = current_app.config['COMMENTS_MIN_FILL_SECONDS']
    if minimum <= 0:
        return False
    try:
        shown_at = _signer().loads(token or '', max_age=FORM_TOKEN_MAX_AGE)
    except BadData:
        return True
    return time.time() - shown_at < minimum


def count_links(body):
    return len(_LINK.findall(body or ''))


def _target_filter(target):
    if isinstance(target, Post):
        return PostComment.post_id == target.id
    if isinstance(target, Episode):
        return PostComment.episode_id == target.id
    return PostComment.page_id == target.id


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _check_rate(ip_hash):
    config = current_app.config
    for seconds, limit in (
            (60, config['COMMENTS_PER_MINUTE_PER_IP']),
            (3600, config['COMMENTS_PER_HOUR_PER_IP'])):
        recent = db.session.scalar(sa.select(sa.func.count()).select_from(
            PostComment).where(
                PostComment.ip_hash == ip_hash,
                PostComment.timestamp >= _now() - timedelta(seconds=seconds)))
        if recent >= limit:
            raise CommentRejected('评论太频繁了，请稍后再试。')


def _check_duplicate(ip_hash, body):
    repeated = db.session.scalar(sa.select(sa.func.count()).select_from(
        PostComment).where(
            PostComment.ip_hash == ip_hash, PostComment.body == body,
            PostComment.timestamp >= _now() - timedelta(hours=1)))
    if repeated:
        raise CommentRejected('你已经提交过相同的评论了。')


def _decide_status(body, email, is_admin):
    if is_admin:
        return APPROVED
    if count_links(body) > MAX_LINKS_FOR_AUTO_APPROVAL:
        return PENDING
    known = db.session.scalar(sa.select(sa.func.count()).select_from(
        PostComment).where(
            PostComment.status == APPROVED, PostComment.user_id.is_(None),
            sa.func.lower(PostComment.email) == email))
    return APPROVED if known else PENDING


def find_reply_target(target, comment_id):
    """The approved comment of this post, page or episode with that id, else None."""
    if not comment_id:
        return None
    return db.session.scalar(sa.select(PostComment).where(
        PostComment.id == comment_id, PostComment.status == APPROVED,
        _target_filter(target)))


def _resolve_parent(target, parent_id):
    """Returns (comment to attach to, comment being answered or None)."""
    answered = find_reply_target(target, parent_id)
    if answered is None:
        raise CommentRejected('要回复的评论不存在或还没有通过审核。')
    if answered.parent_id is None:
        return answered, None
    return answered.parent, answered


def submit_comment(target, *, name, email, body, parent_id=None, honeypot='',
                   form_token='', author=None, notify_replies=False):
    if not target.comments_enabled:
        raise CommentsClosed()
    is_admin = author is not None and author.is_admin
    ip_hash = hash_address()
    body = body.strip()
    email = email.strip().lower()

    if not is_admin:
        if honeypot or _filled_too_fast(form_token):
            return Submission(DROPPED)
        _check_rate(ip_hash)
        _check_duplicate(ip_hash, body)

    parent = answered = None
    if parent_id:
        parent, reply_answered = _resolve_parent(target, parent_id)
        answered = reply_answered or parent
        if reply_answered is not None and not body.startswith(
                f'@{reply_answered.name} '):
            body = f'@{reply_answered.name} {body}'

    comment = PostComment(
        name=name.strip(), email=email, body=body, parent=parent,
        answered=answered, notify_replies=notify_replies,
        status=_decide_status(body, email, is_admin), ip_hash=ip_hash,
        user_id=author.id if is_admin else None)
    if isinstance(target, Post):
        comment.post = target
    elif isinstance(target, Episode):
        comment.episode = target
    else:
        comment.page = target
    db.session.add(comment)
    db.session.flush()
    return Submission(comment.status, comment)


def approved_threads(target):
    """Top-level approved comments, oldest first, each with its replies."""
    rows = db.session.scalars(sa.select(PostComment).where(
        _target_filter(target), PostComment.status == APPROVED).order_by(
            PostComment.timestamp, PostComment.id)).all()
    replies = {}
    for comment in rows:
        if comment.parent_id is not None:
            replies.setdefault(comment.parent_id, []).append(comment)
    threads = [Thread(comment, replies.get(comment.id, []))
               for comment in rows if comment.parent_id is None]
    return threads, len(rows)


def comment_context(target, form):
    """What the shared comment section template needs."""
    threads, count = approved_threads(target)
    reply_to = None
    if target.comments_enabled:
        reply_id = form.parent_id.data or request.args.get('reply', type=int)
        reply_to = find_reply_target(target, reply_id)
    return {
        'comment_threads': threads,
        'comment_count': count,
        'comments_enabled': target.comments_enabled,
        'comment_reply_to': reply_to,
        'comment_form_token': make_form_token(),
    }
