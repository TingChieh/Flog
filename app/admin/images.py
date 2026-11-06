import sqlalchemy as sa
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import ImageDeleteForm, ImageEditForm, ImageUploadForm
from app.images import (ImageUploadError, image_usage, remove_variants,
                        save_uploaded_image, sync_untracked_images,
                        thumbnail_url, upload_folder, visible_images)
from app.models import Image


PICKER_LIMIT = 60
UPLOAD_ERRORS = {'Image only!': '不是有效的 gif/jpg/png 图片'}


@bp.app_template_filter('filesize')
def filesize(value):
    size = float(value or 0)
    for unit in ('B', 'KB', 'MB'):
        if size < 1024 or unit == 'MB':
            return f'{int(size)} B' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


bp.app_template_filter('thumbnail')(thumbnail_url)


def _like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _search(query, text):
    if not text:
        return query
    pattern = _like_pattern(text)
    return query.where(sa.or_(
        Image.title.ilike(pattern, escape='\\'),
        Image.note.ilike(pattern, escape='\\'),
        Image.original_name.ilike(pattern, escape='\\')))


@bp.route('/images', methods=['GET'])
@login_required
def images():
    sync_untracked_images()
    search = request.args.get('q', '').strip()
    rows = db.session.scalars(_search(visible_images(current_user), search)).all()
    usage = image_usage([row.filename for row in rows])
    folder = upload_folder()
    cards = [{
        'image': row,
        'uses': len(usage[row.filename]),
        'missing': not (folder / row.filename).is_file(),
    } for row in rows]
    return render_template(
        'admin/images/list.html', cards=cards, search=search,
        upload_form=ImageUploadForm())


@bp.route('/images/upload', methods=['POST'])
@login_required
def upload_images():
    if not ImageUploadForm().validate_on_submit():
        abort(400)
    uploads = [f for f in request.files.getlist('images') if f.filename]
    if not uploads:
        flash('请选择要上传的图片。')
        return redirect(url_for('admin.images'))
    saved, failed = 0, []
    for file in uploads:
        try:
            save_uploaded_image(file, current_user)
        except ImageUploadError as exc:
            failed.append(f'{file.filename}：{UPLOAD_ERRORS.get(str(exc), str(exc))}')
        else:
            saved += 1
    message = f'已上传 {saved} 张'
    if failed:
        message += f'，{len(failed)} 张失败（{"；".join(failed)}）'
    flash(message + '。')
    return redirect(url_for('admin.images'))


@bp.route('/images/picker', methods=['GET'])
@login_required
def image_picker():
    query = _search(visible_images(current_user),
                    request.args.get('q', '').strip()).limit(PICKER_LIMIT)
    return {'images': [{
        'id': image.id, 'title': image.title, 'size': image.size,
        'url': url_for('uploaded_files', filename=image.filename),
        'thumb': thumbnail_url(image),
    } for image in db.session.scalars(query)]}


def _image_or_404(image_id):
    image = db.session.get(Image, image_id)
    if image is None:
        abort(404)
    if not current_user.is_admin and image.user_id != current_user.id:
        abort(403)
    return image


@bp.route('/images/<int:image_id>', methods=['GET', 'POST'])
@login_required
def image_detail(image_id):
    image = _image_or_404(image_id)
    form = ImageEditForm(obj=image)
    if form.validate_on_submit():
        image.title = form.title.data.strip() or Path(image.original_name).stem
        image.note = form.note.data.strip() or None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('图片保存失败，请重试。')
        else:
            flash('图片已更新。')
            return redirect(url_for('admin.image_detail', image_id=image.id))
    return render_template(
        'admin/images/detail.html', image=image, form=form,
        usages=image_usage([image.filename])[image.filename],
        missing=not (upload_folder() / image.filename).is_file())


@bp.route('/images/<int:image_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_image(image_id):
    image = _image_or_404(image_id)
    usages = image_usage([image.filename])[image.filename]
    form = ImageDeleteForm()
    if form.validate_on_submit() and (not usages or form.force.data):
        filename = image.filename
        db.session.delete(image)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('图片删除失败，请重试。')
        else:
            (upload_folder() / filename).unlink(missing_ok=True)
            remove_variants(filename)
            flash('图片已删除。')
            return redirect(url_for('admin.images'))
    elif form.is_submitted() and usages:
        form.force.errors = [*form.force.errors, '请先勾选确认。']
    return render_template(
        'admin/images/delete.html', image=image, form=form, usages=usages)
