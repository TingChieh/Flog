# Comment Emails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send four kinds of comment emails (new comment → site owner and post author, reply → answered commenter, approval → commenter), with an opt-in checkbox and a one-click-confirm unsubscribe for commenters.

**Architecture:** A new `app/comment_mail.py` decides who is told what and renders shared HTML email templates (a `base.html` extracted from the password reset email). Two new `post_comment` columns (`notify_replies`, `answered_id`) record consent and who a reply answers. The routes call the three `notify_*` entry points after `db.session.commit()`; every entry point swallows and logs errors so mail never breaks a request.

**Tech Stack:** Flask 3, Flask-Mail, Flask-WTF, SQLAlchemy 2, Alembic, Jinja2, itsdangerous, pytest. Run Python with `.venv/bin/python`.

**Spec:** `docs/superpowers/specs/2026-11-07-comment-emails-design.md`

## Global Constraints

- The site is Chinese-only; every new user-facing string (form labels, flashes, email text) is plain Simplified Chinese, like the existing comment code. No `.po`/`.mo` changes.
- Mail is optional: when `mail_configured()` is false every comment email is silently skipped and comments work as before.
- Emails to commenters are sent only when `PostComment.notify_replies` is true; unsubscribing sets it false for every comment of that email (compared lowercase).
- One email per recipient (never several addresses in one `To`); recipients are de-duplicated by lowercase address and never include the commenter's own address.
- Comment text in emails is plain text, escaped, truncated to 300 characters plus `……`.
- Emails reuse the site look from `app/templates/email/reset_password.html` (palette `#f2f1ef` / `#fbfaf8` / `#1c1915` / `#746d48`, serif stack, dark mode via `prefers-color-scheme`).
- Never commit inside `app/comments.py`; the caller owns the transaction (existing rule).
- Tests run against SQLite in memory; anything that touches mail uses the `outbox` fixture (Task 2), which must never leak config into other tests.

## Before you start

The working tree must be clean so each task's commit contains only that task's files. The password-reset fixes and the two docs are still uncommitted from earlier work. If `git status --short` is not empty, commit them first:

```bash
cd /Users/tingchieh/cs-learning/flog
git status --short
git add app/email.py app/models.py app/routes.py app/templates/email app/translations README.md tests/test_password_reset_email.py
git commit -m "fix(email): single-use reset links, site-styled reset email, clear mail-not-configured message"
git add docs/superpowers/specs/2026-11-07-comment-emails-design.md docs/superpowers/plans/2026-11-07-comment-emails.md
git commit -m "docs: comment emails design and plan"
git status --short   # expect: nothing
```

## File Structure

| File | Responsibility |
| --- | --- |
| `migrations/versions/d7b3a9e41c58_add_comment_notifications.py` (new) | Adds `notify_replies` and `answered_id` |
| `app/models.py` | `PostComment` columns and relationships |
| `app/comments.py` | `submit_comment` stores `notify_replies`, `answered_id` |
| `app/forms.py` | `PostCommentForm.notify`, `CommentUnsubscribeForm` |
| `app/templates/_comments.html`, `app/static/style.css` | The checkbox |
| `app/email.py` | `send_email(headers=...)` |
| `app/templates/email/base.html`, `_parts.html` (new) | Shared HTML email shell and macros |
| `app/templates/email/reset_password.html` | Now extends the base |
| `app/comment_mail.py` (new) | Unsubscribe tokens, recipient rules, three `notify_*` entry points |
| `app/templates/email/comment_{new,reply,approved}.{html,txt}` (new) | The three comment emails |
| `app/templates/user/comment_unsubscribe.html` (new) | Unsubscribe confirmation page |
| `app/routes.py` | Pass `notify`, call notifiers, unsubscribe route, robots |
| `app/admin/modules.py` | Call notifiers after reply / approve / bulk approve |
| `tests/conftest.py` | Shared `outbox` fixture |
| `tests/test_comment_mail.py`, `tests/test_comment_unsubscribe.py`, `tests/test_comment_email_flow.py` (new) | Tests |

---

### Task 1: Store consent and who a reply answers

**Files:**
- Create: `migrations/versions/d7b3a9e41c58_add_comment_notifications.py`
- Modify: `app/models.py` (class `PostComment`), `app/comments.py` (`submit_comment`), `app/forms.py` (`PostCommentForm`), `app/templates/_comments.html`, `app/static/style.css`, `app/routes.py` (`_take_comment`)
- Test: `tests/test_migrations.py`, `tests/test_comment_service.py`, `tests/test_comments_public.py`

**Interfaces:**
- Produces: `PostComment.notify_replies: bool` (default False), `PostComment.answered_id: int | None`, `PostComment.answered: PostComment | None`; `submit_comment(..., notify_replies=False)`; `PostCommentForm.notify` (BooleanField, default unchecked).

- [ ] **Step 1: Write the failing tests**

In `tests/test_migrations.py`, change the head assertion (around line 283) to the new revision:

```python
    assert ScriptDirectory.from_config(config).get_heads() == [
        'd7b3a9e41c58']
```

Append at the end of `tests/test_migrations.py`:

```python
NOTIFY_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'd7b3a9e41c58_add_comment_notifications.py')


def load_notify_revision():
    spec = importlib.util.spec_from_file_location(
        'comment_notifications', NOTIFY_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comment_notification_migration_adds_and_removes_columns():
    revision = load_notify_revision()
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE post_comment '
            '(id INTEGER PRIMARY KEY, name VARCHAR(64) NOT NULL)'))
        connection.execute(sa.text(
            "INSERT INTO post_comment (id, name) VALUES (1, 'A')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            columns = {c['name'] for c in
                       sa.inspect(connection).get_columns('post_comment')}
            assert {'notify_replies', 'answered_id'} <= columns
            assert tuple(connection.execute(sa.text(
                'SELECT notify_replies, answered_id FROM post_comment'
            )).one()) == (0, None)

            revision.downgrade()

            columns = {c['name'] for c in
                       sa.inspect(connection).get_columns('post_comment')}
            assert columns == {'id', 'name'}
```

Append to `tests/test_comment_service.py`:

```python
def test_reply_records_who_was_answered(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        top = make_comment(post.id, name='Top', email='top@example.com')
        first = make_comment(post.id, name='First', email='first@example.com',
                             parent_id=top.id)

        to_top = send(post, parent_id=top.id, body='to the top one')
        assert to_top.comment.parent_id == top.id
        assert to_top.comment.answered_id == top.id

        to_reply = send(post, parent_id=first.id, body='to the reply')
        assert to_reply.comment.parent_id == top.id
        assert to_reply.comment.answered_id == first.id

        plain = send(post, body='not a reply')
        assert plain.comment.answered_id is None


def test_notify_replies_is_stored_and_defaults_off(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        assert send(post, body='one').comment.notify_replies is False
        assert send(post, body='two', notify_replies=True
                    ).comment.notify_replies is True
```

Append to `tests/test_comments_public.py`:

```python
def test_comment_form_has_an_unchecked_notify_box(client, users):
    page = page_for(client, f'/post/{users["post"]}')
    boxes = page.xpath('//form[@data-comment-form]//input[@type="checkbox"][@name="notify"]')
    assert len(boxes) == 1
    assert boxes[0].get('checked') is None


def test_notify_box_is_remembered(client, application, users):
    post_comment(client, users['post'], notify='y')
    with application.app_context():
        assert db.session.scalar(db.select(PostComment)).notify_replies is True


def test_comment_without_notify_box_stays_silent(client, application, users):
    post_comment(client, users['post'])
    with application.app_context():
        assert db.session.scalar(db.select(PostComment)).notify_replies is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrations.py tests/test_comment_service.py tests/test_comments_public.py -q -k "notif or answered or notify"`
Expected: FAIL (missing migration file / unknown `notify_replies` / `submit_comment() got an unexpected keyword argument`).

- [ ] **Step 3: Write the migration**

Create `migrations/versions/d7b3a9e41c58_add_comment_notifications.py`:

```python
"""comment email notifications: consent flag and the comment a reply answers"""
from alembic import op
import sqlalchemy as sa


revision = 'd7b3a9e41c58'
down_revision = 'a1d9c3e5f7b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post_comment') as batch:
        batch.add_column(sa.Column(
            'notify_replies', sa.Boolean(), nullable=False,
            server_default=sa.false()))
        batch.add_column(sa.Column('answered_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_post_comment_answered_id_post_comment', 'post_comment',
            ['answered_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_post_comment_answered_id', ['answered_id'])


def downgrade():
    with op.batch_alter_table('post_comment') as batch:
        # MySQL will not drop an index a foreign key still relies on.
        batch.drop_constraint(
            'fk_post_comment_answered_id_post_comment', type_='foreignkey')
        batch.drop_index('ix_post_comment_answered_id')
        batch.drop_column('answered_id')
        batch.drop_column('notify_replies')
```

- [ ] **Step 4: Update the model**

In `app/models.py`, in `PostComment`, after the `user_id` column (the one preceded by the comment `# Set only when the site owner wrote it while signed in.`) add:

```python
    # Set when the commenter ticked "email me"; unsubscribing clears it.
    notify_replies: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    # The comment this one answers: its top-level comment, or the reply it
    # was written to. parent_id alone cannot say which reply was meant.
    answered_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('post_comment.id', ondelete='SET NULL'), index=True)
```

Replace the `parent` and `replies` relationships (there are now two foreign keys to the same table, so each must name its own) and add `answered`:

```python
    parent: so.Mapped[Optional['PostComment']] = so.relationship(
        back_populates='replies', remote_side='PostComment.id',
        foreign_keys='PostComment.parent_id')
    replies: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='parent', cascade='all, delete',
        order_by='PostComment.timestamp',
        foreign_keys='PostComment.parent_id')
    answered: so.Mapped[Optional['PostComment']] = so.relationship(
        remote_side='PostComment.id', foreign_keys='PostComment.answered_id')
```

- [ ] **Step 5: Update `submit_comment`**

In `app/comments.py`, change the signature and the part that resolves the parent:

```python
def submit_comment(target, *, name, email, body, parent_id=None, honeypot='',
                   form_token='', author=None, notify_replies=False):
```

Replace

```python
    parent = None
    if parent_id:
        parent, answered = _resolve_parent(target, parent_id)
        if answered is not None and not body.startswith(f'@{answered.name} '):
            body = f'@{answered.name} {body}'
```

with

```python
    parent = answered = None
    if parent_id:
        parent, reply_answered = _resolve_parent(target, parent_id)
        answered = reply_answered or parent
        if reply_answered is not None and not body.startswith(
                f'@{reply_answered.name} '):
            body = f'@{reply_answered.name} {body}'
```

and pass the new values when building the comment:

```python
    comment = PostComment(
        name=name.strip(), email=email, body=body, parent=parent,
        answered=answered, notify_replies=notify_replies,
        status=_decide_status(body, email, is_admin), ip_hash=ip_hash,
        user_id=author.id if is_admin else None)
```

- [ ] **Step 6: Form, template, route, CSS**

In `app/forms.py`, add the field to `PostCommentForm` right after `body`:

```python
    notify = BooleanField('有回复或审核结果时，用邮件通知我')
```

In `app/templates/_comments.html`, after the closing `</div>` of the body block (the one that ends with the `form.body.errors` loop) and before `{{ form.submit(class="btn btn-primary") }}`, insert:

```html
        <div class="form-check comment-form__notify">
            {{ form.notify(class="form-check-input") }}
            {{ form.notify.label(class="form-check-label") }}
        </div>
```

Append to `app/static/style.css`:

```css
.comment-form__notify {
    margin: 0;
    color: var(--text-secondary);
    font-size: 14px;
}
```

In `app/routes.py`, `_take_comment`, add one argument to the `submit_comment(...)` call:

```python
            honeypot=form.website.data, form_token=form.form_token.data,
            notify_replies=form.notify.data,
            author=current_user if current_user.is_authenticated else None)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_migrations.py tests/test_comment_service.py tests/test_comments_public.py tests/test_admin_comments.py tests/test_comment_model.py -q`
Expected: all PASS (the existing comment tests prove the two-foreign-key relationships still work).

- [ ] **Step 8: Commit**

```bash
git add migrations/versions/d7b3a9e41c58_add_comment_notifications.py app/models.py app/comments.py app/forms.py app/templates/_comments.html app/static/style.css app/routes.py tests/test_migrations.py tests/test_comment_service.py tests/test_comments_public.py
git commit -m "feat(comments): record email consent and which comment a reply answers"
```

---

### Task 2: Shared email test fixture, base HTML template, custom headers

**Files:**
- Modify: `tests/conftest.py`, `tests/test_password_reset_email.py`, `app/email.py`, `app/templates/email/reset_password.html`
- Create: `app/templates/email/base.html`, `app/templates/email/_parts.html`, `tests/test_email_send.py`

**Interfaces:**
- Produces: pytest fixture `outbox` (list of Flask-Mail `Message`s; mail configured as `smtp.test` / `noreply@example.com`, `ADMINS=['admin@example.com']`, sending inline and suppressed, config restored after the test); `send_email(..., headers=None)`; `email/base.html` blocks `title`, `label`, `heading`, `content`, `note`, `unsubscribe`; macros in `email/_parts.html`: `paragraph()` (use with `{% call %}`), `button(url, label)`, `quote(text)`, `fallback_link(url)`, `note()` (use with `{% call %}`), `unsubscribe_note(url)`. Templates receive `site_name`.

- [ ] **Step 1: Move the `outbox` fixture into `tests/conftest.py` and stop it leaking config**

In `tests/conftest.py`, extend the imports at the top:

```python
import threading
...
import pytest
from flask_mail import email_dispatched
```

and change `from app import app, db  # noqa: E402` to:

```python
from app import app, db, mail  # noqa: E402
```

Append at the end of `tests/conftest.py`:

```python
@pytest.fixture()
def outbox(application, users, monkeypatch):
    """Mail is configured, nothing is really sent, and sending happens inline.

    The returned list collects every message Flask-Mail dispatches. Config is
    changed with monkeypatch so it never leaks into other tests.
    """
    for key, value in (('MAIL_SERVER', 'smtp.test'),
                       ('MAIL_USERNAME', 'noreply@example.com'),
                       ('ADMINS', ['admin@example.com'])):
        monkeypatch.setitem(application.config, key, value)
    monkeypatch.setattr(mail.state, 'suppress', True)

    class InlineThread(threading.Thread):
        def start(self):
            self.run()

    monkeypatch.setattr('app.email.Thread', InlineThread)
    sent = []

    def collect(sender, message, **extra):
        sent.append(message)

    email_dispatched.connect(collect)
    yield sent
    email_dispatched.disconnect(collect)
```

Replace the whole content of `tests/test_password_reset_email.py` with this version (fixture removed, config changes via `monkeypatch`):

```python
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
```

- [ ] **Step 2: Run the moved tests (they must still pass) and write the failing header test**

Create `tests/test_email_send.py`:

```python
from app.email import send_email


def test_send_email_passes_extra_headers(application, outbox):
    with application.app_context():
        send_email('subject', 'noreply@example.com', ['reader@example.com'],
                   'text', '<p>html</p>',
                   headers={'List-Unsubscribe': '<https://example.com/u>'},
                   sync=True)
    assert outbox[-1].extra_headers == {
        'List-Unsubscribe': '<https://example.com/u>'}


def test_send_email_without_headers_still_works(application, outbox):
    with application.app_context():
        send_email('subject', 'noreply@example.com', ['reader@example.com'],
                   'text', '<p>html</p>', sync=True)
    assert outbox[-1].subject == 'subject'
```

Run: `.venv/bin/python -m pytest tests/test_password_reset_email.py tests/test_email_send.py -q`
Expected: the password reset tests PASS; `test_send_email_passes_extra_headers` FAILS (`unexpected keyword argument 'headers'`).

- [ ] **Step 3: Add `headers` to `send_email`**

In `app/email.py`:

```python
def send_email(subject, sender, recipients, text_body, html_body,
               attachments=None, sync=False, headers=None):
    msg = Message(subject, sender=sender, recipients=recipients,
                  extra_headers=headers)
```

(the rest of the function is unchanged).

- [ ] **Step 4: Create the shared email shell and macros**

Create `app/templates/email/_parts.html`:

```html
{% macro paragraph() %}<p class="mail-text" style="margin:0 0 16px;color:#1c1915;">{{ caller() }}</p>{% endmacro %}

{% macro button(url, label) %}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:12px 0 28px;">
  <tr>
    <td class="mail-button" style="background-color:#1c1915;border-radius:8px;">
      <a href="{{ url }}" class="mail-button" style="display:inline-block;padding:12px 22px;font-family:'Source Serif 4','Noto Serif SC','Songti SC',Georgia,serif;font-size:14px;font-weight:600;line-height:1.2;color:#f2f1ef;text-decoration:none;">{{ label }}</a>
    </td>
  </tr>
</table>
{% endmacro %}

{% macro quote(text) %}
<div class="mail-quote mail-muted" style="margin:0 0 24px;padding:2px 0 2px 16px;border-left:2px solid #746d48;color:#746d48;white-space:pre-wrap;word-break:break-word;">{{ text }}</div>
{% endmacro %}

{% macro fallback_link(url) %}
<p class="mail-muted" style="margin:0 0 8px;font-size:14px;color:#746d48;">如果按钮无法点击，请把下面的链接复制到浏览器地址栏：</p>
<p style="margin:0 0 28px;font-size:14px;word-break:break-all;"><a href="{{ url }}" class="mail-link" style="color:#0066cc;">{{ url }}</a></p>
{% endmacro %}

{% macro note() %}<p class="mail-muted mail-rule" style="margin:0;padding-top:18px;border-top:1px solid #d2d2d7;font-size:14px;color:#746d48;">{{ caller() }}</p>{% endmacro %}

{% macro unsubscribe_note(url) %}<p class="mail-muted" style="margin:14px 0 0;font-size:13px;color:#746d48;">你收到这封邮件，是因为发表评论时勾选了邮件通知。不想再收到？<a href="{{ url }}" class="mail-link" style="color:#0066cc;">退订</a></p>{% endmacro %}
```

Create `app/templates/email/base.html`:

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{% block title %}{{ site_name }}{% endblock %}</title>
    <style>
      /* Same palette as the site's dark theme; clients without support keep the inline light colours. */
      @media (prefers-color-scheme: dark) {
        .mail-page { background-color: #141412 !important; }
        .mail-card { background-color: #232320 !important; }
        .mail-text { color: #f0eee8 !important; }
        .mail-muted { color: #bfb998 !important; }
        .mail-rule { border-color: #514f46 !important; }
        .mail-quote { border-color: #bfb998 !important; }
        .mail-button { background-color: #f0eee8 !important; color: #141412 !important; }
        .mail-link { color: #2997ff !important; }
      }
      @media (max-width: 480px) {
        .mail-card { padding: 28px 20px !important; }
      }
    </style>
  </head>
  <body class="mail-page" style="margin:0;padding:0;background-color:#f2f1ef;">
    <table role="presentation" class="mail-page" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f2f1ef;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" class="mail-card" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background-color:#fbfaf8;border-radius:16px;">
            <tr>
              <td class="mail-card" style="padding:40px 40px 36px;font-family:'Source Serif 4','Noto Serif SC','Songti SC',Georgia,serif;font-size:16px;line-height:1.7;color:#1c1915;">
                <div class="mail-text" style="font-size:20px;font-weight:700;line-height:1;color:#1c1915;">{{ site_name }}</div>

                <div class="mail-rule" style="margin-top:28px;padding-bottom:18px;border-bottom:1px solid #d2d2d7;">
                  <div class="mail-muted" style="font-size:12px;font-weight:500;letter-spacing:.05em;color:#746d48;">{% block label %}{% endblock %}</div>
                  <h1 class="mail-text" style="margin:10px 0 0;font-size:28px;font-weight:700;line-height:1.2;color:#1c1915;">{% block heading %}{% endblock %}</h1>
                </div>

                <div style="margin-top:28px;">
                  {% block content %}{% endblock %}
                </div>
                {% block note %}{% endblock %}
                {% block unsubscribe %}{% endblock %}
              </td>
            </tr>
          </table>
          <p class="mail-muted" style="margin:20px 0 0;font-family:'Source Serif 4','Noto Serif SC','Songti SC',Georgia,serif;font-size:12px;color:#746d48;">© {{ current_year }} {{ site_name }}</p>
        </td>
      </tr>
    </table>
  </body>
</html>
```

Replace the whole of `app/templates/email/reset_password.html` with:

```html
{% extends "email/base.html" %}
{% import "email/_parts.html" as parts %}
{% block title %}重置你的密码{% endblock %}
{% block label %}账号{% endblock %}
{% block heading %}重置你的密码{% endblock %}
{% block content %}
  {% call parts.paragraph() %}{{ user.username }}，你好：{% endcall %}
  {% call parts.paragraph() %}我们收到了重置你在“{{ site_name }}”的账号密码的请求。点击下面的按钮设置新密码：{% endcall %}
  {{ parts.button(reset_url, '重置密码') }}
  {{ parts.fallback_link(reset_url) }}
{% endblock %}
{% block note %}
  {% call parts.note() %}此链接 {{ expires_minutes }} 分钟内有效，且只能使用一次。如果这不是你本人的操作，请忽略这封邮件，你的密码不会改变。{% endcall %}
{% endblock %}
```

- [ ] **Step 5: Run the tests, then look at the email**

Run: `.venv/bin/python -m pytest tests/test_password_reset_email.py tests/test_email_send.py -q`
Expected: all PASS.

Render and screenshot the reset email to confirm it still looks the same as before the refactor (palette, card, dark button):

```bash
mkdir -p $CLAUDE_JOB_DIR/tmp && cat > $CLAUDE_JOB_DIR/tmp/render.py <<'EOF'
import os, sys
sys.path.insert(0, '.')
os.environ.update(MAIL_SERVER='', ADMIN_EMAILS='a@x.com', SECRET_KEY='render-secret-render-secret-1234', DATABASE_URL='sqlite://')
from app import app, db
from app.models import User
with app.app_context(), app.test_request_context():
    db.create_all()
    u = User(username='小明', email='m@x.com'); u.set_password('p'); db.session.add(u); db.session.commit()
    from flask import render_template
    ctx = dict(user=u, site_name="Aisaka's Blog", reset_url='https://flog.aisaka.cc/reset_password/TOKEN', expires_minutes=10)
    open(os.environ['CLAUDE_JOB_DIR'] + '/tmp/mail.html', 'w').write(render_template('email/reset_password.html', **ctx))
EOF
.venv/bin/python -I $CLAUDE_JOB_DIR/tmp/render.py >/dev/null 2>&1
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=700,820 --screenshot=$CLAUDE_JOB_DIR/tmp/mail.png file://$CLAUDE_JOB_DIR/tmp/mail.html
```

Open `$CLAUDE_JOB_DIR/tmp/mail.png`: expected a warm-grey page, off-white rounded card, bold site name, "账号" label over a large title, a dark "重置密码" button.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_password_reset_email.py tests/test_email_send.py app/email.py app/templates/email
git commit -m "refactor(email): shared HTML email shell, send_email headers, shared outbox test fixture"
```

---

### Task 3: Unsubscribe

**Files:**
- Create: `app/comment_mail.py`, `app/templates/user/comment_unsubscribe.html`, `tests/test_comment_unsubscribe.py`
- Modify: `app/forms.py`, `app/routes.py` (import, new route, robots), `tests/test_syndication.py`

**Interfaces:**
- Produces in `app/comment_mail.py`: `unsubscribe_token(email: str) -> str`, `email_from_unsubscribe_token(token: str) -> str | None`, `unsubscribe_url(email: str) -> str` (absolute; needs a request context), `stop_notifications(email: str) -> int` (switches off `notify_replies` for every comment of that email, case-insensitively; does not commit; returns rows changed). Route endpoint name `comment_unsubscribe` (`/comments/unsubscribe/<token>`, GET shows confirmation, POST applies). `CommentUnsubscribeForm`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comment_unsubscribe.py`:

```python
from lxml import html as lxml_html

from app import db
from app.comment_mail import (email_from_unsubscribe_token, stop_notifications,
                              unsubscribe_token, unsubscribe_url)
from app.models import PostComment


def add_comment(post_id, email, notify=True, **values):
    comment = PostComment(post_id=post_id, name='Reader', email=email,
                          body='hello', notify_replies=notify, **values)
    db.session.add(comment)
    db.session.commit()
    return comment.id


def notify_flags(*ids):
    return [db.session.get(PostComment, i).notify_replies for i in ids]


def test_token_round_trip_lowercases_the_address(application):
    token = unsubscribe_token(' Reader@Example.com ')
    assert email_from_unsubscribe_token(token) == 'reader@example.com'


def test_garbage_and_foreign_tokens_are_refused(application):
    assert email_from_unsubscribe_token('nope') is None
    assert email_from_unsubscribe_token('') is None


def test_unsubscribe_url_is_absolute(application):
    with application.test_request_context():
        url = unsubscribe_url('reader@example.com')
    assert url.startswith('http://localhost/comments/unsubscribe/')


def test_stop_notifications_matches_the_address_case_insensitively(
        application, users):
    mine = add_comment(users['post'], 'Reader@Example.com')
    mine_too = add_comment(users['post'], 'reader@example.com')
    other = add_comment(users['post'], 'someone@example.com')
    assert stop_notifications('READER@example.com') == 2
    db.session.commit()
    assert notify_flags(mine, mine_too, other) == [False, False, True]


def test_get_asks_for_confirmation_and_changes_nothing(
        client, application, users):
    comment_id = add_comment(users['post'], 'reader@example.com')
    token = unsubscribe_token('reader@example.com')
    response = client.get(f'/comments/unsubscribe/{token}')
    assert response.status_code == 200
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert 'reader@example.com' in page.text_content()
    assert page.xpath('//section[contains(@class, "form-shell")]//input[@type="submit"]')
    assert notify_flags(comment_id) == [True]


def test_post_switches_off_every_comment_of_that_address(
        client, application, users):
    first = add_comment(users['post'], 'reader@example.com')
    second = add_comment(users['post'], 'reader@example.com')
    other = add_comment(users['post'], 'someone@example.com')
    token = unsubscribe_token('reader@example.com')
    response = client.post(f'/comments/unsubscribe/{token}',
                           follow_redirects=True)
    assert '已退订' in response.get_data(as_text=True)
    db.session.expire_all()
    assert notify_flags(first, second, other) == [False, False, True]


def test_bad_token_is_a_404(client, application):
    assert client.get('/comments/unsubscribe/nope').status_code == 404
    assert client.post('/comments/unsubscribe/nope').status_code == 404
```

Add `'/comments/unsubscribe/'` to the path tuple in `test_robots_disallows_admin_and_authentication_routes` in `tests/test_syndication.py`:

```python
    for path in ('/admin', '/login', '/logout', '/register',
                 '/reset_password_request', '/reset_password/',
                 '/comments/unsubscribe/'):
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_comment_unsubscribe.py tests/test_syndication.py -q`
Expected: FAIL (`ModuleNotFoundError: app.comment_mail`, missing robots line).

- [ ] **Step 3: Create `app/comment_mail.py` with the unsubscribe helpers**

```python
"""Emails about comments: who hears about a comment and what they are told.

Nothing here commits; call it after the comment is saved.
"""
import sqlalchemy as sa
from flask import current_app, url_for
from itsdangerous import BadData, URLSafeSerializer

from app import db
from app.models import PostComment


def _unsubscribe_signer():
    return URLSafeSerializer(
        current_app.config['SECRET_KEY'], salt='comment-unsubscribe')


def unsubscribe_token(email):
    """Signed, never expires: an unsubscribe link must keep working."""
    return _unsubscribe_signer().dumps(email.strip().lower())


def email_from_unsubscribe_token(token):
    try:
        email = _unsubscribe_signer().loads(token)
    except BadData:
        return None
    return email if isinstance(email, str) else None


def unsubscribe_url(email):
    return url_for('comment_unsubscribe', token=unsubscribe_token(email),
                   _external=True)


def stop_notifications(email):
    """Switch off emails for every comment written with this address.

    Returns how many comments changed; the caller commits.
    """
    result = db.session.execute(
        sa.update(PostComment).where(
            sa.func.lower(PostComment.email) == email.strip().lower(),
            PostComment.notify_replies.is_(True),
        ).values(notify_replies=False))
    return result.rowcount
```

- [ ] **Step 4: Form, page, route, robots**

In `app/forms.py`, after `ResetPasswordForm` add:

```python
class CommentUnsubscribeForm(FlaskForm):
    submit = SubmitField('确认退订')
```

Create `app/templates/user/comment_unsubscribe.html`:

```html
{% extends "base.html" %}
{% import "bootstrap_wtf.html" as wtf %}

{% block page_hero %}{% endblock %}

{% block content %}
  <section class="form-shell public-page" aria-labelledby="page-title">
    <header class="page-heading">
      <div class="public-label">评论</div>
      <h1 id="page-title">退订评论邮件</h1>
      <p>不再给 {{ email }} 发送评论相关的邮件（回复通知、审核结果）？</p>
    </header>
    {{ wtf.quick_form(form) }}
  </section>
{% endblock %}
```

In `app/routes.py`:

- extend the forms import (line 12) with `CommentUnsubscribeForm` (keep the existing names in the import);
- add `from app.comment_mail import email_from_unsubscribe_token, stop_notifications` next to the other `app.*` imports;
- add `'Disallow: /comments/unsubscribe/\n'` to the robots response, right after the `'Disallow: /reset_password/\n'` line;
- add the route right before `_take_comment`:

```python
@app.route('/comments/unsubscribe/<token>', methods=['GET', 'POST'])
def comment_unsubscribe(token):
    email = email_from_unsubscribe_token(token)
    if email is None:
        abort(404)
    form = CommentUnsubscribeForm()
    if form.validate_on_submit():
        stop_notifications(email)
        db.session.commit()
        flash('已退订，之后不会再给你发评论相关的邮件。')
        return redirect(url_for('index'))
    return render_template('user/comment_unsubscribe.html',
                           title='退订评论邮件', form=form, email=email)
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_comment_unsubscribe.py tests/test_syndication.py tests/test_public_pages_consistency.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/comment_mail.py app/forms.py app/routes.py app/templates/user/comment_unsubscribe.html tests/test_comment_unsubscribe.py tests/test_syndication.py
git commit -m "feat(comments): confirm-then-apply unsubscribe for comment emails"
```

---

### Task 4: The three comment emails

**Files:**
- Modify: `app/comment_mail.py`
- Create: `app/templates/email/comment_new.html`, `comment_new.txt`, `comment_reply.html`, `comment_reply.txt`, `comment_approved.html`, `comment_approved.txt`, `tests/test_comment_mail.py`

**Interfaces:**
- Consumes: Task 1 columns, Task 2 `outbox` fixture, `send_email(headers=)`, `_parts` macros, `base.html`; Task 3 `unsubscribe_url`.
- Produces: `notify_comment_published(comment)`, `notify_comment_pending(comment)`, `notify_comments_approved(comments)` — each returns `None`, never raises, does nothing when mail is not configured, must be called inside a request (or `test_request_context`) after the comment is committed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comment_mail.py`:

```python
import re

from app import db
from app.comment_mail import (notify_comment_pending, notify_comment_published,
                              notify_comments_approved)
from app.models import Page, PostComment


def add_comment(**values):
    values.setdefault('name', 'Reader')
    values.setdefault('email', 'reader@example.com')
    values.setdefault('body', 'A fine post')
    comment = PostComment(**values)
    db.session.add(comment)
    db.session.commit()
    return comment


def reply_to(top, **values):
    return add_comment(post_id=top.post_id, page_id=top.page_id,
                       parent_id=top.id, answered_id=top.id, **values)


def mails_to(outbox, address):
    return [m for m in outbox if m.recipients == [address]]


def unsubscribe_link(message):
    return re.search(r'https?://\S+/comments/unsubscribe/\S+',
                     message.body).group(0)


# --- new comment -> site owner and post author ---------------------------

def test_published_comment_goes_to_owner_and_author_separately(
        application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'], body='Great read')
        notify_comment_published(comment)
    assert sorted(m.recipients[0] for m in outbox) == [
        'admin@example.com', 'author@example.com']
    assert all(len(m.recipients) == 1 for m in outbox)
    message = outbox[0]
    assert message.subject == "[Aisaka's Blog] 新评论：Test"
    assert 'Reader' in message.body and 'Great read' in message.body
    assert f'/post/{users["post"]}#comment-{comment.id}' in message.body
    assert 'unsubscribe' not in message.html
    assert 'List-Unsubscribe' not in (message.extra_headers or {})


def test_staff_addresses_are_deduplicated(application, users, outbox,
                                          monkeypatch):
    monkeypatch.setitem(application.config, 'ADMINS',
                        ['Author@Example.com', 'admin@example.com'])
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
    assert sorted(m.recipients[0].lower() for m in outbox) == [
        'admin@example.com', 'author@example.com']


def test_commenter_is_never_told_about_their_own_comment(
        application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'],
                              email='author@example.com')
        notify_comment_published(comment)
    assert [m.recipients[0] for m in outbox] == ['admin@example.com']


def test_page_comment_goes_to_owner_only(application, users, outbox):
    with application.test_request_context():
        page = Page(title='About', slug='about', kind='content',
                    is_published=True, comments_enabled=True)
        db.session.add(page)
        db.session.commit()
        comment = add_comment(page_id=page.id)
        notify_comment_published(comment)
    (message,) = outbox
    assert message.recipients == ['admin@example.com']
    assert '/about#comment-' in message.body
    assert '《About》' in message.body


def test_pending_comment_links_to_the_review_queue(application, users, outbox):
    with application.test_request_context():
        comment = add_comment(post_id=users['post'], status='pending')
        notify_comment_pending(comment)
    assert len(outbox) == 2
    message = outbox[0]
    assert message.subject == "[Aisaka's Blog] 新评论待审核：Test"
    assert '/admin/comments?status=pending' in message.html
    assert '前往审核' in message.html


# --- reply -> the commenter who was answered -----------------------------

def test_reply_tells_the_commenter_who_asked_for_it(application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
        reply = reply_to(top, name='Bob', email='bob@example.com',
                         body='@Ann Agreed')
        notify_comment_published(reply)
    (message,) = mails_to(outbox, 'ann@example.com')
    assert message.subject == "[Aisaka's Blog] 有人回复了你的评论"
    assert 'Bob' in message.body and 'Agreed' in message.body
    assert f'#comment-{reply.id}' in message.body
    link = unsubscribe_link(message)
    assert message.extra_headers == {'List-Unsubscribe': f'<{link}>'}
    assert link in message.html


def test_reply_is_not_sent_without_consent_or_to_oneself_or_to_nobody(
        application, users, outbox):
    with application.test_request_context():
        quiet = add_comment(post_id=users['post'], email='quiet@example.com')
        notify_comment_published(reply_to(quiet, email='bob@example.com'))
        eager = add_comment(post_id=users['post'], email='eager@example.com',
                            notify_replies=True)
        notify_comment_published(reply_to(eager, email='Eager@example.com'))
        orphan = add_comment(post_id=users['post'], parent_id=eager.id,
                             email='orphan@example.com')
        notify_comment_published(orphan)
    assert mails_to(outbox, 'quiet@example.com') == []
    assert mails_to(outbox, 'eager@example.com') == []


def test_reply_to_a_reply_tells_that_reply_author(application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], email='ann@example.com')
        first = reply_to(top, name='Bob', email='bob@example.com',
                         notify_replies=True)
        second = add_comment(post_id=users['post'], parent_id=top.id,
                             answered_id=first.id, name='Cy',
                             email='cy@example.com', body='@Bob me too')
        notify_comment_published(second)
    assert len(mails_to(outbox, 'bob@example.com')) == 1
    assert mails_to(outbox, 'ann@example.com') == []


# --- approval -> the commenter -------------------------------------------

def test_approval_tells_a_commenter_who_asked(application, users, outbox):
    with application.test_request_context():
        mine = add_comment(post_id=users['post'], email='ann@example.com',
                           notify_replies=True)
        silent = add_comment(post_id=users['post'], email='bob@example.com')
        notify_comments_approved([mine, silent])
    (message,) = outbox
    assert message.recipients == ['ann@example.com']
    assert message.subject == "[Aisaka's Blog] 你的评论已通过审核"
    assert f'/post/{users["post"]}#comment-{mine.id}' in message.body
    assert unsubscribe_link(message) in message.html


def test_approving_a_reply_also_tells_the_answered_commenter(
        application, users, outbox):
    with application.test_request_context():
        top = add_comment(post_id=users['post'], email='ann@example.com',
                          notify_replies=True)
        reply = reply_to(top, email='bob@example.com', notify_replies=True)
        notify_comments_approved([reply])
    subjects = {m.recipients[0]: m.subject for m in outbox}
    assert '通过审核' in subjects['bob@example.com']
    assert '回复了你的评论' in subjects['ann@example.com']


# --- robustness ----------------------------------------------------------

def test_long_comments_are_cut_and_markup_is_escaped(application, users, outbox):
    with application.test_request_context():
        long = add_comment(post_id=users['post'], body='x' * 400)
        notify_comment_published(long)
        evil = add_comment(post_id=users['post'],
                           body='<script>alert(1)</script>')
        notify_comment_published(evil)
    first, second = outbox[0], outbox[2]
    assert ('x' * 300 + '……') in first.body
    assert 'x' * 301 not in first.body
    assert '<script>' not in second.html
    assert '&lt;script&gt;' in second.html


def test_nothing_is_sent_when_mail_is_not_configured(
        application, users, outbox, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
        notify_comment_pending(comment)
        notify_comments_approved([comment])
    assert outbox == []


def test_a_mail_failure_never_reaches_the_caller(
        application, users, outbox, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise OSError('smtp down')

    monkeypatch.setattr('app.comment_mail.send_email', boom)
    with application.test_request_context():
        comment = add_comment(post_id=users['post'])
        notify_comment_published(comment)
    assert 'Could not send comment emails' in caplog.text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_comment_mail.py -q`
Expected: FAIL (`ImportError: cannot import name 'notify_comment_published'`).

- [ ] **Step 3: Implement the notifiers**

In `app/comment_mail.py`, replace the import block at the top with:

```python
import functools

import sqlalchemy as sa
from flask import current_app, render_template, url_for
from itsdangerous import BadData, URLSafeSerializer

from app import db
from app.email import mail_configured, mail_sender, send_email
from app.models import PostComment
from app.site_text import site_text

EXCERPT_LENGTH = 300
```

and append to the file:

```python
def _excerpt(body):
    body = (body or '').strip()
    if len(body) <= EXCERPT_LENGTH:
        return body
    return body[:EXCERPT_LENGTH].rstrip() + '……'


def _target(comment):
    return comment.post or comment.page


def _target_title(comment):
    return _target(comment).title or '无标题'


def _comment_url(comment):
    anchor = f'comment-{comment.id}'
    if comment.post is not None:
        return url_for('post', post_id=comment.post.id, _anchor=anchor,
                       _external=True)
    return url_for('public_page', slug=comment.page.slug, _anchor=anchor,
                   _external=True)


def _staff_addresses(comment):
    """Site owners and the post's author, once each, never the commenter."""
    addresses = list(current_app.config['ADMINS'])
    if comment.post is not None:
        addresses.append(comment.post.author.email)
    skip = {comment.email.strip().lower()}
    result = []
    for address in addresses:
        key = address.strip().lower()
        if key and key not in skip:
            skip.add(key)
            result.append(address.strip())
    return result


def _send(subject, recipient, template, unsubscribe_for=None, **context):
    """One email to one person; ``unsubscribe_for`` adds the opt-out link."""
    site_name = site_text()['site_name']
    headers = None
    if unsubscribe_for:
        url = unsubscribe_url(unsubscribe_for)
        context['unsubscribe_url'] = url
        headers = {'List-Unsubscribe': f'<{url}>'}
    context['site_name'] = site_name
    send_email(
        f'[{site_name}] {subject}', sender=(site_name, mail_sender()),
        recipients=[recipient],
        text_body=render_template(f'email/{template}.txt', **context),
        html_body=render_template(f'email/{template}.html', **context),
        headers=headers)


def _tell_staff(comment, pending):
    title = _target_title(comment)
    if pending:
        subject = f'新评论待审核：{title}'
        action_url = url_for('admin.comments', status='pending',
                             _external=True)
    else:
        subject = f'新评论：{title}'
        action_url = _comment_url(comment)
    for address in _staff_addresses(comment):
        _send(subject, address, 'comment_new', comment=comment,
              pending=pending, target_title=title, action_url=action_url,
              excerpt=_excerpt(comment.body))


def _tell_answered(comment):
    answered = comment.answered
    if answered is None or not answered.notify_replies:
        return
    if answered.email.strip().lower() == comment.email.strip().lower():
        return
    _send('有人回复了你的评论', answered.email, 'comment_reply',
          unsubscribe_for=answered.email, comment=comment,
          target_title=_target_title(comment),
          comment_url=_comment_url(comment), excerpt=_excerpt(comment.body))


def _tell_approved(comment):
    if not comment.notify_replies:
        return
    _send('你的评论已通过审核', comment.email, 'comment_approved',
          unsubscribe_for=comment.email, comment=comment,
          target_title=_target_title(comment),
          comment_url=_comment_url(comment), excerpt=_excerpt(comment.body))


def _quietly(function):
    """Mail is optional and must never break the request that triggered it."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        if not mail_configured():
            return None
        try:
            function(*args, **kwargs)
        except Exception:
            current_app.logger.exception('Could not send comment emails')
        return None
    return wrapper


@_quietly
def notify_comment_published(comment):
    """A comment is now public: tell the owners, and whoever it answers."""
    _tell_staff(comment, pending=False)
    _tell_answered(comment)


@_quietly
def notify_comment_pending(comment):
    """A comment waits for review: tell the owners."""
    _tell_staff(comment, pending=True)


@_quietly
def notify_comments_approved(comments):
    """Held comments just went public: tell their authors, and whoever
    each one answers (the owners already knew about it)."""
    for comment in comments:
        _tell_approved(comment)
        _tell_answered(comment)
```

(`sa`, `db`, `PostComment`, `BadData`, `URLSafeSerializer` stay in use by the Task 3 helpers above.)

- [ ] **Step 4: Create the templates**

`app/templates/email/comment_new.html`:

```html
{% extends "email/base.html" %}
{% import "email/_parts.html" as parts %}
{% block title %}{% if pending %}新评论待审核{% else %}新评论{% endif %}{% endblock %}
{% block label %}评论{% endblock %}
{% block heading %}{% if pending %}有一条评论等待审核{% else %}收到一条新评论{% endif %}{% endblock %}
{% block content %}
  {% call parts.paragraph() %}<strong>{{ comment.name }}</strong>（{{ comment.email }}）在《{{ target_title }}》下评论：{% endcall %}
  {{ parts.quote(excerpt) }}
  {{ parts.button(action_url, '前往审核' if pending else '查看评论') }}
  {{ parts.fallback_link(action_url) }}
{% endblock %}
```

`app/templates/email/comment_new.txt`:

```
{% if pending %}有一条评论等待审核{% else %}收到一条新评论{% endif %}

{{ comment.name }}（{{ comment.email }}）在《{{ target_title }}》下评论：

{{ excerpt }}

{% if pending %}前往审核{% else %}查看评论{% endif %}：
{{ action_url }}

{{ site_name }}
```

`app/templates/email/comment_reply.html`:

```html
{% extends "email/base.html" %}
{% import "email/_parts.html" as parts %}
{% block title %}有人回复了你的评论{% endblock %}
{% block label %}评论{% endblock %}
{% block heading %}有人回复了你的评论{% endblock %}
{% block content %}
  {% call parts.paragraph() %}<strong>{{ comment.name }}</strong> 在《{{ target_title }}》下回复了你：{% endcall %}
  {{ parts.quote(excerpt) }}
  {{ parts.button(comment_url, '查看回复') }}
  {{ parts.fallback_link(comment_url) }}
{% endblock %}
{% block unsubscribe %}{{ parts.unsubscribe_note(unsubscribe_url) }}{% endblock %}
```

`app/templates/email/comment_reply.txt`:

```
有人回复了你的评论

{{ comment.name }} 在《{{ target_title }}》下回复了你：

{{ excerpt }}

查看回复：
{{ comment_url }}

{{ site_name }}

你收到这封邮件，是因为发表评论时勾选了邮件通知。不想再收到？退订：
{{ unsubscribe_url }}
```

`app/templates/email/comment_approved.html`:

```html
{% extends "email/base.html" %}
{% import "email/_parts.html" as parts %}
{% block title %}你的评论已通过审核{% endblock %}
{% block label %}评论{% endblock %}
{% block heading %}你的评论已通过审核{% endblock %}
{% block content %}
  {% call parts.paragraph() %}你在《{{ target_title }}》下的评论已通过审核，现在大家都能看到了：{% endcall %}
  {{ parts.quote(excerpt) }}
  {{ parts.button(comment_url, '查看评论') }}
  {{ parts.fallback_link(comment_url) }}
{% endblock %}
{% block unsubscribe %}{{ parts.unsubscribe_note(unsubscribe_url) }}{% endblock %}
```

`app/templates/email/comment_approved.txt`:

```
你的评论已通过审核

你在《{{ target_title }}》下的评论已通过审核，现在大家都能看到了：

{{ excerpt }}

查看评论：
{{ comment_url }}

{{ site_name }}

你收到这封邮件，是因为发表评论时勾选了邮件通知。不想再收到？退订：
{{ unsubscribe_url }}
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_comment_mail.py tests/test_comment_unsubscribe.py tests/test_password_reset_email.py -q`
Expected: all PASS.

- [ ] **Step 6: Look at a comment email**

Render `comment_reply.html` with sample values the same way as Task 2 step 5 (context: `comment=SimpleNamespace(name='Bob')`, `target_title='你好，世界'`, `excerpt='同意！写得很好。\n第二行'`, `comment_url='https://flog.aisaka.cc/post/1#comment-3'`, `unsubscribe_url='https://flog.aisaka.cc/comments/unsubscribe/TOKEN'`, `site_name="Aisaka's Blog"`), screenshot it, and check: label "评论", quote with a left rule, dark button "查看回复", small "退订" note under the card text.

- [ ] **Step 7: Commit**

```bash
git add app/comment_mail.py app/templates/email tests/test_comment_mail.py
git commit -m "feat(comments): new-comment, reply and approval emails"
```

---

### Task 5: Send the emails when comments change state

**Files:**
- Modify: `app/routes.py` (`_take_comment`, imports), `app/admin/modules.py` (`approve_comment`, `bulk_comments`, `reply_comment`, imports)
- Test: `tests/test_comment_email_flow.py` (new)

**Interfaces:**
- Consumes: `notify_comment_published`, `notify_comment_pending`, `notify_comments_approved` (Task 4); `PENDING` from `app.comments`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comment_email_flow.py`:

```python
from app import db
from app.models import PostComment
from tests.conftest import login


def add_comment(**values):
    values.setdefault('name', 'Old')
    values.setdefault('email', 'old@example.com')
    values.setdefault('body', 'earlier')
    comment = PostComment(**values)
    db.session.add(comment)
    db.session.commit()
    return comment.id


def post_comment(client, post_id, **data):
    data.setdefault('name', 'Reader')
    data.setdefault('email', 'reader@example.com')
    data.setdefault('body', 'Nice post')
    return client.post(f'/post/{post_id}', data=data)


def mails_to(outbox, address):
    return [m for m in outbox if m.recipients == [address]]


def comment_id_of(email):
    return db.session.scalar(
        db.select(PostComment.id).where(PostComment.email == email))


def test_first_comment_tells_staff_it_needs_review(client, outbox, users):
    post_comment(client, users['post'])
    assert sorted(m.recipients[0] for m in outbox) == [
        'admin@example.com', 'author@example.com']
    assert all('待审核' in m.subject for m in outbox)


def test_trusted_comment_tells_staff_at_once(client, application, outbox, users):
    with application.app_context():
        add_comment(post_id=users['post'], email='reader@example.com')
    post_comment(client, users['post'])
    assert len(outbox) == 2
    assert all('新评论：Test' in m.subject for m in outbox)


def test_approving_tells_the_commenter_once(client, application, outbox, users):
    post_comment(client, users['post'], notify='y')
    outbox.clear()
    with application.app_context():
        comment_id = comment_id_of('reader@example.com')
    login(client, 'admin')

    client.post(f'/admin/comments/{comment_id}/approve')
    (message,) = outbox
    assert message.recipients == ['reader@example.com']
    assert '通过审核' in message.subject

    client.post(f'/admin/comments/{comment_id}/approve')
    assert len(outbox) == 1


def test_approving_stays_silent_without_the_checkbox(
        client, application, outbox, users):
    post_comment(client, users['post'])
    outbox.clear()
    with application.app_context():
        comment_id = comment_id_of('reader@example.com')
    login(client, 'admin')
    client.post(f'/admin/comments/{comment_id}/approve')
    assert outbox == []


def test_bulk_approve_only_tells_comments_that_changed(
        client, application, outbox, users):
    with application.app_context():
        held = add_comment(post_id=users['post'], status='pending',
                           email='held@example.com', notify_replies=True)
        live = add_comment(post_id=users['post'], status='approved',
                           email='live@example.com', notify_replies=True)
    login(client, 'admin')
    client.post('/admin/comments/bulk',
                data={'action': 'approve', 'ids': [str(held), str(live)]})
    assert [m.recipients for m in outbox] == [['held@example.com']]


def test_admin_reply_tells_the_commenter_and_the_author(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
    login(client, 'admin')
    client.post(f'/admin/comments/{top}/reply', data={'body': 'Thanks!'})

    (to_ann,) = mails_to(outbox, 'ann@example.com')
    assert '回复了你的评论' in to_ann.subject
    assert 'Thanks!' in to_ann.body
    assert mails_to(outbox, 'author@example.com')
    assert mails_to(outbox, 'admin@example.com') == []


def test_published_reply_tells_the_answered_commenter(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
        add_comment(post_id=users['post'], name='Bob',
                    email='bob@example.com')
    post_comment(client, users['post'], name='Bob', email='bob@example.com',
                 body='Agreed', parent_id=top)
    assert len(mails_to(outbox, 'ann@example.com')) == 1


def test_pending_reply_tells_the_answered_commenter_only_once_approved(
        client, application, outbox, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Ann',
                          email='ann@example.com', notify_replies=True)
    post_comment(client, users['post'], email='new@example.com', body='hi',
                 parent_id=top, notify='y')
    assert mails_to(outbox, 'ann@example.com') == []
    outbox.clear()

    with application.app_context():
        reply_id = comment_id_of('new@example.com')
    login(client, 'admin')
    client.post(f'/admin/comments/{reply_id}/approve')
    subjects = {m.recipients[0]: m.subject for m in outbox}
    assert '回复了你的评论' in subjects['ann@example.com']
    assert '通过审核' in subjects['new@example.com']


def test_dropped_comment_sends_nothing(client, application, outbox, users):
    post_comment(client, users['post'], website='http://bot.example')
    assert outbox == []
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count(PostComment.id))) == 0


def test_comments_work_when_mail_is_not_configured(
        client, application, outbox, users, monkeypatch):
    monkeypatch.setitem(application.config, 'MAIL_SERVER', '')
    response = post_comment(client, users['post'])
    assert response.status_code == 302
    assert outbox == []


def test_a_mail_failure_does_not_break_posting(
        client, application, outbox, users, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError('smtp down')

    monkeypatch.setattr('app.comment_mail.send_email', boom)
    response = post_comment(client, users['post'])
    assert response.status_code == 302
    with application.app_context():
        assert comment_id_of('reader@example.com') is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_comment_email_flow.py -q`
Expected: the "tells …" tests FAIL (outbox empty); the "sends nothing" / "not configured" / "failure" tests already pass.

- [ ] **Step 3: Wire the public route**

In `app/routes.py`:

- change the `app.comments` import to also bring in `PENDING`:

```python
from app.comments import (APPROVED, PENDING, CommentRejected, CommentsClosed,
                          comment_context, submit_comment)
```

- extend the `app.comment_mail` import added in Task 3:

```python
from app.comment_mail import (email_from_unsubscribe_token,
                              notify_comment_pending,
                              notify_comment_published, stop_notifications)
```

- in `_take_comment`, replace the part after `db.session.commit()` with:

```python
    db.session.commit()
    if result.outcome == APPROVED:
        notify_comment_published(result.comment)
        flash('你的评论已发布。')
        return redirect(destination(f'comment-{result.comment.id}'))
    if result.outcome == PENDING:
        notify_comment_pending(result.comment)
    flash('评论已提交，审核通过后显示。')
    return redirect(destination('comments'))
```

- [ ] **Step 4: Wire the admin views**

In `app/admin/modules.py`, extend the imports:

```python
from app.comment_mail import notify_comment_published, notify_comments_approved
```

`approve_comment`:

```python
def approve_comment(comment_id):
    if not BulkCommentForm().validate_on_submit():
        abort(400)
    comment = db.get_or_404(PostComment, comment_id)
    newly_approved = comment.status != 'approved'
    comment.status = 'approved'
    if not _commit_or_flash('评论保存失败，请重试。'):
        abort(500)
    if newly_approved:
        notify_comments_approved([comment])
    return _comments_back()
```

`bulk_comments` — replace the `for comment in selected:` loop and the commit with:

```python
    newly_approved = []
    for comment in selected:
        if action == 'approve':
            if comment.status != 'approved':
                newly_approved.append(comment)
            comment.status = 'approved'
        else:
            db.session.delete(comment)
    if not _commit_or_flash('批量操作失败，请重试。'):
        abort(500)
    notify_comments_approved(newly_approved)
```

`reply_comment` — keep the result of `submit_comment` and notify after the commit:

```python
    try:
        result = submit_comment(
            comment.post or comment.page, name=current_user.username,
            email=current_user.email, body=form.body.data,
            parent_id=comment.id, author=current_user)
    except CommentsClosed:
        ...
    if not _commit_or_flash('回复保存失败，请重试。'):
        abort(500)
    notify_comment_published(result.comment)
    flash('回复已发布。')
    return _comments_back()
```

(only the `result =` assignment and the `notify_comment_published` line are new; the `except` branches stay exactly as they are.)

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_comment_email_flow.py tests/test_comment_mail.py tests/test_admin_comments.py tests/test_comments_public.py tests/test_comment_service.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routes.py app/admin/modules.py tests/test_comment_email_flow.py
git commit -m "feat(comments): email on new comments, replies and approvals"
```

---

### Task 6: Docs and full verification

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] **Step 1: Update the docs**

In `README.md`:

- in the feature list, change `点赞与评论（两层回复、首次评论审核、受限 Markdown，可按文章或页面开关）` to `点赞与评论（两层回复、首次评论审核、受限 Markdown，可按文章或页面开关；新评论、回复和审核结果可邮件通知，评论者自愿勾选并可退订）`;
- in the configuration table, change `出错通知的收件人，多个地址用逗号分隔；` to `出错通知和新评论通知的收件人，多个地址用逗号分隔；`.

In `.env.example`, change line 12 to:

```
# 邮件（重置密码、评论通知、出错通知）。MAIL_SERVER 留空则不发邮件
```

- [ ] **Step 2: Run the whole suite**

Run (takes about 3.5 minutes; run it in the background and wait for completion): `.venv/bin/python -m pytest -q`
Expected: everything PASS (previously 923 tests, now more).

- [ ] **Step 3: Check for leaked mail config**

Run: `.venv/bin/python -m pytest -q tests/test_password_reset_email.py tests/test_comment_email_flow.py tests/test_comments_public.py -p no:randomly`
Expected: PASS. Then run `tests/test_comments_public.py` alone and confirm the same result, proving the mail fixtures leave no state behind.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example
git commit -m "docs: mention comment emails"
```

- [ ] **Step 5: Manual check in a real mailbox (after deploy)**

On a site with real `MAIL_*` settings: comment on a post with a throwaway address and the box ticked → owners get "新评论待审核"; approve it in the admin → you get "你的评论已通过审核"; reply to it from the admin → you get "有人回复了你的评论"; click 退订 in the email → confirm page → the next reply sends nothing.
