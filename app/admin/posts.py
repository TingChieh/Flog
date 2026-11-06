import secrets
from datetime import datetime, timezone
from types import SimpleNamespace

import sqlalchemy as sa
from flask import (abort, flash, make_response, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.admin import bp
from app.authorization import owned_post_or_404
from app.content import (BODY_FORMAT_MARKDOWN, normalize_body_format,
                         render_article)
from app.forms import PostDraftForm
from app.models import Category, Post, PostRevision
from app.timezones import later_update, to_display
from app.post_drafts import (DraftValues, PostDraftError, discard_draft,
                             invalidate_editor_writes, publish_draft,
                             restore_revision, save_draft,
                             save_editor_draft, snapshot_draft, unpublish_post)


def draft_values_from_json(payload):
    if not isinstance(payload, dict):
        abort(400)
    title = payload.get('title')
    body = payload.get('body')
    category_id = payload.get('category_id')
    if not isinstance(title, str) or not isinstance(body, str):
        abort(400)
    if len(title) > 120:
        abort(400)
    if isinstance(category_id, bool) or not isinstance(category_id, int):
        abort(400)
    if db.session.get(Category, category_id) is None:
        abort(400)
    return DraftValues(title, body, category_id)


def editor_request_metadata():
    session_key = request.headers.get('X-Draft-Key')
    sequence = request.headers.get('X-Draft-Sequence')
    try:
        generation = int(request.headers.get('X-Draft-Generation', '0'))
    except ValueError:
        abort(400)
    if generation < 0:
        abort(400)
    if session_key is not None and (not session_key or len(session_key) > 64):
        abort(400)
    if sequence is None:
        return session_key, None, generation
    try:
        sequence = int(sequence)
    except ValueError:
        abort(400)
    if sequence < 1:
        abort(400)
    return session_key, sequence, generation


def save_editor_request(post, values, session_key, sequence, generation):
    if post is not None or not session_key:
        return save_editor_draft(
            current_user, post, values, sequence, session_key, generation)
    try:
        saved, applied = save_editor_draft(
            current_user, None, values, sequence, session_key, generation)
        db.session.flush()
        return saved, applied
    except IntegrityError:
        db.session.rollback()
        saved = db.session.scalar(sa.select(Post).where(
            Post.editor_session_key == session_key))
        if saved is None:
            raise
        return save_editor_draft(
            current_user, saved, values, sequence, session_key, generation)


def editor_save_result(post, applied, generation):
    result = {'post_id': post.id, 'applied': applied,
              'generation': post.draft_generation, 'sequence': post.draft_sequence}
    if post.draft_generation != generation:
        db.session.rollback()
        abort(409)
    return result


def _commit_post_change(error_message):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash(error_message)
        abort(500)


def _post_revisions(post):
    return db.session.scalars(sa.select(PostRevision).where(
        PostRevision.post_id == post.id).order_by(
            PostRevision.created_at.desc(), PostRevision.id.desc())).all()


@bp.route('/posts', methods=['GET'])
@login_required
def posts():
    scope = request.args.get('scope')
    if scope not in (None, 'mine', 'all'):
        abort(400)
    if not current_user.is_admin:
        scope = 'mine'
    elif scope is None:
        scope = 'all'
    query = sa.select(Post).order_by(Post.timestamp.desc())
    if scope == 'mine':
        query = query.where(Post.user_id == current_user.id)
    return render_template(
        'admin/posts/list.html', posts=db.session.scalars(query).all(),
        posts_scope=scope)


@bp.route('/posts/draft', methods=['POST'])
@login_required
def create_draft():
    session_key, sequence, generation = editor_request_metadata()
    post, applied = save_editor_request(
        None, draft_values_from_json(request.get_json(silent=True)),
        session_key, sequence, generation)
    result = editor_save_result(post, applied, generation)
    db.session.flush()
    saved_at = post.draft.updated_at.isoformat()
    _commit_post_change('草稿保存失败，请重试。')
    return {**result, 'saved_at': saved_at}, 201


@bp.route('/posts/draft/leave', methods=['POST'])
@login_required
def create_draft_and_leave():
    session_key, sequence, generation = editor_request_metadata()
    post, applied = save_editor_request(
        None, draft_values_from_json(request.get_json(silent=True)),
        session_key, sequence, generation)
    result = editor_save_result(post, applied, generation)
    db.session.flush()
    revision = snapshot_draft(current_user, post.id) if applied else None
    _commit_post_change('草稿保存失败，请重试。')
    return {**result, 'revision_created': revision is not None}, 201


@bp.route('/posts/<int:post_id>/draft', methods=['PUT'])
@login_required
def update_draft(post_id):
    post = owned_post_or_404(post_id, current_user)
    _, sequence, generation = editor_request_metadata()
    post, applied = save_editor_request(
        post, draft_values_from_json(request.get_json(silent=True)),
        None, sequence, generation)
    result = editor_save_result(post, applied, generation)
    db.session.flush()
    saved_at = post.draft.updated_at.isoformat()
    _commit_post_change('草稿保存失败，请重试。')
    return {**result, 'saved_at': saved_at}


@bp.route('/posts/<int:post_id>/leave', methods=['POST'])
@login_required
def leave_editor(post_id):
    post = owned_post_or_404(post_id, current_user)
    _, sequence, generation = editor_request_metadata()
    post, applied = save_editor_request(
        post, draft_values_from_json(request.get_json(silent=True)),
        None, sequence, generation)
    result = editor_save_result(post, applied, generation)
    revision = snapshot_draft(current_user, post.id) if applied else None
    _commit_post_change('草稿保存失败，请重试。')
    return {**result, 'revision_created': revision is not None}


@bp.route('/posts/new', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostDraftForm()
    if form.validate_on_submit():
        post = save_draft(
            current_user, None,
            DraftValues(form.title.data, form.post.data, form.category.data))
        db.session.flush()
        _commit_post_change('草稿保存失败，请重试。')
        flash('草稿已保存。')
        return redirect(url_for('admin.edit_post', post_id=post.id))
    return render_template('admin/posts/form.html', form=form, post=None,
                           legacy_html=False, revisions=[],
                           editor_session_key=secrets.token_urlsafe(24),
                           editor_sequence=0, draft_generation=0)


@bp.route('/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = owned_post_or_404(post_id, current_user)
    form = PostDraftForm()
    if form.validate_on_submit():
        invalidate_editor_writes(post)
        post.body_format = normalize_body_format(post.body_format)
        save_draft(
            current_user, post,
            DraftValues(form.title.data, form.post.data, form.category.data))
        _commit_post_change('草稿保存失败，请重试。')
        flash('草稿已保存。')
        return redirect(url_for('admin.edit_post', post_id=post.id))
    if not form.is_submitted():
        editable = post.draft or post
        form.title.data = editable.title
        form.post.data = editable.body
        form.category.data = editable.category_id
    legacy_html = normalize_body_format(post.body_format) != BODY_FORMAT_MARKDOWN
    return render_template(
        'admin/posts/form.html', form=form, post=post,
        legacy_html=legacy_html, revisions=_post_revisions(post),
        editor_session_key=None,
        editor_sequence=post.draft_sequence,
        draft_generation=post.draft_generation)


@bp.route('/posts/preview', methods=['POST'])
@login_required
def preview_post():
    """Render what the editor holds right now as a reader would see it.

    Nothing is saved: the editor posts its current title and body, so a new
    post, a draft and an unsaved edit all preview the same way.
    """
    post_id = request.form.get('post_id', type=int)
    existing = owned_post_or_404(post_id, current_user) if post_id else None
    title = request.form.get('title', '').strip()[:120]
    body = request.form.get('body', '')
    body_format = (normalize_body_format(existing.body_format) if existing
                   else BODY_FORMAT_MARKDOWN)
    article_html, article_toc = render_article(body, body_format)
    now = datetime.now(timezone.utc)
    # Dates as they will read once this is published (or its update is).
    live = existing is not None and existing.is_published
    timestamp = existing.timestamp if live else now
    preview = SimpleNamespace(
        id=existing.id if existing else 'preview',
        title=title or '无标题',
        author=existing.author if existing else current_user,
        timestamp=timestamp,
        local_timestamp=to_display(timestamp),
        local_updated_at=later_update(timestamp, now) if live else None,
        view_count=existing.view_count if existing else 0)
    response = make_response(render_template(
        'post/preview.html', post=preview, article_html=article_html,
        article_toc=article_toc, title=preview.title))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@bp.route('/posts/<int:post_id>/publish', methods=['POST'])
@login_required
def publish_post(post_id):
    try:
        publish_draft(current_user, post_id)
    except PostDraftError as exc:
        flash(str(exc))
        return redirect(url_for('admin.edit_post', post_id=post_id))
    _commit_post_change('文章发布失败，请重试。')
    flash('文章已发布。')
    return redirect(url_for('admin.edit_post', post_id=post_id))


@bp.route('/posts/<int:post_id>/unpublish', methods=['POST'])
@login_required
def unpublish(post_id):
    unpublish_post(current_user, post_id)
    _commit_post_change('文章取消发布失败，请重试。')
    flash('文章已取消发布。')
    return redirect(url_for('admin.edit_post', post_id=post_id))


@bp.route('/posts/<int:post_id>/discard-draft', methods=['POST'])
@login_required
def discard_post_draft(post_id):
    discard_draft(current_user, post_id)
    _commit_post_change('草稿丢弃失败，请重试。')
    flash('草稿已丢弃。')
    return redirect(url_for('admin.edit_post', post_id=post_id))


@bp.route('/posts/<int:post_id>/revisions/<int:revision_id>/restore',
          methods=['POST'])
@login_required
def restore_post_revision(post_id, revision_id):
    try:
        restore_revision(current_user, post_id, revision_id)
    except PostDraftError as exc:
        flash(str(exc))
        return redirect(url_for('admin.edit_post', post_id=post_id))
    _commit_post_change('版本恢复失败，请重试。')
    flash('版本已恢复为草稿。')
    return redirect(url_for('admin.edit_post', post_id=post_id))


@bp.route('/posts/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = owned_post_or_404(post_id, current_user)
    db.session.execute(post.likes.delete())
    db.session.delete(post)
    db.session.commit()
    flash('文章已删除。')
    return redirect(url_for('admin.posts'))
