import io
import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from lxml import html as lxml_html

from app import resend_client
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
FIRST = '11111111-1111-4111-8111-111111111111'
SECOND = '22222222-2222-4222-8222-222222222222'
THIRD = '33333333-3333-4333-8333-333333333333'


class Response(io.BytesIO):
    """What urlopen returns: readable, and usable in a with block."""


class FakeResend:
    """Stands in for urlopen: records requests, answers from a path table."""

    def __init__(self):
        self.requests = []
        self.routes = {}

    def json(self, path, body):
        self.routes[path] = Response(json.dumps(body).encode())

    def raw(self, path, data):
        self.routes[path] = Response(data)

    def fail(self, path, error):
        self.routes[path] = error

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        entry = self.routes.get(urlparse(request.full_url).path)
        if entry is None:
            raise AssertionError(f'unexpected request: {request.full_url}')
        if isinstance(entry, BaseException):
            raise entry
        return Response(entry.getvalue())

    def query(self, index=-1):
        return parse_qs(urlparse(self.requests[index].full_url).query)


def http_error(code):
    return urllib.error.HTTPError(
        'https://api.resend.com/x', code, 'err', {}, io.BytesIO(b'{}'))


@pytest.fixture()
def resend(application, monkeypatch):
    monkeypatch.setitem(application.config, 'RESEND_API_KEY', 're_test_key')
    resend_client.clear_cache()
    fake = FakeResend()
    monkeypatch.setattr('app.resend_client.urllib.request.urlopen', fake)
    yield fake
    resend_client.clear_cache()


def sent_item(email_id, subject='Hello', event='delivered', **extra):
    return {'id': email_id, 'from': "Aisaka's Blog <noreply@aisaka.cc>",
            'to': ['reader@example.com'], 'subject': subject,
            'created_at': '2026-11-07 06:45:12.123456+00',
            'last_event': event, **extra}


def received_item(email_id, subject='你好'):
    return {'id': email_id, 'from': 'Ann <ann@example.org>',
            'to': ['admin@aisaka.cc'], 'subject': subject,
            'created_at': '2026-11-07T07:00:00.000Z'}


def page_of(client, path):
    response = client.get(path)
    return response, lxml_html.fromstring(response.get_data(as_text=True))


def rows(page):
    return page.xpath('//article[@data-mail-row]')


@pytest.fixture()
def admin_client(client, users):
    login(client, 'admin')
    return client


# --- access and configuration ---------------------------------------------

def test_visitors_are_sent_to_log_in(client, resend):
    response = client.get('/admin/mail')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert resend.requests == []


def test_members_are_refused(client, users, resend):
    login(client, 'author')
    assert client.get('/admin/mail').status_code == 403
    assert resend.requests == []


def test_admin_navigation_has_a_mail_link(admin_client, resend):
    resend.json('/emails', {'data': [], 'has_more': False})
    _, page = page_of(admin_client, '/admin/mail')
    assert page.xpath('//nav[@aria-label="管理导航"]//a[contains(., "邮件")]')


def test_without_a_key_the_page_explains_and_calls_nothing(
        admin_client, application, resend, monkeypatch):
    monkeypatch.setitem(application.config, 'RESEND_API_KEY', '')
    response, page = page_of(admin_client, '/admin/mail')
    assert response.status_code == 200
    assert 'RESEND_API_KEY' in page.text_content()
    assert resend.requests == []


def test_key_is_a_documented_setting(application):
    from config import Config
    assert Config.RESEND_API_KEY == '' or isinstance(Config.RESEND_API_KEY, str)
    assert 'RESEND_API_KEY' in (ROOT / '.env.example').read_text()
    assert 'RESEND_API_KEY' in (ROOT / 'README.md').read_text()


# --- lists ------------------------------------------------------------------

def test_sent_list_shows_the_mails(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': [
        sent_item(FIRST, '[Aisaka] 重置你的密码'),
        sent_item(SECOND, '<b>bold</b> & more', event='bounced')]})
    response, page = page_of(admin_client, '/admin/mail')
    assert response.status_code == 200
    first, second = rows(page)
    text = first.text_content()
    assert 'noreply@aisaka.cc' in text and 'reader@example.com' in text
    assert '重置你的密码' in text and '已送达' in text
    assert '2026-11-07 14:45' in text
    assert '已退信' in second.text_content()
    assert '<b>bold</b>' not in response.get_data(as_text=True)
    assert '&lt;b&gt;bold&lt;/b&gt;' in response.get_data(as_text=True)
    assert first.xpath(f'.//a[@href="/admin/mail/sent/{FIRST}"]')


def test_received_list_uses_the_receiving_endpoint(admin_client, resend):
    resend.json('/emails/receiving', {'has_more': False,
                                       'data': [received_item(FIRST)]})
    _, page = page_of(admin_client, '/admin/mail?box=received')
    (row,) = rows(page)
    assert 'ann@example.org' in row.text_content()
    assert '2026-11-07 15:00' in row.text_content()
    assert row.xpath(f'.//a[@href="/admin/mail/received/{FIRST}"]')
    assert urlparse(resend.requests[0].full_url).path == '/emails/receiving'


def test_unknown_box_falls_back_to_sent(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': [sent_item(FIRST)]})
    response, page = page_of(admin_client, '/admin/mail?box=trash')
    assert response.status_code == 200
    assert len(rows(page)) == 1
    assert urlparse(resend.requests[0].full_url).path == '/emails'


def test_empty_list_says_so(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': []})
    _, page = page_of(admin_client, '/admin/mail')
    assert rows(page) == []
    assert '还没有邮件' in page.text_content()


def test_more_mail_links_to_the_next_page_and_back_to_latest(
        admin_client, resend):
    resend.json('/emails', {'has_more': True, 'data': [
        sent_item(FIRST), sent_item(SECOND)]})
    _, page = page_of(admin_client, '/admin/mail')
    older = page.xpath('//a[contains(., "较早的邮件")]')
    assert older
    assert f'after={SECOND}' in older[0].get('href')
    assert 'box=sent' in older[0].get('href')
    assert not page.xpath('//a[contains(., "回到最新")]')

    resend.json('/emails', {'has_more': False, 'data': [sent_item(THIRD)]})
    _, page = page_of(admin_client, f'/admin/mail?after={SECOND}')
    assert resend.query() == {'limit': ['20'], 'after': [SECOND]}
    assert page.xpath('//a[contains(., "回到最新")]')
    assert not page.xpath('//a[contains(., "较早的邮件")]')


def test_a_bad_cursor_is_ignored(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': []})
    response, _ = page_of(admin_client, '/admin/mail?after=../../keys')
    assert response.status_code == 200
    assert 'after' not in resend.query()


def test_identical_lists_are_fetched_once(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': [sent_item(FIRST)]})
    admin_client.get('/admin/mail')
    admin_client.get('/admin/mail')
    assert len(resend.requests) == 1


# --- details ----------------------------------------------------------------

def test_sent_detail_shows_headers_and_escaped_text(admin_client, resend):
    resend.json(f'/emails/{FIRST}', sent_item(
        FIRST, 'Hi', text='hello <script>alert(1)</script>', html=None,
        cc=['cc@example.com'], bcc=[], reply_to=['reply@example.com']))
    response, page = page_of(admin_client, f'/admin/mail/sent/{FIRST}')
    assert response.status_code == 200
    body = page.xpath('//pre[@class="mail-body"]')[0]
    assert 'hello <script>alert(1)</script>' in body.text_content()
    assert not body.xpath('.//script')
    assert '&lt;script&gt;' in response.get_data(as_text=True)
    text = page.text_content()
    for expected in ('noreply@aisaka.cc', 'reader@example.com',
                     'cc@example.com', 'reply@example.com', '已送达',
                     '2026-11-07 14:45'):
        assert expected in text
    link = page.xpath(f'//a[@href="https://resend.com/emails/{FIRST}"]')[0]
    assert 'noopener' in link.get('rel')


def test_html_only_mail_is_shown_as_text(admin_client, resend):
    resend.json(f'/emails/{FIRST}', sent_item(
        FIRST, 'Hi', text=None,
        html='<p>Hi <b>there</b></p><script>evil()</script>'))
    _, page = page_of(admin_client, f'/admin/mail/sent/{FIRST}')
    body = page.xpath('//pre[@class="mail-body"]')[0]
    assert 'Hi there' in body.text_content()
    assert 'evil' not in body.text_content()
    assert not body.xpath('.//script') and not body.xpath('.//b')


def test_received_detail_shows_authentication_and_attachments(
        admin_client, resend):
    resend.json(f'/emails/receiving/{FIRST}', {
        **received_item(FIRST), 'text': '嗨', 'html': None, 'cc': [],
        'bcc': [], 'reply_to': [],
        'attachments': [{'id': 'a1', 'filename': 'invoice.pdf',
                         'content_type': 'application/pdf', 'size': 2048}],
        'authentication': {'spf': 'pass', 'dkim': 'pass', 'dmarc': 'gray'}})
    response, page = page_of(admin_client, f'/admin/mail/received/{FIRST}')
    assert response.status_code == 200
    text = page.text_content()
    for expected in ('invoice.pdf', 'application/pdf', 'SPF', 'DKIM', 'DMARC',
                     'gray', 'ann@example.org', '嗨'):
        assert expected in text
    assert page.xpath(
        f'//a[@href="https://resend.com/emails/receiving/{FIRST}"]')


def test_detail_survives_missing_fields(admin_client, resend):
    resend.json(f'/emails/receiving/{FIRST}', {'id': FIRST})
    response, _ = page_of(admin_client, f'/admin/mail/received/{FIRST}')
    assert response.status_code == 200


@pytest.mark.parametrize('path', [
    '/admin/mail/sent/not-a-uuid',
    '/admin/mail/sent/../../api-keys',
    f'/admin/mail/inbox/{FIRST}',
])
def test_bad_detail_addresses_are_404_without_a_request(
        admin_client, resend, path):
    assert admin_client.get(path).status_code == 404
    assert resend.requests == []


def test_unknown_mail_is_404(admin_client, resend):
    resend.fail(f'/emails/{FIRST}', http_error(404))
    assert admin_client.get(f'/admin/mail/sent/{FIRST}').status_code == 404


# --- failures ---------------------------------------------------------------

@pytest.mark.parametrize('error, message', [
    (http_error(401), 'Full access'),
    (http_error(403), 'Full access'),
    (http_error(429), '太频繁'),
    (http_error(500), 'HTTP 500'),
    (urllib.error.URLError('no route'), '无法连接'),
    (TimeoutError(), '无法连接'),
])
def test_api_errors_are_shown_not_raised(admin_client, resend, error, message):
    resend.fail('/emails', error)
    response, page = page_of(admin_client, '/admin/mail')
    assert response.status_code == 200
    assert message in page.xpath('//div[contains(@class, "admin-notice")]')[0].text_content()
    assert rows(page) == []


def test_a_reply_that_is_not_json_is_a_connection_problem(admin_client, resend):
    resend.raw('/emails', b'<html>blocked</html>')
    response, page = page_of(admin_client, '/admin/mail')
    assert response.status_code == 200
    assert '无法连接' in page.text_content()


# --- the key is only ever used to read --------------------------------------

def test_requests_are_authenticated_gets_to_resend(admin_client, resend):
    resend.json('/emails', {'has_more': False, 'data': [sent_item(FIRST)]})
    resend.json(f'/emails/{FIRST}', sent_item(FIRST, text='x'))
    resend.json('/emails/receiving', {'has_more': False, 'data': []})
    resend.json(f'/emails/receiving/{FIRST}', {'id': FIRST})
    for path in ('/admin/mail', f'/admin/mail/sent/{FIRST}',
                 '/admin/mail?box=received', f'/admin/mail/received/{FIRST}'):
        admin_client.get(path)
    assert len(resend.requests) == 4
    for request in resend.requests:
        assert request.get_method() == 'GET'
        assert request.data is None
        assert urlparse(request.full_url).netloc == 'api.resend.com'
        assert request.get_header('Authorization') == 'Bearer re_test_key'
        assert request.get_header('User-agent')
        assert 'python-urllib' not in request.get_header('User-agent').lower()
