import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import DeleteForm, PageForm, ToggleForm
from app.content import BODY_FORMAT_MARKDOWN, normalize_body_format
from app.models import Page, PodcastShow, get_podcast_show
from app.pages import (PAGE_CONTENT, PageValidationError,
                       delete_content_page, move_nav_item, nav_sort_key,
                       save_page)
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
        'comments_enabled': form.comments_enabled.data,
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


def _pages_redirect():
    return redirect(url_for('admin.pages', **{
        key: value for key, value in (
            ('q', request.args.get('q')),
            ('filter', request.args.get('filter'))) if value}))


def _podcast_matches(show, active_filter, search):
    enabled = show.enabled if show is not None else False
    if active_filter == 'published' and not enabled:
        return False
    if active_filter == 'unpublished' and enabled:
        return False
    if not search:
        return True
    needle = search.lower()
    custom_title = (show.title or '').lower() if show is not None else ''
    return needle in '播客' or needle in 'podcast' or needle in custom_title


def _build_page_items(pages, show, active_filter, search):
    items = [
        {
            'kind': 'page',
            'id': page.id,
            'title': page.title,
            'slug': page.slug,
            'updated_at': page.updated_at,
            'custom_title': None,
            'is_published': page.is_published,
            'show_in_nav': page.show_in_nav,
            'nav_order': page.nav_order,
            'sort_id': page.id,
        }
        for page in pages
    ]
    if _podcast_matches(show, active_filter, search):
        items.append({
            'kind': 'podcast',
            'id': None,
            'title': '播客',
            'slug': 'podcast',
            'updated_at': None,
            'custom_title': show.title if show is not None else None,
            'is_published': show.enabled if show is not None else False,
            'show_in_nav': show.show_in_nav if show is not None else True,
            'nav_order': show.nav_order if show is not None else 100,
            'sort_id': 1,
        })
    items.sort(key=lambda item: nav_sort_key(
        item['kind'], item['nav_order'], item['title'], item['sort_id']))
    return items


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
    page_rows = db.session.scalars(query).all()
    show = db.session.get(PodcastShow, 1)
    items = _build_page_items(page_rows, show, active_filter, search)
    return render_template(
        'admin/pages/list.html', pages=items,
        active_filter=active_filter, search=search,
        delete_form=DeleteForm(), toggle_form=ToggleForm())


def _commit_toggle(message):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('页面保存失败，请重试。')
    else:
        flash(message)
    return _pages_redirect()


def _toggle_page_flag(page_id, attribute, message):
    if not ToggleForm().validate_on_submit():
        abort(400)
    page = db.get_or_404(Page, page_id)
    setattr(page, attribute, not getattr(page, attribute))
    return _commit_toggle(message)


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


@bp.route('/pages/podcast/publish', methods=['POST'])
@login_required
@admin_required
def toggle_podcast_from_pages():
    if not ToggleForm().validate_on_submit():
        abort(400)
    show = get_podcast_show()
    show.enabled = not show.enabled
    return _commit_toggle(
        '播客已开启。' if show.enabled else '播客已关闭，单集和音频都还在。')


@bp.route('/pages/podcast/nav', methods=['POST'])
@login_required
@admin_required
def toggle_podcast_nav_from_pages():
    if not ToggleForm().validate_on_submit():
        abort(400)
    show = get_podcast_show()
    show.show_in_nav = not show.show_in_nav
    return _commit_toggle(
        '导航里已显示播客。' if show.show_in_nav else '导航里已隐藏播客。')


def _move_item(kind, target_id):
    direction = request.form.get('direction')
    if direction not in ('up', 'down') or \
            not ToggleForm().validate_on_submit():
        abort(400)
    try:
        move_nav_item(kind, target_id, direction)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('页面顺序保存失败，请重试。')
    return redirect(url_for('admin.pages'))


@bp.route('/pages/<int:page_id>/move', methods=['POST'])
@login_required
@admin_required
def move_page_order(page_id):
    db.get_or_404(Page, page_id)
    return _move_item('page', page_id)


@bp.route('/pages/podcast/move', methods=['POST'])
@login_required
@admin_required
def move_podcast_order():
    return _move_item('podcast', None)


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
