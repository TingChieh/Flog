from threading import Thread
from flask import current_app, render_template, url_for
from flask_mail import Message
from app import mail
from app.models import RESET_TOKEN_LIFETIME, User
from app.site_text import site_text


def mail_sender():
    """The address mail is sent from, or None when none is configured.

    MAIL_FROM wins: providers such as Resend log in with a name that is not an
    address and send from a verified one. Otherwise MAIL_USERNAME (the SMTP
    login, usually the from address too), then the first admin.
    """
    config = current_app.config
    candidates = [config['MAIL_FROM'] or '', config['MAIL_USERNAME'] or '',
                  *config['ADMINS']]
    return next((value for value in candidates if '@' in value), None)


def mail_senders():
    """Addresses the admin page may send from: MAIL_SENDERS, then the default."""
    result = []
    for address in [*current_app.config['MAIL_SENDERS'], mail_sender() or '']:
        address = address.strip()
        if '@' in address and address.lower() not in [a.lower() for a in result]:
            result.append(address)
    return result


def mail_configured():
    return bool(current_app.config['MAIL_SERVER'] and mail_sender())


def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:
            app.logger.exception('Could not send email "%s"', msg.subject)


def send_email(subject, sender, recipients, text_body, html_body,
               attachments=None, sync=False, headers=None):
    msg = Message(subject, sender=sender, recipients=recipients,
                  extra_headers=headers)
    msg.body = text_body
    msg.html = html_body
    if attachments:
        for attachment in attachments:
            msg.attach(*attachment)
    if sync:
        mail.send(msg)
    else:
        Thread(target=send_async_email,
               args=(current_app._get_current_object(), msg)).start()


def send_password_reset_email(user: User):
    """Send the reset link; returns False when mail is not configured."""
    if not mail_configured():
        return False
    site_name = site_text()['site_name']
    token = user.get_reset_password_token()
    context = {
        'user': user,
        'site_name': site_name,
        'reset_url': url_for('reset_password', token=token, _external=True),
        'expires_minutes': RESET_TOKEN_LIFETIME // 60,
    }
    send_email(f'[{site_name}] 重置你的密码',
               sender=(site_name, mail_sender()),
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt', **context),
               html_body=render_template('email/reset_password.html', **context))
    return True

