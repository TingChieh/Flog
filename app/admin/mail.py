"""A read-only look at the mail Resend has sent and received."""
from flask import abort, render_template, request
from flask_login import login_required

from app import resend_client
from app.admin import bp
from app.security import admin_required

BOXES = ('sent', 'received')


@bp.route('/mail', methods=['GET'])
@login_required
@admin_required
def mail():
    box = request.args.get('box', 'sent')
    if box not in BOXES:
        box = 'sent'
    after = request.args.get('after', '')
    if not resend_client.is_valid_id(after):
        after = ''
    page = error = None
    configured = resend_client.configured()
    if configured:
        fetch = (resend_client.list_received if box == 'received'
                 else resend_client.list_sent)
        try:
            page = fetch(after=after or None)
        except resend_client.ResendError as exc:
            error = str(exc)
    return render_template('admin/mail/list.html', box=box, page=page,
                           error=error, configured=configured, after=after)


@bp.route('/mail/<box>/<email_id>', methods=['GET'])
@login_required
@admin_required
def mail_detail(box, email_id):
    if box not in BOXES:
        abort(404)
    fetch = (resend_client.get_received if box == 'received'
             else resend_client.get_sent)
    item = error = None
    try:
        item = fetch(email_id)
    except resend_client.NotFound:
        abort(404)
    except resend_client.ResendError as exc:
        error = str(exc)
    return render_template('admin/mail/detail.html', box=box, item=item,
                           error=error, email_id=email_id)
