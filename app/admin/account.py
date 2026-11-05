from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.admin import bp
from app.admin.forms import AvatarUploadForm, ToggleForm
from app.avatars import AvatarUploadError, clear_avatar, save_avatar


@bp.route('/account/avatar', methods=['GET', 'POST'])
@login_required
def avatar():
    form = AvatarUploadForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            abort(400)
        try:
            save_avatar(request.files.get('avatar'), current_user)
        except AvatarUploadError as exc:
            flash(str(exc))
        except SQLAlchemyError:
            flash('头像保存失败，请重试。')
        else:
            flash('头像已更新。')
        return redirect(url_for('admin.avatar'))
    return render_template('admin/account/avatar.html', form=form,
                           remove_form=ToggleForm())


@bp.route('/account/avatar/remove', methods=['POST'])
@login_required
def remove_avatar():
    if not ToggleForm().validate_on_submit():
        abort(400)
    try:
        clear_avatar(current_user)
    except SQLAlchemyError:
        flash('头像恢复失败，请重试。')
    else:
        flash('已恢复默认头像。')
    return redirect(url_for('admin.avatar'))
