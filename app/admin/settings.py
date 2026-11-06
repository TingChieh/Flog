from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from app import db
from app.admin import bp
from app.admin.forms import SiteSettingsForm
from app.models import get_site_settings
from app.post_drafts import trim_all_post_revisions
from app.security import admin_required
from app.site_text import FIELDS, default_site_text


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    site_settings = get_site_settings()
    form = SiteSettingsForm(obj=site_settings)
    if form.validate_on_submit():
        site_settings.registration_open = form.registration_open.data
        site_settings.post_revision_limit = form.post_revision_limit.data
        for name in FIELDS:
            setattr(site_settings, name, (getattr(form, name).data or '').strip() or None)
        trim_all_post_revisions(site_settings.post_revision_limit)
        db.session.commit()
        flash('网站设置已保存。')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings/form.html', form=form,
                           site_text_defaults=default_site_text())
