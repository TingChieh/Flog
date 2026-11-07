import json
import os
import subprocess
import sys
from pathlib import Path

from app.email import mail_configured, mail_sender


def test_mail_from_is_a_config_setting(application):
    assert 'MAIL_FROM' in application.config


def test_mail_from_wins_over_username_and_admins(application, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_FROM', 'blog@example.com')
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'login@example.com')
    monkeypatch.setitem(application.config, 'ADMINS', ['admin@example.com'])
    with application.app_context():
        assert mail_sender() == 'blog@example.com'


def test_blank_mail_from_falls_back_to_username_then_admin(
        application, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_FROM', '')
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'login@example.com')
    with application.app_context():
        assert mail_sender() == 'login@example.com'
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'resend')
    monkeypatch.setitem(application.config, 'ADMINS', ['admin@example.com'])
    with application.app_context():
        assert mail_sender() == 'admin@example.com'


def test_api_key_style_login_works_with_mail_from_alone(
        application, monkeypatch):
    """Resend logs in as the word "resend" and sends from a verified address."""
    monkeypatch.setitem(application.config, 'MAIL_SERVER', 'smtp.resend.com')
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'resend')
    monkeypatch.setitem(application.config, 'ADMINS', [])
    with application.app_context():
        assert not mail_configured()
        monkeypatch.setitem(application.config, 'MAIL_FROM',
                            'noreply@example.com')
        assert mail_configured()


def test_reset_email_is_sent_from_mail_from(client, application, outbox,
                                            monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'resend')
    monkeypatch.setitem(application.config, 'MAIL_FROM', 'noreply@example.com')
    client.post('/reset_password_request',
                data={'email': 'author@example.com'})
    assert outbox[0].sender == "Aisaka's Blog <noreply@example.com>"


def test_error_mails_are_sent_from_mail_from(tmp_path):
    """The failure notifier must not use a login that is not an address."""
    root = Path(__file__).parents[1]
    environment = dict(os.environ, SECRET_KEY='x', DATABASE_URL='sqlite://',
                       ADMIN_EMAILS='admin@example.com',
                       MAIL_SERVER='smtp.resend.com', MAIL_USERNAME='resend',
                       MAIL_PASSWORD='re_secret', MAIL_FROM='noreply@example.com')
    script = (
        'import json, logging; from app import app; '
        'from app.email_handler import SMTP_SSLHandler; '
        'handlers = [h for h in app.logger.handlers '
        'if isinstance(h, SMTP_SSLHandler)]; '
        'print(json.dumps([h.fromaddr for h in handlers]))')
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=tmp_path, env=dict(
            environment, PYTHONPATH=str(root)),
        check=True, capture_output=True, text=True)
    assert json.loads(result.stdout.splitlines()[-1]) == ['noreply@example.com']
