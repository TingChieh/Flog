"""Reading and writing mail through Resend: what was sent and received, and a
form to write or answer a message (sent over the site's SMTP settings)."""
from email.utils import parseaddr

from flask import (abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import login_required

from wtforms.fields import SelectChoice
from app import resend_client
from app.admin import bp
from app.admin.forms import MailComposeForm, clean_message_ids
from app.email import mail_configured, mail_senders, send_email
from app.security import admin_required
from app.timezones import to_display

BOXES = ('sent', 'received')
QUOTE_LIMIT = 4000


def _bare(address):
    return parseaddr(address)[1].lower()


def _is_for_me(item, mine):
    """Whether a received mail was sent to an address the site really uses.

    Resend accepts mail for every address on the domain, so most spam comes in
    for addresses nobody ever set up (info@, contact@, ...).
    """
    return any(_bare(address) in mine
               for address in (*item.to, *item.cc, *item.bcc))


@bp.route('/mail', methods=['GET'])
@login_required
@admin_required
def mail():
    box = request.args.get('box', 'sent')
    if box not in BOXES:
        box = 'sent'
    show_all = request.args.get('all') == '1'
    after = request.args.get('after', '')
    if not resend_client.is_valid_id(after):
        after = ''
    page = error = None
    items = []
    stray = set()
    configured = resend_client.configured()
    if configured:
        fetch = (resend_client.list_received if box == 'received'
                 else resend_client.list_sent)
        try:
            page = fetch(after=after or None)
        except resend_client.ResendError as exc:
            error = str(exc)
    if page:
        items = page.items
        mine = {_bare(address) for address in mail_senders()}
        if box == 'received' and mine:
            stray = {item.id for item in items if not _is_for_me(item, mine)}
            if not show_all:
                items = [item for item in items if item.id not in stray]
    return render_template('admin/mail/list.html', box=box, page=page,
                           items=items, stray=stray, show_all=show_all,
                           error=error, configured=configured, after=after,
                           can_send=mail_configured())


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
                           error=error, email_id=email_id,
                           can_send=mail_configured())


def _prefill_reply(form, email_id):
    """Fill the form from a received mail; returns a notice if that failed."""
    if not resend_client.is_valid_id(email_id):
        return None
    try:
        item = resend_client.get_received(email_id)
    except resend_client.ResendError as exc:
        return str(exc)
    form.to.data = parseaddr(item.reply_to[0] if item.reply_to
                             else item.sender)[1]
    subject = item.subject.strip()
    form.subject.data = (subject if subject.lower().startswith('re:')
                         else f'Re: {subject}'.strip())
    allowed = [choice.value for choice in form.sender.choices]
    for address in item.to:
        candidate = parseaddr(address)[1].lower()
        match = next((a for a in allowed if a.lower() == candidate), None)
        if match:
            form.sender.data = match
            break
    when = (to_display(item.created_at).strftime('%Y-%m-%d %H:%M')
            if item.created_at else '')
    quoted = '\n'.join(f'> {line}'
                       for line in item.text[:QUOTE_LIMIT].splitlines())
    form.body.data = f'\n\n在 {when}，{item.sender} 写道：\n{quoted}'
    form.in_reply_to.data = clean_message_ids(item.message_id)
    form.references.data = form.in_reply_to.data
    return None


@bp.route('/mail/compose', methods=['GET', 'POST'])
@login_required
@admin_required
def mail_compose():
    configured = mail_configured()
    form = MailComposeForm()
    form.sender.choices = [SelectChoice(address, address) for address in mail_senders()]
    notice = None
    if configured:
        if request.method == 'GET' and request.args.get('reply'):
            notice = _prefill_reply(form, request.args['reply'])
        elif form.validate_on_submit():
            headers = {}
            reply_to = clean_message_ids(form.in_reply_to.data)
            references = clean_message_ids(form.references.data, many=True)
            if reply_to:
                headers['In-Reply-To'] = reply_to
            if references:
                headers['References'] = references
            try:
                send_email(form.subject.data.strip(), form.sender.data,
                           form.recipients, form.body.data, None, sync=True,
                           headers=headers or None)
            except Exception:
                current_app.logger.exception(
                    'Could not send mail from the admin page')
                form.body.errors.append('发送失败，请稍后再试；原因见服务器日志。')
            else:
                resend_client.clear_cache()
                flash('邮件已发送。')
                return redirect(url_for('admin.mail', box='sent'))
    return render_template('admin/mail/compose.html', form=form,
                           configured=configured, notice=notice)
