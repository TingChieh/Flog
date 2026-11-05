import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import CategoryAdminForm, DeleteForm
from app.models import Category, Post, PostComment
from app.security import admin_required


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


@bp.route('/comments', methods=['GET'])
@login_required
@admin_required
def comments():
    post_comments = db.session.scalars(sa.select(PostComment).order_by(
        PostComment.timestamp.desc())).all()
    return render_template(
        'admin/comments/list.html', post_comments=post_comments,
        delete_form=DeleteForm())


@bp.route('/comments/posts/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_article_comment(comment_id):
    if not DeleteForm().validate_on_submit():
        abort(400)
    db.session.delete(db.get_or_404(PostComment, comment_id))
    if not _commit_or_flash('评论删除失败，请重试。'):
        abort(500)
    return redirect(url_for('admin.comments'))
