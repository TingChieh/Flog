import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import DeleteForm, PageForm, ToggleForm
from app.content import BODY_FORMAT_MARKDOWN, normalize_body_format
from app.models import Page
from app.pages import (PAGE_CONTENT, PageValidationError,
                       delete_content_page, save_page)
from app.security import admin_required


PAGE_FILTERS = frozenset({'all', 'published', 'unpublished'})


def _page_values(form):
    return {
        'title': form.title.data,
        'slug': form.slug.data,
        'summary': form.summary.data,
        'body': form.body.data,
        'is_published': form.is_published.data,
        'show_in_nav': form.show_in_nav.data,
        'nav_order': form.nav_order.data,
    }


def _render_form(form, page, status=200):
    legacy_html = page is not None and page.kind == PAGE_CONTENT and \
        normalize_body_format(page.body_format) != BODY_FORMAT_MARKDOWN
    return render_template(
        'admin/pages/form.html', form=form, page=page,
        legacy_html=legacy_html), status


def _like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@bp.route('/pages', methods=['GET'])
@login_required
@admin_required
def pages():
    active_filter = request.args.get('filter', 'all')
    if active_filter not in PAGE_FILTERS:
        abort(400)
    search = request.args.get('q', '').strip()
    query = sa.select(Page).order_by(Page.nav_order, Page.title, Page.id)
    if active_filter == 'published':
        query = query.where(Page.is_published.is_(True))
    elif active_filter == 'unpublished':
        query = query.where(Page.is_published.is_(False))
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            Page.title.ilike(pattern, escape='\\'),
            Page.slug.ilike(pattern, escape='\\')))
    return render_template(
        'admin/pages/list.html', pages=db.session.scalars(query).all(),
        active_filter=active_filter, search=search,
        delete_form=DeleteForm(), toggle_form=ToggleForm())


def _toggle_page_flag(page_id, attribute, message):
    if not ToggleForm().validate_on_submit():
        abort(400)
    page = db.get_or_404(Page, page_id)
    setattr(page, attribute, not getattr(page, attribute))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('页面保存失败，请重试。')
    else:
        flash(message)
    return redirect(url_for('admin.pages', **{
        key: value for key, value in (
            ('q', request.args.get('q')),
            ('filter', request.args.get('filter'))) if value}))


@bp.route('/pages/<int:page_id>/publish', methods=['POST'])
@login_required
@admin_required
def toggle_page_publication(page_id):
    return _toggle_page_flag(page_id, 'is_published', '页面发布状态已更新。')


@bp.route('/pages/<int:page_id>/nav', methods=['POST'])
@login_required
@admin_required
def toggle_page_navigation(page_id):
    return _toggle_page_flag(page_id, 'show_in_nav', '页面导航显示已更新。')


@bp.route('/pages/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_page():
    form = PageForm()
    if form.validate_on_submit():
        page = Page(kind=PAGE_CONTENT, body_format=BODY_FORMAT_MARKDOWN)
        try:
            save_page(page, _page_values(form))
            db.session.commit()
        except PageValidationError as exc:
            db.session.rollback()
            form.slug.errors.append(str(exc))
        except SQLAlchemyError:
            db.session.rollback()
            flash('页面保存失败，请重试。')
        else:
            flash('页面已创建。')
            return redirect(url_for('admin.pages'))
    return _render_form(form, None)


@bp.route('/pages/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_page(page_id):
    page = db.get_or_404(Page, page_id)
    form = PageForm(page=page, obj=page)
    if form.validate_on_submit():
        try:
            save_page(page, _page_values(form))
            db.session.commit()
        except PageValidationError as exc:
            db.session.rollback()
            form.slug.errors.append(str(exc))
        except SQLAlchemyError:
            db.session.rollback()
            flash('页面保存失败，请重试。')
        else:
            flash('页面已更新。')
            return redirect(url_for('admin.pages'))
    return _render_form(form, page)


@bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_page(page_id):
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)
    page = db.get_or_404(Page, page_id)
    try:
        delete_content_page(page)
        db.session.commit()
    except PageValidationError as exc:
        db.session.rollback()
        flash(str(exc))
        abort(400)
    except SQLAlchemyError:
        db.session.rollback()
        flash('页面删除失败，请重试。')
        abort(500)
    flash('页面已删除。')
    return redirect(url_for('admin.pages'))


@bp.route('/pages/<int:page_id>/preview', methods=['GET'])
@login_required
@admin_required
def preview_page(page_id):
    page = db.get_or_404(Page, page_id)
    return render_template('admin/pages/preview.html', page=page)
