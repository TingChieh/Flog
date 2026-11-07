import jwt
import pytest

from app import app, db, mail
from app.models import User


def request_reset(client, email):
    return client.post('/reset_password_request', data={'email': email})


def token_from(message):
    return message.body.split('/reset_password/')[1].split()[0]


def test_reset_email_uses_site_style_and_mail_username(client, outbox):
    request_reset(client, 'author@example.com')
    (message,) = outbox
    assert message.recipients == ['author@example.com']
    assert message.sender == "Aisaka's Blog <noreply@example.com>"
    assert message.subject == "[Aisaka's Blog] 重置你的密码"
    assert '/reset_password/' in message.html
    assert '10 分钟内有效，且只能使用一次' in message.body
    assert '#f2f1ef' in message.html and '#fbfaf8' in message.html
    assert 'prefers-color-scheme: dark' in message.html


def test_unknown_address_gets_the_same_answer_and_no_mail(client, outbox):
    known = request_reset(client, 'author@example.com')
    outbox.clear()
    unknown = request_reset(client, 'nobody@example.com')
    assert outbox == []
    assert unknown.status_code == known.status_code == 302
    assert unknown.headers['Location'] == known.headers['Location']


def test_sender_falls_back_to_first_admin(client, application, outbox,
                                          monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_USERNAME', 'smtp-api-key')
    request_reset(client, 'author@example.com')
    assert outbox[0].sender.endswith('<admin@example.com>')


@pytest.mark.parametrize('overrides', [
    {'MAIL_SERVER': ''},
    {'MAIL_USERNAME': 'smtp-api-key', 'ADMINS': []},
])
def test_unconfigured_mail_is_reported_not_sent(client, application, outbox,
                                                monkeypatch, overrides):
    for key, value in overrides.items():
        monkeypatch.setitem(application.config, key, value)
    response = request_reset(client, 'author@example.com')
    assert outbox == []
    assert response.headers['Location'].endswith('/login')
    page = client.get('/login').get_data(as_text=True)
    assert '暂时无法通过邮件重置密码' in page
    assert '检查你的电子邮箱' not in page


def test_reset_link_works_once(client, outbox):
    request_reset(client, 'author@example.com')
    token = token_from(outbox[0])
    data = {'password': 'brand-new-pw', 'password2': 'brand-new-pw'}
    assert client.get(f'/reset_password/{token}').status_code == 200
    first = client.post(f'/reset_password/{token}', data=data)
    assert first.headers['Location'].endswith('/login')
    with app.app_context():
        assert User.query.filter_by(
            email='author@example.com').one().check_password('brand-new-pw')
    again = client.get(f'/reset_password/{token}')
    assert again.status_code == 302
    assert again.headers['Location'].endswith('/index')
    assert '无效或已过期' in client.get('/index').get_data(as_text=True)


def test_reset_token_without_password_binding_is_rejected(application, users):
    legacy = jwt.encode({'reset_password': users['author'], 'exp': 9999999999},
                        application.config['SECRET_KEY'], algorithm='HS256')
    assert User.verify_reset_password_token(legacy) is None


def test_failed_background_send_is_logged(application, users, outbox,
                                          monkeypatch, caplog):
    def boom(message):
        raise OSError('smtp down')

    monkeypatch.setattr(mail, 'send', boom)
    with application.test_request_context():
        from app.email import send_password_reset_email
        send_password_reset_email(db.session.get(User, users['author']))
    assert 'Could not send email' in caplog.text
