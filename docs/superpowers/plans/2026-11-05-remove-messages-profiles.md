# Remove Private Messages, User Profiles And Post Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete private messages, public profile pages (edit form and popover) and the post-export background job, plus the `Message`, `Notification` and `Task` models and tables.

**Architecture:** A new Alembic revision drops the three tables. The user-facing routes, templates, forms and `base.html` scripts go in one commit (they reference each other through `url_for` and `redirect`), then the models, task code and `rq` dependency, then CSS/docs/translations.

**Tech Stack:** Flask, SQLAlchemy 2.x, Alembic, Flask-Babel, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-05-remove-messages-profiles-design.md`. Branch `feat/remove-messages-profiles` already exists; never commit to `main`.
- Run tests from the repo root: `.venv/bin/python -m pytest -q` and `node --test tests/*.test.js`. Baseline: **559 pytest passed, 40 node passed**.
- Migration revision id `5a1f9c0d7e42`, `down_revision = 'bad2dd157a5f'`. SQLAlchemy/Alembic operations only; drop each table only if it exists; log row counts; downgrade recreates the three tables empty with their current model columns, indexes and foreign keys to `user`.
- Keep: `User.last_seen` and its `before_request` update, `User.about_me` and `User.last_message_read_time` columns (no change to the `user` table), registration, login, password reset, `app/email.py`, `app.redis`, `REDIS_URL` settings and the Redis check in the admin environment page, the `redis` package, the reserved slug `messages`, `.search-pagination` CSS.
- A test is deleted only if it exercises a removed feature; any other failure must be fixed.
- Stage only the files each task changes; never `git add -A`.
- UI is Chinese-only; user-visible strings use `_()` or Chinese literals like the surrounding code.

## File Structure

- Create `migrations/versions/5a1f9c0d7e42_remove_messages_profiles_tasks.py`, `tests/test_messages_profiles_removed.py`.
- Modify `tests/test_migrations.py`, `app/routes.py`, `app/forms.py`, `app/models.py`, `app/__init__.py`, `app/templates/base.html`, `app/templates/post/post.html`, `flog.py`, `requirements.in`, `requirements.txt`, `app/static/style.css`, `README.md`, `app/translations/zh/LC_MESSAGES/messages.{po,mo}`, the spec's delivery section.
- Delete: `app/templates/{messages,send_message,edit_profile,_message,_pager}.html`, `app/templates/user/{user,user_popup}.html`, `app/tasks.py`, `app/templates/email/export_posts.{html,txt}`, `tests/test_public_profiles.py`, `tests/test_tasks.py`.

---

### Task 1: Migration

**Files:**
- Create: `migrations/versions/5a1f9c0d7e42_remove_messages_profiles_tasks.py`
- Modify: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_migrations.py`, after `MODULE_REMOVAL_REVISION_PATH` add:

```python
MESSAGES_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    '5a1f9c0d7e42_remove_messages_profiles_tasks.py')
```

After `load_module_removal_revision` add:

```python
def load_messages_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_messages_profiles_tasks', MESSAGES_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Change the head assertion in `test_drafts_revision_is_the_only_head` to `['5a1f9c0d7e42']`. Append:

```python
def _messages_removal_tables(metadata):
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(64), nullable=False))
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False))
    legacy = {
        'message': sa.Table(
            'message', metadata, sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('sender_id', sa.Integer, sa.ForeignKey('user.id'))),
        'notification': sa.Table(
            'notification', metadata, sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'))),
        'task': sa.Table(
            'task', metadata, sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'))),
    }
    return users, posts, legacy


def test_messages_removal_upgrade_drops_tables_and_keeps_content(caplog):
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users, posts, legacy = _messages_removal_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(users.insert().values(id=1, username='author'))
        connection.execute(posts.insert().values(id=7, title='Preserved'))
        connection.execute(legacy['message'].insert().values(id=1, sender_id=1))
        connection.execute(legacy['notification'].insert().values(id=1, user_id=1))
        connection.execute(legacy['task'].insert().values(id='t1', user_id=1))
        context = MigrationContext.configure(connection)
        with caplog.at_level(logging.INFO, logger='alembic.runtime.migration'):
            with Operations.context(context):
                revision.upgrade()

        tables = sa.inspect(connection).get_table_names()
        assert {'message', 'notification', 'task'}.isdisjoint(tables)
        assert connection.execute(sa.text(
            'SELECT username FROM user')).scalars().all() == ['author']
        assert connection.execute(sa.text(
            'SELECT title FROM post')).scalars().all() == ['Preserved']
    messages = ' '.join(record.getMessage() for record in caplog.records)
    for name in ('message', 'notification', 'task'):
        assert name in messages


def test_messages_removal_upgrade_tolerates_missing_tables():
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()


def test_messages_removal_downgrade_recreates_empty_tables():
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _messages_removal_tables(metadata)
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()
        inspector = sa.inspect(connection)
        columns = {name: {c['name'] for c in inspector.get_columns(name)}
                   for name in ('message', 'notification', 'task')}
        assert columns['message'] == {
            'id', 'sender_id', 'recipient_id', 'body', 'timestamp'}
        assert columns['notification'] == {
            'id', 'name', 'user_id', 'timestamp', 'payload_json'}
        assert columns['task'] == {
            'id', 'name', 'description', 'user_id', 'complete'}
        for name in columns:
            assert connection.execute(sa.text(
                f'SELECT COUNT(*) FROM {name}')).scalar_one() == 0
        indexed = {name: {tuple(i['column_names'])
                          for i in inspector.get_indexes(name)}
                   for name in columns}
        assert {('sender_id',), ('recipient_id',), ('timestamp',)} <= indexed['message']
        assert {('name',), ('user_id',), ('timestamp',)} <= indexed['notification']
        assert ('name',) in indexed['task']
        assert {fk['referred_table'] for fk in inspector.get_foreign_keys('message')} == {'user'}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -q -k "messages_removal or only_head"`
Expected: FAIL.

- [ ] **Step 3: Create the migration**

```python
"""remove private messages, notifications and background tasks

Upgrade permanently drops the message, notification and task tables with all
their rows. Downgrade recreates them empty; deleted rows are unrecoverable.

Revision ID: 5a1f9c0d7e42
Revises: bad2dd157a5f
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = '5a1f9c0d7e42'
down_revision = 'bad2dd157a5f'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')
DROPPED_TABLES = ('message', 'notification', 'task')


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    for name in DROPPED_TABLES:
        if name not in tables:
            continue
        rows = connection.execute(sa.select(sa.func.count()).select_from(
            sa.table(name))).scalar_one()
        log.info('Dropping table %s (%s rows)', name, rows)
        op.drop_table(name)


def downgrade():
    op.create_table(
        'message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('recipient_id', sa.Integer(), nullable=False),
        sa.Column('body', sa.String(length=140), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sender_id'], ['user.id']),
        sa.ForeignKeyConstraint(['recipient_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_message_sender_id', 'message', ['sender_id'])
    op.create_index('ix_message_recipient_id', 'message', ['recipient_id'])
    op.create_index('ix_message_timestamp', 'message', ['timestamp'])
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_name', 'notification', ['name'])
    op.create_index('ix_notification_user_id', 'notification', ['user_id'])
    op.create_index('ix_notification_timestamp', 'notification', ['timestamp'])
    op.create_table(
        'task',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=128), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_name', 'task', ['name'])
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 5: Verify a real upgrade and downgrade**

Build a scratch DB from the current models, stamp, seed, upgrade, downgrade (the historical migration chain cannot be replayed on an empty SQLite database, so `stamp` is used):

```bash
S="$SCRATCH"  # a scratch directory outside the repository
rm -f $S/migrate2.sqlite3
export SECRET_KEY=x MAIL_SERVER= DATABASE_URL=sqlite:///$S/migrate2.sqlite3
PYTHONPATH=$PWD .venv/bin/python - <<'EOF'
from app import app, db
from app.models import Message, Notification, SiteSettings, Task, User
with app.app_context():
    db.create_all(); db.session.add(SiteSettings(id=1))
    a = User(username='a', email='a@x.com'); b = User(username='b', email='b@x.com')
    db.session.add_all([a, b]); db.session.commit()
    db.session.add_all([Message(author=a, recipient=b, body='hi'),
                        Notification(name='n', user=a, payload_json='{}'),
                        Task(id='t1', name='export_posts', user=a)])
    db.session.commit()
EOF
.venv/bin/flask --app flog.py db stamp bad2dd157a5f
.venv/bin/flask --app flog.py db upgrade 2>&1 | grep -iE "dropping|error"
sqlite3 $S/migrate2.sqlite3 "select name from sqlite_master where type='table' and name in ('message','notification','task','user','post');"
.venv/bin/flask --app flog.py db downgrade 2>&1 | grep -iE "downgrade|error"
sqlite3 $S/migrate2.sqlite3 "select name from sqlite_master where type='table' and name in ('message','notification','task');"
```
Expected: three `Dropping table ... (1 rows)` lines; only `user` (and `post`) remain after upgrade; the three tables are back after downgrade.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/5a1f9c0d7e42_remove_messages_profiles_tasks.py tests/test_migrations.py
git commit -m "feat(db): migration dropping message, notification and task tables"
```

---

### Task 2: Routes, templates, forms and scripts

**Files:**
- Modify: `app/routes.py`, `app/forms.py`, `app/templates/base.html`, `app/templates/post/post.html`
- Delete: `app/templates/messages.html`, `send_message.html`, `edit_profile.html`, `_message.html`, `_pager.html`, `user/user.html`, `user/user_popup.html`
- Create: `tests/test_messages_profiles_removed.py`
- Delete: `tests/test_public_profiles.py`
- Modify: `tests/test_public_pages_consistency.py`, `tests/test_ui_pages.py`, `tests/test_public_management_separation.py` (only if it fails)

**Interfaces:** `Message`, `Notification`, `Task` models and `app.tasks` still exist after this task (removed in Task 3).

- [ ] **Step 1: Write the failing tests**

`tests/test_messages_profiles_removed.py`:

```python
import pytest
from lxml import html as lxml_html

from tests.conftest import login


@pytest.mark.parametrize('path', [
    '/messages', '/user/author', '/user/author/popup', '/edit_profile',
    '/send_message/other', '/export_posts', '/notifications', '/test_redis',
])
def test_removed_urls_are_not_found(client, users, path):
    assert client.get(path).status_code == 404
    login(client, 'author')
    assert client.get(path).status_code == 404


def test_article_author_is_plain_text(client, users):
    body = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    page = lxml_html.fromstring(body)
    header = page.xpath('//header[contains(@class, "article-header")]')[0]
    assert not header.xpath('.//a')
    assert header.xpath('.//img[contains(@class, "article-header__avatar")]')
    assert 'author' in header.text_content()
    assert 'user_popup' not in body


def test_base_template_has_no_popover_or_notification_scripts(client, users):
    login(client, 'author')
    body = client.get('/').get_data(as_text=True)
    for fragment in ('initialize_popovers', 'initialize_notifications',
                     'message_count', '/notifications', '-progress'):
        assert fragment not in body, fragment
```

(If `/user/author` fails with 405 rather than 404 for some path, adjust that single case to accept 405 and note why; the paths above should all fall through to 404.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_messages_profiles_removed.py -q`
Expected: FAIL.

- [ ] **Step 3: Remove the code**

`app/routes.py`: delete the functions `user`, `user_popup`, `edit_profile`, `send_message`, `messages`, `notifications`, `export_posts`, `test_redis` with their decorators (use `ast` to find the line ranges: for each top-level `FunctionDef` with that name take `min(decorator linenos)` to `end_lineno`). Imports: drop `EditProfileForm` and `MessageForm` from the `app.forms` import and `Message`, `Notification` from the `app.models` import. Keep `datetime`/`timezone` (used by `before_request`). Check `grep -n "published_post_statement" app/routes.py` still has users (it does: home, archive, feed).

`app/forms.py`: delete `EditProfileForm` and `MessageForm`; drop imports that become unused (check each name with `grep -c`).

`app/templates/post/post.html`: replace the `<header class="article-header">` author block with:

```html
    <header class="article-header">
        <img src="{{ post.author.avatar(70) }}" class="article-header__avatar" width="70" height="70" alt="{{ post.author.username }}">
        <div>
            <span class="article-header__author">{{ post.author.username }}</span>
            <div class="article-header__meta">
                <time class="article-header__time">{{ moment(post.timestamp).fromNow() }}</time>
                <span class="post-view-count">{{ post.view_count }} {{ _('views') }}</span>
            </div>
        </div>
    </header>
```

`app/templates/base.html`: delete the task-progress banner (`{% if current_user.is_authenticated %}{% with tasks = current_user.get_tasks_in_progress() %} ... {% endwith %}{% endif %}` inside `<main>`), and delete the whole inline `<script>` block that defines `initialize_popovers` and `initialize_notifications`. Keep `{{ moment.include_moment() }}` and `{{ moment.lang(g.locale) }}`.

Delete templates:

```bash
git rm -q app/templates/messages.html app/templates/send_message.html app/templates/edit_profile.html app/templates/_message.html app/templates/_pager.html app/templates/user/user.html app/templates/user/user_popup.html tests/test_public_profiles.py
```
(Confirm `_pager.html` has no users: `grep -rn "_pager" app` must be empty.)

Verify no dangling references:

```bash
grep -rnE "url_for\('(user|user_popup|edit_profile|send_message|messages|notifications|export_posts|test_redis)'" app
grep -rnE "get_tasks_in_progress|get_task_in_progress|user_popup|message_count" app
```
Expected: no output (models still define the task methods; templates must not call them).

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_messages_profiles_removed.py -q`
Expected: PASS.

- [ ] **Step 5: Fix tests of removed features**

Run the full suite; for each failure:
- `tests/test_public_pages_consistency.py`: delete `test_signed_in_form_pages_use_public_form_shell`, `test_messages_page_uses_public_list`, `test_message_rows_use_small_avatars`, `test_profile_page_uses_public_layout`, `test_profile_pagination_uses_pager`, `test_user_popup_has_no_inline_styles`; in `test_new_public_page_strings_are_chinese` keep only the reset-password and category assertions and drop the login/messages/profile lines; remove helpers and imports that become unused (`assert_public_list` stays if a test still uses it).
- `tests/test_ui_pages.py`: delete `test_authenticated_profile_and_messages_use_shared_sections`.
- `tests/test_public_management_separation.py` and any other failure: fix only the part that mentions the removed profile/popup surface; do not weaken unrelated assertions.

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app tests
git commit -m "refactor: remove messages, profiles, popover and export routes"
```

---

### Task 3: Models, tasks and the queue

**Files:**
- Modify: `app/models.py`, `app/__init__.py`, `flog.py`, `requirements.in`, `requirements.txt`
- Delete: `app/tasks.py`, `app/templates/email/export_posts.html`, `app/templates/email/export_posts.txt`, `tests/test_tasks.py`
- Modify: `tests/test_messages_profiles_removed.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_messages_profiles_removed.py`:

```python
from pathlib import Path


def test_removed_models_and_user_methods_are_gone():
    import app as flog
    import app.models as models
    for name in ('Message', 'Notification', 'Task'):
        assert not hasattr(models, name), name
    for name in ('unread_message_count', 'add_notification', 'launch_task',
                 'get_tasks_in_progress', 'get_task_in_progress'):
        assert not hasattr(models.User, name), name
    assert not hasattr(flog.app, 'task_queue')
    assert hasattr(flog.app, 'redis')


def test_task_module_templates_and_rq_requirement_are_gone():
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'app' / 'tasks.py').exists()
    assert not (root / 'app' / 'templates' / 'email' / 'export_posts.html').exists()
    assert not (root / 'app' / 'templates' / 'email' / 'export_posts.txt').exists()
    for name in ('requirements.in', 'requirements.txt'):
        lines = [line.split('==')[0].strip() for line in
                 (root / name).read_text().splitlines()
                 if line and not line.startswith(('#', ' '))]
        assert 'rq' not in lines, name
        assert 'redis' in lines, name
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_messages_profiles_removed.py -q`
Expected: FAIL.

- [ ] **Step 3: Remove the code**

`app/models.py`:
- Delete classes `Message`, `Notification`, `Task` (use `ast` ranges).
- In `User`, delete the methods `unread_message_count`, `add_notification`, `launch_task`, `get_tasks_in_progress`, `get_task_in_progress`, and the relationship attributes `messages_sent`, `messages_received`, `notifications`, `tasks` (each is a two- or one-line statement inside the class body; remove exactly those). Keep `last_message_read_time`.
- Remove imports that become unused; check each with `grep -c`: `redis`, `rq`, `json`, `current_app`. (`from time import time` stays: reset token.)

`app/__init__.py`: delete `import rq` and the line `app.task_queue = rq.Queue('flog-task', connection=app.redis)`; keep `from redis import Redis` and `app.redis = ...`.

`flog.py`: remove `Message`, `Notification`, `Task` from the import and from `make_shell_context`.

`requirements.in`: delete the `rq` line. `requirements.txt`: delete the `rq==...` line and any `# via rq` comment lines that no longer have a requester; leave other pins alone. Check what else lists only `rq` as its requester with `grep -n "via rq\|# rq" requirements.txt`; a package whose only `via` is `rq` (for example `croniter`) is removed too, with its own comment lines.

Delete files:

```bash
git rm -q app/tasks.py app/templates/email/export_posts.html app/templates/email/export_posts.txt tests/test_tasks.py
```

Verify: `grep -rnE "\b(Message|Notification|Task)\b|task_queue|import rq|app\.tasks" app flog.py tests --include='*.py'` shows no hits other than test strings in `tests/test_messages_profiles_removed.py` and `tests/test_migrations.py`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. Fix any other failure by tracing it to the removal; do not delete tests that do not exercise a removed feature.

- [ ] **Step 5: Commit**

```bash
git add app flog.py requirements.in requirements.txt tests
git commit -m "refactor: remove Message, Notification and Task models, export job and rq"
```

---

### Task 4: CSS, docs, translations, verification

**Files:**
- Modify: `app/static/style.css`, `README.md`, `app/translations/zh/LC_MESSAGES/messages.{po,mo}`, `tests/test_ui_shell.py`, the spec's delivery section

- [ ] **Step 1: Remove dead CSS**

```bash
grep -nE "profile|message-row|user-popup|user_popup|\.popover" app/static/style.css
for c in profile-layout profile-avatar profile-details profile-actions profile-meta profile-posts message-row user-popup user_popup; do printf "%-16s %s\n" $c "$(grep -rl "$c" app/templates app/static/*.js | tr '\n' ' ')"; done
```
For classes with no remaining template/script reference, delete their rules with a script that parses leaf rules and removes dead selectors from selector lists (same approach as the previous module-removal commit: regex over `selector { body }` leaf rules, drop empty `@media` blocks, assert `{`/`}` counts balance). Keep `.article-header__author` (still used) and `.search-pagination`.

Delete `test_profile_details_allow_long_profile_text_to_wrap` from `tests/test_ui_shell.py`.

- [ ] **Step 2: README**

Edit `README.md`: remove the profile, private-message and notification items from the feature list (`- 用户：…`: keep registration/login/password reset), remove the `- 后台任务：Redis + RQ …` line and the `Redis、RQ` technology line, delete the "文章导出等异步任务需要 Redis" section with the `rq worker` command, and change the `REDIS_URL` table row to say it is only used by the environment page's Redis check. In the upgrade section add: "迁移 `5a1f9c0d7e42` 会永久删除私信、通知和后台任务三张表的数据。"

- [ ] **Step 3: Translations**

```bash
export PATH="$PWD/.venv/bin:$PATH"
pybabel extract -F babel.cfg -k _l -o messages.pot . && pybabel update -i messages.pot -d app/translations && rm -f messages.pot
.venv/bin/python - <<'EOF'
from babel.messages.pofile import read_po
cat = read_po(open('app/translations/zh/LC_MESSAGES/messages.po','rb'), locale='zh')
for m in cat:
    if not m.id: continue
    missing = (not all(m.string)) if isinstance(m.id, tuple) else (not m.string)
    if missing or m.fuzzy:
        print(('FUZZY ' if m.fuzzy else 'EMPTY ') + repr(m.id) + ' -> ' + repr(m.string))
EOF
pybabel compile -d app/translations
```
Fix any fuzzy/empty entry that is still in use (set the correct Chinese string, clear the fuzzy flag with babel's `read_po`/`write_po`, then recompile). Obsolete `#~` entries may stay.

- [ ] **Step 4: Update the spec's delivery section**

In `docs/superpowers/specs/2026-11-05-remove-messages-profiles-design.md` replace the five-step list under "Delivery" with the four commits actually made: migration; routes, templates, forms and scripts; models, tasks and queue; CSS, README, translations and verification, and add one sentence saying the first non-migration commit combines them because the routes redirect to each other through `url_for`.

- [ ] **Step 5: Full verification**

```bash
.venv/bin/python -m pytest -q
node --test tests/*.test.js
```
Expected: all pass; record the counts.

- [ ] **Step 6: Visual verification (playwright skill)**

Seed a scratch database under the scratchpad directory (`db.create_all()`: admin user, a category, two posts, one content page in nav), run `flask run -p 5055`, drive the browser with `bash $HOME/.claude/skills/playwright/scripts/playwright_cli.sh` (the script is not executable directly), and confirm: signed-in home shows no console errors and no polling requests to `/notifications`; the article page shows the author name and avatar as plain text; `/messages`, `/user/aisaka`, `/edit_profile` show the 404 page; the footer still shows 管理 and 登出. Stop the server and close the browser afterwards.

- [ ] **Step 7: Commit**

```bash
git add app/static/style.css README.md app/translations tests docs/superpowers/specs/2026-11-05-remove-messages-profiles-design.md
git commit -m "chore: remove profile and message CSS and docs, refresh translations"
```

---

## Self-Review

- **Spec coverage:** messages (routes, forms, templates, model, `unread_message_count`) Tasks 2-3; profiles (routes, popup, edit form, templates, popover script, article author) Task 2; export (route, `tasks.py`, email templates, `launch_task` family, `Task`) Tasks 2-3; notifications (route, model, `add_notification`, polling script, banner) Tasks 2-3; `task_queue`, `rq`, `/test_redis` Tasks 2-3; shell context Task 3; migration with row-count logging and empty-table downgrade Task 1; README, CSS, translations Task 4; kept items listed in Global Constraints.
- **Deviation from spec:** four commits instead of five, because the routes, templates and scripts reference each other (`redirect(url_for('user'))`, `url_for('notifications')` in `base.html`); Task 4 Step 4 updates the spec's Delivery section.
- **Placeholders:** none; file lists, deletion names and commands are explicit. The `ast` range removal is the same method used in the previous removal.
- **Consistency:** revision id `5a1f9c0d7e42` / down revision `bad2dd157a5f` used identically in the migration, the head test and the Task 1 stamp step.
