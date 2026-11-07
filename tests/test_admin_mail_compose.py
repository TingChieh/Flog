from pathlib import Path

import pytest
from lxml import html as lxml_html

from app import mail
from tests.conftest import login
# Fixtures and helpers shared with the read-only mail page tests.
from tests.test_admin_mail import (FIRST, admin_client, http_error,  # noqa: F401
                                   received_item, resend)

ROOT = Path(__file__).resolve().parents[1]
MESSAGE_ID = '<abc123.def@mail.example.org>'


@pytest.fixture()
def senders(application, outbox, monkeypatch):
    """Mail is configured and two personal addresses may be used to send."""
    monkeypatch.setitem(application.config, 'MAIL_FROM', 'noreply@aisaka.cc')
    monkeypatch.setitem(application.config, 'MAIL_SENDERS',
                        ['admin@aisaka.cc', 'tingchieh@aisaka.cc'])
    return outbox


def page_of(client, path):
    response = client.get(path)
    return response, lxml_html.fromstring(response.get_data(as_text=True))


def compose(client, **overrides):
    data = {'sender': 'tingchieh@aisaka.cc', 'to': 'friend@example.com',
            'subject': 'Hello', 'body': 'Just saying hi.'}
    data.update(overrides)
    return client.post('/admin/mail/compose', data=data)


def received_detail(**extra):
    return {**received_item(FIRST, '想请教一个问题'), 'text': '嗨\n第二行',
            'html': None, 'cc': [], 'bcc': [], 'reply_to': [],
            'attachments': [], 'message_id': MESSAGE_ID, **extra}


# --- access ----------------------------------------------------------------

def test_visitors_and_members_cannot_compose(client, users, senders):
    assert client.get('/admin/mail/compose').status_code == 302
    assert compose(client).status_code == 302
    login(client, 'author')
    assert client.get('/admin/mail/compose').status_code == 403
    assert compose(client).status_code == 403
    assert senders == []


# --- the form --------------------------------------------------------------

def test_form_offers_the_configured_senders(admin_client, senders):
    response, page = page_of(admin_client, '/admin/mail/compose')
    assert response.status_code == 200
    options = [o.get('value') for o in page.xpath('//select[@name="sender"]/option')]
    assert options == ['admin@aisaka.cc', 'tingchieh@aisaka.cc', 'noreply@aisaka.cc']
    for name in ('to', 'subject', 'body'):
        assert page.xpath(f'//*[@name="{name}"]')


def test_without_mail_the_page_says_so_and_has_no_form(
        admin_client, application, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    response, page = page_of(admin_client, '/admin/mail/compose')
    assert response.status_code == 200
    assert 'MAIL_SERVER' in page.text_content()
    assert not page.xpath('//textarea[@name="body"]')
    assert compose(admin_client).status_code == 200


# --- sending ---------------------------------------------------------------

def test_sending_uses_the_chosen_address_and_plain_text(admin_client, senders):
    response = compose(admin_client, to='friend@example.com')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/mail?box=sent')
    (message,) = senders
    assert message.sender == 'tingchieh@aisaka.cc'
    assert message.recipients == ['friend@example.com']
    assert message.subject == 'Hello'
    assert message.body == 'Just saying hi.'
    assert not message.html
    page = admin_client.get('/admin/mail?box=sent').get_data(as_text=True)
    assert '邮件已发送' in page


def test_several_recipients_are_split_on_commas_and_semicolons(
        admin_client, senders):
    compose(admin_client, to='a@example.com, b@example.com;c@example.com')
    assert senders[0].recipients == ['a@example.com', 'b@example.com',
                                     'c@example.com']


@pytest.mark.parametrize('overrides', [
    {'sender': 'ceo@aisaka.cc'},
    {'sender': 'someone@gmail.com'},
    {'to': ''},
    {'to': 'not-an-address'},
    {'to': 'a@example.com\nBcc: spy@example.com'},
    {'to': ', '.join(f'u{i}@example.com' for i in range(11))},
    {'subject': ''},
    {'subject': 'Hi\r\nBcc: spy@example.com'},
    {'subject': 'x' * 201},
    {'body': ''},
])
def test_bad_input_is_refused_and_nothing_is_sent(
        admin_client, senders, overrides):
    response = compose(admin_client, **overrides)
    assert response.status_code == 200
    assert senders == []
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert page.xpath('//div[contains(@class, "invalid-feedback")]')


def test_ten_recipients_are_allowed(admin_client, senders):
    compose(admin_client, to=', '.join(f'u{i}@example.com' for i in range(10)))
    assert len(senders[0].recipients) == 10


def test_a_failed_send_is_reported_without_leaking_details(
        admin_client, senders, monkeypatch, caplog):
    def boom(message):
        raise OSError('smtp down at 10.0.0.9')

    monkeypatch.setattr(mail, 'send', boom)
    response = compose(admin_client)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert '发送失败' in text
    assert '10.0.0.9' not in text
    assert 'Could not send mail from the admin page' in caplog.text


# --- replying ---------------------------------------------------------------

def test_reply_prefills_the_form(admin_client, senders, resend):
    resend.json(f'/emails/receiving/{FIRST}', received_detail(
        to=['admin@aisaka.cc']))
    response, page = page_of(admin_client, f'/admin/mail/compose?reply={FIRST}')
    assert response.status_code == 200
    assert page.xpath('//input[@name="to"]')[0].get('value') == 'ann@example.org'
    assert page.xpath('//input[@name="subject"]')[0].get('value') == 'Re: 想请教一个问题'
    selected = page.xpath('//select[@name="sender"]/option[@selected]')
    assert [o.get('value') for o in selected] == ['admin@aisaka.cc']
    body = page.xpath('//textarea[@name="body"]')[0].text_content()
    assert '写道' in body and '> 嗨' in body and '> 第二行' in body
    assert page.xpath('//input[@name="in_reply_to"]')[0].get('value') == MESSAGE_ID


def test_reply_goes_to_the_reply_to_address_when_there_is_one(
        admin_client, senders, resend):
    resend.json(f'/emails/receiving/{FIRST}', received_detail(
        reply_to=['Support <support@example.org>']))
    _, page = page_of(admin_client, f'/admin/mail/compose?reply={FIRST}')
    assert page.xpath('//input[@name="to"]')[0].get('value') == 'support@example.org'


def test_reply_subject_is_not_prefixed_twice(admin_client, senders, resend):
    resend.json(f'/emails/receiving/{FIRST}', received_detail(
        **{'subject': 'RE: already'}))
    _, page = page_of(admin_client, f'/admin/mail/compose?reply={FIRST}')
    assert page.xpath('//input[@name="subject"]')[0].get('value') == 'RE: already'


def test_reply_to_a_mail_for_another_address_uses_the_first_sender(
        admin_client, senders, resend):
    resend.json(f'/emails/receiving/{FIRST}', received_detail(
        to=['someone-else@aisaka.cc']))
    _, page = page_of(admin_client, f'/admin/mail/compose?reply={FIRST}')
    selected = page.xpath('//select[@name="sender"]/option[@selected]')
    assert selected == [] or selected[0].get('value') == 'admin@aisaka.cc'


def test_a_sent_reply_carries_the_thread_headers(admin_client, senders):
    compose(admin_client, in_reply_to=MESSAGE_ID, references=MESSAGE_ID)
    headers = senders[0].extra_headers
    assert headers['In-Reply-To'] == MESSAGE_ID
    assert headers['References'] == MESSAGE_ID


@pytest.mark.parametrize('value', [
    'garbage', '<a b@c>', MESSAGE_ID + '\r\nBcc: spy@example.com', '<' + 'x' * 300 + '>'])
def test_forged_thread_headers_are_dropped(admin_client, senders, value):
    compose(admin_client, in_reply_to=value, references=value)
    assert len(senders) == 1
    assert 'In-Reply-To' not in (senders[0].extra_headers or {})
    assert 'References' not in (senders[0].extra_headers or {})


def test_reply_page_survives_a_resend_error(admin_client, senders, resend):
    resend.fail(f'/emails/receiving/{FIRST}', http_error(401))
    response, page = page_of(admin_client, f'/admin/mail/compose?reply={FIRST}')
    assert response.status_code == 200
    assert 'Full access' in page.text_content()
    assert page.xpath('//textarea[@name="body"]')


def test_a_bad_reply_id_is_ignored(admin_client, senders, resend):
    response, page = page_of(admin_client, '/admin/mail/compose?reply=../../keys')
    assert response.status_code == 200
    assert page.xpath('//input[@name="to"]')[0].get('value') in (None, '')
    assert resend.requests == []


# --- buttons ----------------------------------------------------------------

def test_list_offers_compose_only_when_mail_is_configured(
        admin_client, senders, resend):
    resend.json('/emails', {'has_more': False, 'data': []})
    _, page = page_of(admin_client, '/admin/mail')
    assert page.xpath('//a[@href="/admin/mail/compose"]')


def test_list_hides_compose_without_mail(admin_client, application, resend,
                                         monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    resend.json('/emails', {'has_more': False, 'data': []})
    _, page = page_of(admin_client, '/admin/mail')
    assert not page.xpath('//a[@href="/admin/mail/compose"]')


def test_received_detail_has_a_reply_button_and_sent_detail_does_not(
        admin_client, senders, resend):
    resend.json(f'/emails/receiving/{FIRST}', received_detail())
    resend.json(f'/emails/{FIRST}', received_detail())
    _, received = page_of(admin_client, f'/admin/mail/received/{FIRST}')
    _, sent = page_of(admin_client, f'/admin/mail/sent/{FIRST}')
    assert received.xpath(f'//a[@href="/admin/mail/compose?reply={FIRST}"]')
    assert not sent.xpath('//a[contains(@href, "compose")]')


def test_sending_refreshes_the_sent_list(admin_client, senders, resend):
    resend.json('/emails', {'has_more': False, 'data': []})
    admin_client.get('/admin/mail')
    compose(admin_client)
    admin_client.get('/admin/mail')
    assert len(resend.requests) == 2


# --- settings ---------------------------------------------------------------

def test_senders_setting_is_documented(application):
    assert 'MAIL_SENDERS' in (ROOT / '.env.example').read_text()
    assert 'MAIL_SENDERS' in (ROOT / 'README.md').read_text()
    assert isinstance(application.config['MAIL_SENDERS'], list)
