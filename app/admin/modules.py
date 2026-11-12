import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import (BulkCommentForm, CategoryAdminForm,
                             CommentReplyForm, DeleteForm)
from app.admin.pages import _like_pattern
from app.comment_mail import notify_comment_published, notify_comments_approved
from app.comments import CommentRejected, CommentsClosed, submit_comment
from app.models import Category, Post, PostComment
from app.security import admin_required


COMMENTS_PER_PAGE = 50


def _commit_or_flash(message):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash(message)
        return False
    return True


@bp.route('/categories', methods=['GET', 'POST'])
@login_required
@admin_required
def categories():
    form = CategoryAdminForm()
    if form.validate_on_submit():
        db.session.add(Category(name=form.name.data))
        if _commit_or_flash('分类保存失败，请重试。'):
            return redirect(url_for('admin.categories'))
    categories = db.session.scalars(sa.select(Category).order_by(
        Category.name)).all()
    return render_template(
        'admin/categories/list.html', categories=categories, form=form,
        delete_form=DeleteForm())


@bp.route('/categories/<int:category_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = db.get_or_404(Category, category_id)
    form = CategoryAdminForm(category=category)
    if not form.validate_on_submit():
        abort(400)
    category.name = form.name.data
    if not _commit_or_flash('分类保存失败，请重试。'):
        abort(500)
    return redirect(url_for('admin.categories'))


@bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    if not DeleteForm().validate_on_submit():
        abort(400)
    category = db.get_or_404(Category, category_id)
    in_use = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.category_id == category.id))
    if in_use:
        flash('该分类仍有文章使用，不能删除。')
        abort(400)
    db.session.delete(category)
    if not _commit_or_flash('分类删除失败，请重试。'):
        abort(500)
    return redirect(url_for('admin.categories'))


COMMENT_STATUSES = ('all', 'pending', 'approved')


def _comment_target(raw):
    """Parse 'post:12' / 'page:3' / 'episode:4' into a SQL condition; None when absent."""
    if not raw:
        return None
    kind, _, value = raw.partition(':')
    columns = {'post': PostComment.post_id, 'page': PostComment.page_id,
               'episode': PostComment.episode_id}
    if kind not in columns or not value.isdigit():
        abort(400)
    return columns[kind] == int(value)


def _comments_back():
    """Return to the list the admin came from, filters and all."""
    target = request.form.get('next', '')
    if target.startswith('/admin/comments'):
        return redirect(target)
    return redirect(url_for('admin.comments'))


@bp.route('/comments', methods=['GET'])
@login_required
@admin_required
def comments():
    status = request.args.get('status', 'all')
    if status not in COMMENT_STATUSES:
        abort(400)
    search = request.args.get('q', '').strip()
    target = request.args.get('target', '')
    condition = _comment_target(target)

    # Each row names the post, page or episode it belongs to.
    query = sa.select(PostComment).options(
        so.selectinload(PostComment.post), so.selectinload(PostComment.page),
        so.selectinload(PostComment.episode)).order_by(
        PostComment.timestamp.desc(), PostComment.id.desc())
    if status != 'all':
        query = query.where(PostComment.status == status)
    if condition is not None:
        query = query.where(condition)
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            PostComment.name.ilike(pattern, escape='\\'),
            PostComment.email.ilike(pattern, escape='\\'),
            PostComment.body.ilike(pattern, escape='\\')))

    counts = dict(db.session.execute(sa.select(
        PostComment.status, sa.func.count()).group_by(PostComment.status)).all())
    pending = counts.get('pending', 0)
    approved = counts.get('approved', 0)
    listing = db.paginate(query, page=request.args.get('page', 1, type=int),
                          per_page=COMMENTS_PER_PAGE, error_out=False)
    return render_template(
        'admin/comments/list.html',
        post_comments=listing.items, listing=listing, status=status,
        search=search, target=target,
        tab_counts={'pending': pending, 'approved': approved,
                    'all': pending + approved},
        delete_form=DeleteForm(), bulk_form=BulkCommentForm(),
        reply_form=CommentReplyForm())


@bp.route('/comments/<int:comment_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_comment(comment_id):
    if not BulkCommentForm().validate_on_submit():
        abort(400)
    comment = db.get_or_404(PostComment, comment_id)
    newly_approved = comment.status != 'approved'
    comment.status = 'approved'
    if not _commit_or_flash('评论保存失败，请重试。'):
        abort(500)
    if newly_approved:
        notify_comments_approved([comment])
    return _comments_back()


@bp.route('/comments/posts/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_article_comment(comment_id):
    if not DeleteForm().validate_on_submit():
        abort(400)
    db.session.delete(db.get_or_404(PostComment, comment_id))
    if not _commit_or_flash('评论删除失败，请重试。'):
        abort(500)
    return _comments_back()


@bp.route('/comments/bulk', methods=['POST'])
@login_required
@admin_required
def bulk_comments():
    if not BulkCommentForm().validate_on_submit():
        abort(400)
    action = request.form.get('action', '')
    raw_ids = request.form.getlist('ids')
    if action not in ('approve', 'delete') or not all(i.isdigit() for i in raw_ids):
        abort(400)
    selected = db.session.scalars(sa.select(PostComment).where(
        PostComment.id.in_([int(i) for i in raw_ids]))).all()
    newly_approved = []
    for comment in selected:
        if action == 'approve':
            if comment.status != 'approved':
                newly_approved.append(comment)
            comment.status = 'approved'
        else:
            db.session.delete(comment)
    if not _commit_or_flash('批量操作失败，请重试。'):
        abort(500)
    notify_comments_approved(newly_approved)
    flash(f'已处理 {len(selected)} 条评论。')
    return _comments_back()


@bp.route('/comments/<int:comment_id>/reply', methods=['POST'])
@login_required
@admin_required
def reply_comment(comment_id):
    form = CommentReplyForm()
    comment = db.get_or_404(PostComment, comment_id)
    if not form.validate_on_submit():
        flash('回复内容不能为空，且不超过 1000 字。')
        return _comments_back()
    try:
        result = submit_comment(
            comment.post or comment.page or comment.episode,
            name=current_user.username,
            email=current_user.email, body=form.body.data,
            parent_id=comment.id, author=current_user)
    except CommentsClosed:
        flash('这里的评论已关闭，不能回复。')
        return _comments_back()
    except CommentRejected as exc:
        flash(str(exc))
        return _comments_back()
    if not _commit_or_flash('回复保存失败，请重试。'):
        abort(500)
    notify_comment_published(result.comment)
    flash('回复已发布。')
    return _comments_back()
