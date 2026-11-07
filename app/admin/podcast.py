from datetime import datetime, timezone

import sqlalchemy as sa
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import DeleteForm, EpisodeForm, PodcastShowForm, ToggleForm
from app.images import ImageUploadError, save_uploaded_image
from app.models import Episode, get_podcast_show
from app.podcast import (AudioUploadError, apply_audio, delete_episode,
                         feed_problems, next_episode_number,
                         remove_audio, save_uploaded_audio, show_text)
from app.security import admin_required
from app.timezones import from_display, to_display


def _uploaded(form_field):
    file = form_field.data
    return file if file is not None and getattr(file, 'filename', '') else None


def _save_cover(form, target):
    """Store a newly chosen cover on ``target``; False when it was refused."""
    file = _uploaded(form.cover)
    if file is None:
        return True
    try:
        target.cover_filename = save_uploaded_image(file, current_user).filename
    except ImageUploadError:
        form.cover.errors.append('封面需要是 PNG、JPG 或 GIF 图片。')
        return False
    return True


@bp.errorhandler(413)
def upload_too_large(error):
    limit = current_app.config['PODCAST_AUDIO_MAX_MB']
    flash(f'文件太大了，音频最大 {limit} MB。')
    return redirect(request.referrer or url_for('admin.podcast')), 303


@bp.route('/podcast', methods=['GET'])
@login_required
@admin_required
def podcast():
    episodes = db.session.scalars(sa.select(Episode).order_by(
        Episode.number.desc())).all()
    return render_template(
        'admin/podcast/list.html', episodes=episodes, show=show_text(),
        problems=feed_problems(), podcast=get_podcast_show(),
        toggle_form=ToggleForm(),
        delete_form=DeleteForm())


def _toggle_podcast(attribute, message):
    if not ToggleForm().validate_on_submit():
        abort(400)
    show = get_podcast_show()
    setattr(show, attribute, not getattr(show, attribute))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('保存失败，请重试。')
    else:
        flash(message(show))
    return redirect(url_for('admin.podcast'))


@bp.route('/podcast/enable', methods=['POST'])
@login_required
@admin_required
def toggle_podcast():
    return _toggle_podcast(
        'enabled', lambda show: '播客已开启。' if show.enabled else '播客已关闭，单集和音频都还在。')


@bp.route('/podcast/nav', methods=['POST'])
@login_required
@admin_required
def toggle_podcast_navigation():
    return _toggle_podcast(
        'show_in_nav', lambda show: '导航里已显示播客。' if show.show_in_nav else '导航里已隐藏播客。')


@bp.route('/podcast/show', methods=['GET', 'POST'])
@login_required
@admin_required
def podcast_show():
    show = get_podcast_show()
    form = PodcastShowForm(obj=show)
    if form.validate_on_submit():
        for name in ('title', 'description', 'author', 'owner_email',
                     'category', 'apple_url', 'xiaoyuzhou_url'):
            setattr(show, name, (getattr(form, name).data or '').strip() or None)
        if _save_cover(form, show):
            db.session.commit()
            flash('节目设置已保存。')
            return redirect(url_for('admin.podcast_show'))
        db.session.rollback()
    return render_template('admin/podcast/show.html', form=form,
                           defaults=show_text(), show=show)


def _episode_form_page(form, episode, status=200):
    return render_template('admin/podcast/form.html', form=form,
                           episode=episode), status


@bp.route('/podcast/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_episode():
    form = EpisodeForm()
    if request.method == 'GET':
        form.number.data = next_episode_number()
        form.published_at.data = to_display(
            datetime.now(timezone.utc)).replace(tzinfo=None, second=0, microsecond=0)
        form.comments_enabled.data = True
    if form.validate_on_submit():
        audio = _uploaded(form.audio)
        if audio is None:
            form.audio.errors.append('请选择音频文件。')
            return _episode_form_page(form, None, 400)
        try:
            info = save_uploaded_audio(audio)
        except AudioUploadError as exc:
            form.audio.errors.append(str(exc))
            return _episode_form_page(form, None, 400)
        episode = Episode()
        apply_audio(episode, info)
        _fill_episode(episode, form)
        if not _save_cover(form, episode):
            remove_audio(info.filename)
            return _episode_form_page(form, None, 400)
        db.session.add(episode)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            remove_audio(info.filename)
            flash('单集保存失败，请重试。')
            return _episode_form_page(form, None, 500)
        flash('单集已创建。')
        return redirect(url_for('admin.podcast'))
    return _episode_form_page(form, None, 400 if form.errors else 200)


def _fill_episode(episode, form):
    episode.number = form.number.data
    episode.title = form.title.data.strip()
    episode.summary = (form.summary.data or '').strip() or None
    episode.body = form.body.data or None
    episode.published_at = from_display(form.published_at.data)
    episode.is_published = form.is_published.data
    episode.comments_enabled = form.comments_enabled.data


@bp.route('/podcast/<int:episode_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_episode(episode_id):
    episode = db.get_or_404(Episode, episode_id)
    form = EpisodeForm(episode=episode, obj=episode)
    if request.method == 'GET':
        form.published_at.data = to_display(
            episode.published_at).replace(tzinfo=None)
    if form.validate_on_submit():
        new_info = None
        audio = _uploaded(form.audio)
        if audio is not None:
            try:
                new_info = save_uploaded_audio(audio)
            except AudioUploadError as exc:
                form.audio.errors.append(str(exc))
                return _episode_form_page(form, episode, 400)
        _fill_episode(episode, form)
        if not _save_cover(form, episode):
            if new_info:
                remove_audio(new_info.filename)
            db.session.rollback()
            return _episode_form_page(form, episode, 400)
        old_filename = apply_audio(episode, new_info) if new_info else None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            if new_info:
                remove_audio(new_info.filename)
            flash('单集保存失败，请重试。')
            return _episode_form_page(form, episode, 500)
        if new_info:
            # Only now that the new file is recorded is the old one expendable.
            remove_audio(old_filename)
        flash('单集已更新。')
        return redirect(url_for('admin.podcast'))
    return _episode_form_page(form, episode, 400 if form.errors else 200)


@bp.route('/podcast/<int:episode_id>/publish', methods=['POST'])
@login_required
@admin_required
def toggle_episode_publication(episode_id):
    if not ToggleForm().validate_on_submit():
        abort(400)
    episode = db.get_or_404(Episode, episode_id)
    episode.is_published = not episode.is_published
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('单集保存失败，请重试。')
    else:
        flash('单集发布状态已更新。')
    return redirect(url_for('admin.podcast'))


@bp.route('/podcast/<int:episode_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_episode_view(episode_id):
    if not DeleteForm().validate_on_submit():
        abort(400)
    episode = db.get_or_404(Episode, episode_id)
    try:
        filename = delete_episode(episode)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('单集删除失败，请重试。')
        abort(500)
    remove_audio(filename)
    flash('单集已删除。')
    return redirect(url_for('admin.podcast'))
