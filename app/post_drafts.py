from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

import sqlalchemy as sa
from flask import abort
from langdetect import LangDetectException, detect

from app import db
from app.authorization import owned_post_or_404
from app.content import BODY_FORMAT_MARKDOWN, prepare_content_source, publication_body_error
from app.models import Category, Post, PostDraft, PostRevision, get_site_settings
from app.timezones import from_display


logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime, matching how SQLAlchemy stores columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_utc_naive(value: datetime) -> datetime:
    """Convert an aware datetime to naive UTC; treat naive input as DISPLAY_TIMEZONE."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return from_display(value)


@dataclass(frozen=True)
class PublishDueResult:
    published_ids: list[int] = field(default_factory=list)
    failed: list[tuple[int, str]] = field(default_factory=list)


DEFAULT_POST_REVISION_LIMIT = 20
MIN_POST_REVISION_LIMIT = 1
MAX_POST_REVISION_LIMIT = 100


class PostDraftError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class DraftValues:
    title: str
    body: str
    category_id: int | None


def _detect_language(value):
    try:
        return detect(value or '')
    except LangDetectException:
        return ''


def _ensure_can_edit(post, actor):
    if post.id is not None:
        return owned_post_or_404(post.id, actor)
    if post.user_id is not None and post.user_id != actor.id:
        abort(403)
    if not actor.is_admin and (
            post.author is None
            or (post.author.id is None and post.author is not actor)
            or (post.author.id is not None and post.author.id != actor.id)):
        abort(403)
    return post


def _revision_limit(limit):
    if not isinstance(limit, int):
        return DEFAULT_POST_REVISION_LIMIT
    return max(MIN_POST_REVISION_LIMIT, min(limit, MAX_POST_REVISION_LIMIT))


def _trim_post_revisions(post_id, limit):
    stale_revisions = db.session.scalars(
        sa.select(PostRevision).where(PostRevision.post_id == post_id).order_by(
            PostRevision.created_at.desc(), PostRevision.id.desc()
        ).offset(limit)
    ).all()
    for revision in stale_revisions:
        db.session.delete(revision)


def save_draft(actor, post, values):
    if post is None:
        post = Post(title='', body='', body_format=BODY_FORMAT_MARKDOWN,
                    is_published=False, author=actor)
        db.session.add(post)
    post = _ensure_can_edit(post, actor)
    if post.draft is None:
        post.draft = PostDraft(title='', body='')
        db.session.add(post.draft)
    post.draft.title = values.title.strip()
    post.draft.body = prepare_content_source(values.body, post.body_format)
    post.draft.category_id = values.category_id
    post.draft.language = _detect_language(values.body)
    return post


def save_editor_draft(actor, post, values, sequence, session_key=None, generation=0):
    if post is None and session_key:
        post = db.session.scalar(sa.select(Post).where(
            Post.editor_session_key == session_key))
    if post is None:
        post = Post(title='', body='', body_format=BODY_FORMAT_MARKDOWN,
                    is_published=False, author=actor,
                    editor_session_key=session_key)
        db.session.add(post)
        db.session.flush()
    post = _ensure_can_edit(post, actor)
    # The post survives draft deletion. Claim ordering and its write lock in
    # one statement, before reading or modifying the draft in this transaction.
    claim = sa.update(Post).where(
        Post.id == post.id, Post.draft_generation == generation)
    if sequence is not None:
        claim = claim.where(Post.draft_sequence < sequence)
    result = db.session.execute(claim.values(
        draft_sequence=sequence if sequence is not None else Post.draft_sequence + 1
    ).execution_options(synchronize_session=False))
    db.session.refresh(post)
    if not getattr(result, 'rowcount', 0):
        return post, False
    post = save_draft(actor, post, values)
    post.draft.last_editor_sequence = post.draft_sequence
    return post, True


def invalidate_editor_writes(post):
    db.session.execute(sa.update(Post).where(Post.id == post.id).values(
        draft_generation=Post.draft_generation + 1,
        draft_sequence=0).execution_options(synchronize_session=False))
    db.session.refresh(post)


def _validate_publication(values, body_format):
    if not values.title.strip():
        raise PostDraftError('A title is required before publishing.', 'title')
    if len(values.title.strip()) > 120:
        raise PostDraftError('Title must be 120 characters or fewer.', 'title')
    if error := publication_body_error(values.body, body_format):
        raise PostDraftError(error, 'post')
    if values.category_id is None or db.session.get(Category, values.category_id) is None:
        raise PostDraftError('The selected category does not exist.', 'category')


def publish_draft(actor, post_id, values=None):
    post = owned_post_or_404(post_id, actor)
    # Validate an unflushed draft before the ordering update triggers autoflush.
    # Otherwise a bad category reaches a database foreign-key constraint first.
    with db.session.no_autoflush:
        pending_draft = post.draft
        if values is not None:
            _validate_publication(values, post.body_format)
        if (pending_draft is not None
                and (pending_draft in db.session.new or pending_draft in db.session.dirty)):
            _validate_publication(pending_draft, post.body_format)
    invalidate_editor_writes(post)
    if values is not None:
        save_draft(actor, post, values)
    draft = post.draft
    if draft is None:
        raise PostDraftError('A draft is required before publishing.')
    if values is None:
        _validate_publication(draft, post.body_format)
    category_id = draft.category_id
    assert category_id is not None

    now = datetime.now(timezone.utc)
    if not post.is_published:
        post.timestamp = now
        post.updated_at = None
    elif (post.title, post.body, post.category_id) != (
            draft.title, draft.body, draft.category_id):
        post.updated_at = now
    post.title = draft.title
    post.body = draft.body
    post.category_id = category_id
    post.language = draft.language
    post.is_published = True
    post.scheduled_at = None
    post.draft = None
    return post


def unpublish_post(actor, post_id):
    post = owned_post_or_404(post_id, actor)
    invalidate_editor_writes(post)
    if post.draft is None:
        save_draft(actor, post, DraftValues(
            post.title, post.body, post.category_id))
    post.is_published = False
    post.scheduled_at = None
    return post


def schedule_post(actor, post_id: int, scheduled_at: datetime, *,
                  now: datetime | None = None,
                  allow_past: bool = False) -> Post:
    """Schedule an unpublished post to go live at ``scheduled_at``.

    Aware datetimes are converted to UTC; naive datetimes are interpreted in
    ``DISPLAY_TIMEZONE``. Already-published posts must be unpublished first so
    live visibility is never altered implicitly.
    """
    post = owned_post_or_404(post_id, actor)
    if post.is_published:
        raise PostDraftError('Already published posts cannot be scheduled; unpublish first.')
    target_utc = normalize_utc_naive(scheduled_at).replace(microsecond=0)
    current_utc = (normalize_utc_naive(now) if now is not None
                   else utc_now_naive()).replace(microsecond=0)
    if not allow_past and target_utc <= current_utc:
        raise PostDraftError('Scheduled publish time must be in the future.')
    source = post.draft or post
    _validate_publication(source, post.body_format)
    invalidate_editor_writes(post)
    if post.draft is None:
        save_draft(actor, post, DraftValues(
            post.title, post.body, post.category_id))
    post.scheduled_at = target_utc
    return post


def cancel_schedule(actor, post_id: int) -> Post:
    """Clear a pending publish schedule, returning the post to a plain draft."""
    post = owned_post_or_404(post_id, actor)
    post.scheduled_at = None
    return post


def publish_due_posts(now: datetime | None = None) -> PublishDueResult:
    """Publish all unpublished posts whose ``scheduled_at`` is <= ``now`` (UTC).

    Safe to call repeatedly: each post is claimed by clearing ``scheduled_at``
    and setting ``is_published = True`` in a single transaction boundary.
    """
    cutoff = normalize_utc_naive(now) if now is not None else utc_now_naive()
    due_posts = db.session.scalars(
        sa.select(Post).where(
            Post.is_published.is_(False),
            Post.scheduled_at.is_not(None),
            Post.scheduled_at <= cutoff,
        ).order_by(Post.scheduled_at.asc(), Post.id.asc())
    ).all()

    result = PublishDueResult()
    for post in due_posts:
        source = post.draft or post
        try:
            _validate_publication(source, post.body_format)
        except PostDraftError as exc:
            logger.warning('Skipping scheduled post %s: %s', post.id, exc)
            result.failed.append((post.id, str(exc)))
            continue
        scheduled_time = post.scheduled_at or cutoff
        invalidate_editor_writes(post)
        post.title = source.title.strip()
        post.body = source.body
        post.category_id = source.category_id  # type: ignore[assignment]
        post.language = source.language
        post.timestamp = scheduled_time
        post.updated_at = None
        post.is_published = True
        post.scheduled_at = None
        post.draft = None
        result.published_ids.append(post.id)
    return result


def discard_draft(actor, post_id):
    post = owned_post_or_404(post_id, actor)
    invalidate_editor_writes(post)
    post.draft = None
    return post


def restore_revision(actor, post_id, revision_id):
    post = owned_post_or_404(post_id, actor)
    revision = db.session.scalar(sa.select(PostRevision).where(
        PostRevision.id == revision_id, PostRevision.post_id == post.id))
    if revision is None:
        raise PostDraftError('The requested revision does not belong to this post.')
    invalidate_editor_writes(post)
    if post.draft is None:
        post.draft = PostDraft(title='', body='')
        db.session.add(post.draft)
    post.draft.title = revision.title
    post.draft.body = revision.body
    post.draft.category_id = revision.category_id
    post.draft.language = revision.language
    return post


def snapshot_draft(actor, post_id):
    post = owned_post_or_404(post_id, actor)
    if post.draft is None:
        return None
    revision = PostRevision(
        post=post,
        title=post.draft.title,
        body=post.draft.body,
        category_id=post.draft.category_id,
        language=post.draft.language,
    )
    db.session.add(revision)
    db.session.flush()
    _trim_post_revisions(
        post.id, _revision_limit(get_site_settings().post_revision_limit))
    return revision


def trim_all_post_revisions(limit):
    revision_limit = _revision_limit(limit)
    post_ids = db.session.scalars(sa.select(Post.id)).all()
    for post_id in post_ids:
        _trim_post_revisions(post_id, revision_limit)
