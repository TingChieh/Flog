from dataclasses import dataclass

import sqlalchemy as sa
from flask import abort
from langdetect import LangDetectException, detect

from app import db
from app.authorization import owned_post_or_404
from app.content import BODY_FORMAT_MARKDOWN, prepare_content_source
from app.models import Category, Post, PostDraft, PostRevision, get_site_settings


DEFAULT_POST_REVISION_LIMIT = 20
MIN_POST_REVISION_LIMIT = 1
MAX_POST_REVISION_LIMIT = 100


class PostDraftError(ValueError):
    pass


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
    if not result.rowcount:
        return post, False
    post = save_draft(actor, post, values)
    post.draft.last_editor_sequence = post.draft_sequence
    return post, True


def invalidate_editor_writes(post):
    db.session.execute(sa.update(Post).where(Post.id == post.id).values(
        draft_generation=Post.draft_generation + 1,
        draft_sequence=0).execution_options(synchronize_session=False))
    db.session.refresh(post)


def publish_draft(actor, post_id):
    post = owned_post_or_404(post_id, actor)
    # Validate an unflushed draft before the ordering update triggers autoflush.
    # Otherwise a bad category reaches a database foreign-key constraint first.
    with db.session.no_autoflush:
        pending_draft = post.draft
        if (pending_draft is not None
                and (pending_draft in db.session.new or pending_draft in db.session.dirty)):
            if not pending_draft.title.strip():
                raise PostDraftError('A title is required before publishing.')
            if not pending_draft.body.strip():
                raise PostDraftError('A body is required before publishing.')
            if (pending_draft.category_id is None or db.session.get(
                    Category, pending_draft.category_id) is None):
                raise PostDraftError('The selected category does not exist.')
    invalidate_editor_writes(post)
    draft = post.draft
    if draft is None:
        raise PostDraftError('A draft is required before publishing.')
    if not draft.title.strip():
        raise PostDraftError('A title is required before publishing.')
    if not draft.body.strip():
        raise PostDraftError('A body is required before publishing.')
    if draft.category_id is None or db.session.get(
            Category, draft.category_id) is None:
        raise PostDraftError('The selected category does not exist.')

    post.title = draft.title
    post.body = draft.body
    post.category_id = draft.category_id
    post.language = draft.language
    post.is_published = True
    post.draft = None
    return post


def unpublish_post(actor, post_id):
    post = owned_post_or_404(post_id, actor)
    invalidate_editor_writes(post)
    if post.draft is None:
        save_draft(actor, post, DraftValues(
            post.title, post.body, post.category_id))
    post.is_published = False
    return post


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
