"""A read-only view of the mail Resend has sent and received.

Only GET requests are made. Resend's sending-only keys cannot list mail, so
the key must have Full access: keep it in the server's .env and nowhere else.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from flask import current_app

from app.search import plain_text

API = 'https://api.resend.com'
# Resend's gateway turns away urllib's default User-Agent.
USER_AGENT = 'flog-admin/1.0'
TIMEOUT = 8
PAGE_SIZE = 20
CACHE_SECONDS = 20
CACHE_LIMIT = 64

STATUS_LABELS = {
    'sent': '已发出', 'delivered': '已送达', 'delivery_delayed': '投递延迟',
    'bounced': '已退信', 'complained': '被投诉为垃圾邮件', 'failed': '发送失败',
    'opened': '已打开', 'clicked': '已点击', 'queued': '排队中',
    'scheduled': '已定时', 'canceled': '已取消', 'suppressed': '已被屏蔽',
}

_UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
                   r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
_cache = {}


class ResendError(Exception):
    """The message is meant for the administrator."""


class NotConfigured(ResendError):
    pass


class NotFound(ResendError):
    pass


@dataclass(frozen=True)
class MailItem:
    id: str
    sender: str
    to: list
    subject: str
    created_at: datetime | None
    status: str
    cc: list = field(default_factory=list)
    bcc: list = field(default_factory=list)
    reply_to: list = field(default_factory=list)
    text: str = ''
    attachments: list = field(default_factory=list)
    authentication: dict = field(default_factory=dict)
    message_id: str = ''


@dataclass(frozen=True)
class MailPage:
    items: list
    has_more: bool


def configured():
    return bool(current_app.config['RESEND_API_KEY'])


def is_valid_id(value):
    return bool(value) and _UUID.fullmatch(value) is not None


def clear_cache():
    _cache.clear()


def _http_error(code):
    if code in (401, 403):
        return ResendError('Resend 拒绝了密钥：需要 Full access 权限的密钥。')
    if code == 404:
        return NotFound('找不到这封邮件。')
    if code == 429:
        return ResendError('请求太频繁，稍后再试。')
    return ResendError(f'Resend 返回了错误（HTTP {code}）。')


def _get(path, params=None):
    key = current_app.config['RESEND_API_KEY']
    if not key:
        raise NotConfigured('还没有配置 RESEND_API_KEY。')
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    now = time.monotonic()
    cached = _cache.get(url)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    request = urllib.request.Request(url, method='GET', headers={
        'Authorization': f'Bearer {key}', 'Accept': 'application/json',
        'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        raise _http_error(error.code) from None
    except (OSError, ValueError):
        raise ResendError('无法连接 Resend。') from None
    if not isinstance(body, dict):
        raise ResendError('无法连接 Resend。')

    if len(_cache) >= CACHE_LIMIT:
        del _cache[min(_cache, key=lambda u: _cache[u][0])]
    _cache[url] = (now, body)
    return body


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(' ', 'T', 1)
    text = re.sub(r'Z$', '+00:00', text)
    text = re.sub(r'(T.*[+-]\d\d)$', r'\1:00', text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _body(record):
    text = record.get('text')
    if isinstance(text, str) and text.strip():
        return text.strip()
    html = record.get('html')
    if not isinstance(html, str):
        return ''
    return plain_text(re.sub(r'(?is)<(script|style)\b.*?</\1>', '', html))


def _attachments(value):
    result = []
    for entry in value if isinstance(value, list) else []:
        if isinstance(entry, dict):
            size = entry.get('size')
            result.append({
                'filename': str(entry.get('filename') or '（无文件名）'),
                'content_type': str(entry.get('content_type') or ''),
                'size': size if isinstance(size, int) else None})
    return result


def _authentication(value):
    if not isinstance(value, dict):
        return {}
    return {name: str(value[name]) for name in ('spf', 'dkim', 'dmarc')
            if value.get(name)}


def _item(record):
    if not isinstance(record, dict):
        record = {}
    event = record.get('last_event')
    event = event if isinstance(event, str) else ''
    return MailItem(
        id=str(record.get('id') or ''),
        sender=str(record.get('from') or ''),
        to=_as_list(record.get('to')),
        subject=str(record.get('subject') or ''),
        created_at=_parse_time(record.get('created_at')),
        status=STATUS_LABELS.get(event, event),
        cc=_as_list(record.get('cc')),
        bcc=_as_list(record.get('bcc')),
        reply_to=_as_list(record.get('reply_to')),
        text=_body(record),
        attachments=_attachments(record.get('attachments')),
        authentication=_authentication(record.get('authentication')),
        message_id=str(record.get('message_id') or ''))


def _list(path, after):
    params = {'limit': PAGE_SIZE}
    if is_valid_id(after):
        params['after'] = after
    body = _get(path, params)
    data = body.get('data')
    items = [_item(record) for record in data] if isinstance(data, list) else []
    return MailPage(items, bool(body.get('has_more')))


def _detail(path, email_id):
    if not is_valid_id(email_id):
        raise NotFound('找不到这封邮件。')
    return _item(_get(f'{path}/{email_id}'))


def list_sent(after=None):
    return _list('/emails', after)


def list_received(after=None):
    return _list('/emails/receiving', after)


def get_sent(email_id):
    return _detail('/emails', email_id)


def get_received(email_id):
    return _detail('/emails/receiving', email_id)
