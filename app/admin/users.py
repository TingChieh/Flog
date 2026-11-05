import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import UserCreateForm, UserDeleteForm, UserEditForm
from app.avatars import remove_avatar_file
from app.authorization import RoleChangeError, change_user_role
from app.authorization import delete_user as remove_user
from app.models import Post, User
from app.security import admin_required


USER_ROLE_FILTERS = frozenset({'all', 'user', 'admin'})


def _like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@bp.route('/users', methods=['GET'])
@login_required
@admin_required
def users():
    role = request.args.get('role', 'all')
    if role not in USER_ROLE_FILTERS:
        abort(400)
    search = request.args.get('q', '').strip()
    post_counts = sa.select(
        Post.user_id.label('user_id'),
        sa.func.count(Post.id).label('post_count'),
    ).group_by(Post.user_id).subquery()
    query = sa.select(
        User, sa.func.coalesce(post_counts.c.post_count, 0)
    ).outerjoin(post_counts, post_counts.c.user_id == User.id)
    if role != 'all':
        query = query.where(User.role == role)
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            User.username.ilike(pattern, escape='\\'),
            User.email.ilike(pattern, escape='\\')))
    rows = db.session.execute(query.order_by(User.username)).all()
    return render_template(
        'admin/users/list.html', user_rows=rows, active_role=role,
        search=search)


@bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    form = UserCreateForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data,
                    role=form.role.data)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户保存失败，请重试。')
        else:
            flash('用户已创建。')
            return redirect(url_for('admin.users'))
    return render_template(
        'admin/users/form.html', form=form, target=None, editing_self=False)


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    target = db.session.scalar(sa.select(User).where(
        User.id == user_id).with_for_update())
    if target is None:
        abort(404)
    editing_self = target.id == current_user.id
    if request.method == 'POST':
        form = UserEditForm(user=target)
        if editing_self:
            form.role.data = target.role  # the select is disabled in the page
    else:
        form = UserEditForm(user=target, obj=target)
    if form.validate_on_submit():
        try:
            target.username = form.username.data
            target.email = form.email.data
            change_user_role(current_user, target, form.role.data)
            if form.password.data:
                target.set_password(form.password.data)
            db.session.commit()
        except RoleChangeError as exc:
            db.session.rollback()
            flash(str(exc))
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户保存失败，请重试。')
        else:
            flash('用户已更新。')
            return redirect(url_for('admin.users'))
    return render_template(
        'admin/users/form.html', form=form, target=target,
        editing_self=editing_self)


@bp.route('/users/<int:user_id>/delete', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_user(user_id):
    target = db.get_or_404(User, user_id)
    if target.id == current_user.id:
        abort(400)
    post_count = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.user_id == target.id))
    candidates = db.session.scalars(sa.select(User).where(
        User.id != target.id).order_by(User.username)).all()
    form = UserDeleteForm()
    form.receiver.choices = [(user.id, user.username) for user in candidates]
    if request.method == 'GET':
        form.receiver.data = current_user.id
    if form.validate_on_submit():
        receiver = db.session.get(User, form.receiver.data) \
            if form.receiver.data else None
        avatar_filename = target.avatar_filename
        try:
            remove_user(current_user, target, receiver)
            db.session.commit()
        except RoleChangeError:
            db.session.rollback()
            form.receiver.errors = [*form.receiver.errors,
                                    '请选择接收文章的其他用户。']
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户删除失败，请重试。')
        else:
            remove_avatar_file(avatar_filename)
            flash('用户已删除。')
            return redirect(url_for('admin.users'))
    return render_template(
        'admin/users/delete.html', form=form, target=target,
        post_count=post_count)
