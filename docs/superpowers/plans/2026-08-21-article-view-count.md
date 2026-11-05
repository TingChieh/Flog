# Article View Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Count each browser's public visit to an article at most once per rolling 24-hour window and display the persisted count on article detail and list views.

**Architecture:** Add a database-backed counter to `Post`, but keep visitor deduplication in short-lived, timestamp-signed, article-scoped cookies. A focused `app/post_views.py` service owns cookie validation, response cookie creation, atomic SQL increments, rollback, and logging; the public article route only coordinates GET/POST behavior and rendering.

**Tech Stack:** Flask 3.1, Flask-SQLAlchemy/SQLAlchemy 2.0, Alembic/Flask-Migrate, itsdangerous 2.2, Jinja, pytest, MySQL production and SQLite tests.

## Global Constraints

- Count only valid `GET /post/<post_id>` requests for existing articles.
- Count at most once per browser, per article, during a rolling 24-hour window of exactly 86,400 seconds by default.
- Authors, administrators, authenticated members, and anonymous readers use the same counting rule.
- Never count comment POSTs, article lists, category/search/feed/RSS requests, administrative editing or preview requests, or missing articles.
- Persist no visitor identity or individual view event in the database.
- Use a timestamped `SECRET_KEY` signature and enforce both server-side signature age and browser `Max-Age`.
- Set view cookies with `HttpOnly`, `SameSite=Lax`, the exact public article path, and the application's secure-cookie setting.
- Increment with a database-side `view_count = view_count + 1` expression; never use a Python read-modify-write.
- A counting failure must roll back, be logged, leave the article readable, and omit the view cookie.
- Keep the existing process-local `SimpleCache` out of the counting path.
- Run the migration before deploying application code that selects `post.view_count`.
- Do not upgrade the production MySQL database without a separate explicit confirmation after implementation and scratch verification.

## File Structure

- Create `migrations/versions/c2f6e8a91d04_add_post_view_count.py`: add and remove the non-null counter at the current Alembic head.
- Create `app/post_views.py`: own marker naming/signing/validation, response cookie attributes, atomic increment, rollback, and error logging.
- Create `tests/test_post_views.py`: focused model, cookie, service, route, role, exclusion, and failure tests.
- Modify `app/models.py`: declare `Post.view_count` with matching application and server defaults.
- Modify `config.py`: define the 86,400-second view window.
- Modify `app/routes.py`: invoke the view service only for public article GET requests and attach the marker only after a successful count.
- Modify `app/templates/post/post.html`: render detail-page view metadata.
- Modify `app/templates/post/_post.html`: render list-page view metadata without triggering a count.
- Modify `app/static/style.css`: make detail/list view metadata fit existing desktop, mobile, and dark-mode styles.
- Modify `tests/test_migrations.py`: prove backfill, insert default, nullability, content preservation, and downgrade behavior.
- Modify `tests/test_ui_shell.py`: prove both public surfaces render the persisted count.

---

### Task 1: Persisted Counter And Migration

**Files:**
- Create: `migrations/versions/c2f6e8a91d04_add_post_view_count.py`
- Create: `tests/test_post_views.py`
- Modify: `app/models.py` in `Post`
- Modify: `config.py` in `Config`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: current Alembic head `b1d4e6f70819`; existing `Post` model and test database fixtures.
- Produces: `Post.view_count: int`, database column `post.view_count INTEGER NOT NULL DEFAULT 0`, and `Config.POST_VIEW_WINDOW_SECONDS: int`.

- [ ] **Step 1: Write failing model and migration tests**

Add the revision path and loader to `tests/test_migrations.py`:

```python
VIEW_COUNT_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'c2f6e8a91d04_add_post_view_count.py')


def load_view_count_revision():
    spec = importlib.util.spec_from_file_location(
        'post_view_count', VIEW_COUNT_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Add a migration test that preserves existing content, backfills zero, applies a
server default to later raw inserts, enforces non-null, and removes only the new
column on downgrade:

```python
def test_view_count_migration_backfills_and_preserves_existing_posts():
    revision = load_view_count_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(
            title='Existing', body='<p>Keep me</p>'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post (title, body) VALUES ('Later', '<p>New</p>')"))
            rows = connection.execute(sa.text(
                'SELECT title, body, view_count FROM post ORDER BY id'
            )).mappings().all()
            assert rows == [
                {'title': 'Existing', 'body': '<p>Keep me</p>', 'view_count': 0},
                {'title': 'Later', 'body': '<p>New</p>', 'view_count': 0},
            ]
            column = next(item for item in sa.inspect(connection).get_columns(
                'post') if item['name'] == 'view_count')
            assert column['nullable'] is False
            revision.downgrade()

        assert 'view_count' not in {
            item['name'] for item in sa.inspect(connection).get_columns('post')}
        assert connection.execute(sa.text(
            'SELECT title, body FROM post ORDER BY id'
        )).mappings().all()[0] == {
            'title': 'Existing', 'body': '<p>Keep me</p>'}
```

Create `tests/test_post_views.py` with imports and the model-default test:

```python
import sqlalchemy as sa

from app import db
from app.models import Category, Post, User


def test_new_post_defaults_view_count_to_zero(application):
    with application.app_context():
        author = User(username='counter-author', email='counter@example.com')
        category = Category(name='Counter')
        post = Post(title='Counter', body='Body', author=author,
                    category=category)
        db.session.add_all([author, category, post])
        db.session.flush()

        assert post.view_count == 0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_migrations.py::test_view_count_migration_backfills_and_preserves_existing_posts tests/test_post_views.py::test_new_post_defaults_view_count_to_zero -v
```

Expected: FAIL because the revision file and `Post.view_count` do not exist.

- [ ] **Step 3: Add the model field, configuration, and migration**

Add to `Post` in `app/models.py`:

```python
view_count: so.Mapped[int] = so.mapped_column(
    sa.Integer, nullable=False, default=0, server_default=sa.text('0'))
```

Add to `Config` in `config.py`:

```python
POST_VIEW_WINDOW_SECONDS = 24 * 60 * 60
```

Create `migrations/versions/c2f6e8a91d04_add_post_view_count.py`:

```python
"""add post view count"""
from alembic import op
import sqlalchemy as sa


revision = 'c2f6e8a91d04'
down_revision = 'b1d4e6f70819'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('post', sa.Column(
        'view_count', sa.Integer(), nullable=False,
        server_default=sa.text('0')))


def downgrade():
    op.drop_column('post', 'view_count')
```

- [ ] **Step 4: Run focused and migration-head tests**

Run:

```bash
.venv/bin/pytest tests/test_migrations.py tests/test_post_views.py -v
.venv/bin/flask db heads
```

Expected: all selected tests PASS and Flask-Migrate reports only
`c2f6e8a91d04 (head)`.

- [ ] **Step 5: Commit the persisted counter**

```bash
git add app/models.py config.py migrations/versions/c2f6e8a91d04_add_post_view_count.py tests/test_migrations.py tests/test_post_views.py
git commit -m "feat: persist article view counts"
```

---

### Task 2: Signed Marker And Atomic Counting Service

**Files:**
- Create: `app/post_views.py`
- Modify: `tests/test_post_views.py`

**Interfaces:**
- Consumes: `Post.view_count`, `Config.POST_VIEW_WINDOW_SECONDS`, Flask `SECRET_KEY`, `SESSION_COOKIE_SECURE`, and the active SQLAlchemy session.
- Produces: `view_cookie_name(post_id: int) -> str`, `has_recent_view(post_id: int, marker: str | None) -> bool`, `record_view(post: Post) -> bool`, and `attach_view_cookie(response: Response, post_id: int) -> None`.

- [ ] **Step 1: Write failing cookie behavior tests**

Extend `tests/test_post_views.py`:

```python
from http.cookies import SimpleCookie

from flask import Response
from itsdangerous import TimestampSigner

from app.post_views import (
    attach_view_cookie, has_recent_view, view_cookie_name,
)


def _cookie_from_response(response, post_id):
    jar = SimpleCookie()
    jar.load(response.headers['Set-Cookie'])
    return jar[view_cookie_name(post_id)]


def test_view_cookie_is_signed_scoped_and_accepted(application):
    with application.test_request_context('/post/42'):
        response = Response('article')
        attach_view_cookie(response, 42)
        cookie = _cookie_from_response(response, 42)

        assert cookie['max-age'] == '86400'
        assert cookie['path'] == '/post/42'
        assert cookie['httponly'] is True
        assert cookie['samesite'] == 'Lax'
        assert has_recent_view(42, cookie.value) is True
        assert has_recent_view(43, cookie.value) is False
        assert has_recent_view(42, f'{cookie.value}tampered') is False


def test_expired_view_cookie_is_rejected(application, monkeypatch):
    with application.test_request_context('/post/42'):
        monkeypatch.setattr(
            TimestampSigner, 'get_timestamp', lambda self: 1_000)
        response = Response('article')
        attach_view_cookie(response, 42)
        marker = _cookie_from_response(response, 42).value

        monkeypatch.setattr(
            TimestampSigner, 'get_timestamp', lambda self: 87_401)
        assert has_recent_view(42, marker) is False
```

- [ ] **Step 2: Write failing atomic increment and rollback tests**

Add these imports and tests to `tests/test_post_views.py`:

```python
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app.post_views import record_view


def test_record_view_uses_database_arithmetic(application, users):
    statements = []
    with application.app_context():
        engine = db.engine

        def capture_statement(conn, cursor, statement, parameters, context,
                              executemany):
            statements.append(statement)

        event.listen(engine, 'before_cursor_execute', capture_statement)
        try:
            post = db.session.get(Post, users['post'])
            assert record_view(post) is True
            assert post.view_count == 1
        finally:
            event.remove(engine, 'before_cursor_execute', capture_statement)

    update_sql = next(statement for statement in statements
                      if statement.lstrip().upper().startswith('UPDATE POST'))
    normalized = ' '.join(update_sql.lower().split())
    assert 'view_count=(post.view_count + ?)' in normalized


def test_record_view_rolls_back_and_logs(application, users, monkeypatch):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        rollback_calls = []
        log_calls = []
        monkeypatch.setattr(
            db.session, 'execute',
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SQLAlchemyError('counter unavailable')))
        monkeypatch.setattr(db.session, 'rollback',
                            lambda: rollback_calls.append(True))
        monkeypatch.setattr(application.logger, 'exception',
                            lambda *args, **kwargs: log_calls.append(args))

        assert record_view(post) is False
        assert rollback_calls == [True]
        assert len(log_calls) == 1
```

- [ ] **Step 3: Run service tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_post_views.py -v
```

Expected: collection FAILS because `app.post_views` does not exist.

- [ ] **Step 4: Implement the focused view-counting service**

Create `app/post_views.py`:

```python
from flask import Response, current_app, url_for
from itsdangerous import BadSignature, TimestampSigner
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Post


COOKIE_PREFIX = 'post_viewed_'
SIGNING_SALT = 'post-view-count'


def view_cookie_name(post_id: int) -> str:
    return f'{COOKIE_PREFIX}{post_id}'


def _signer() -> TimestampSigner:
    return TimestampSigner(current_app.config['SECRET_KEY'], salt=SIGNING_SALT)


def has_recent_view(post_id: int, marker: str | None) -> bool:
    if not marker:
        return False
    try:
        payload = _signer().unsign(
            marker,
            max_age=current_app.config['POST_VIEW_WINDOW_SECONDS'],
        )
    except BadSignature:
        return False
    return payload == str(post_id).encode('ascii')


def record_view(post: Post) -> bool:
    try:
        db.session.execute(
            sa.update(Post)
            .where(Post.id == post.id)
            .values(view_count=Post.view_count + 1)
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        db.session.refresh(post)
        return True
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            'Failed to increment view count for post %s', post.id)
        return False


def attach_view_cookie(response: Response, post_id: int) -> None:
    max_age = current_app.config['POST_VIEW_WINDOW_SECONDS']
    marker = _signer().sign(str(post_id).encode('ascii')).decode('ascii')
    response.set_cookie(
        view_cookie_name(post_id),
        marker,
        max_age=max_age,
        path=url_for('post', post_id=post_id),
        secure=bool(current_app.config.get('SESSION_COOKIE_SECURE', False)),
        httponly=True,
        samesite='Lax',
    )
```

If SQLite emits spacing different from the expected SQL string, normalize the
assertion only enough to accept dialect whitespace; retain the assertion that
the right-hand side references `post.view_count` instead of a Python literal.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_post_views.py -v
```

Expected: all service and model tests PASS.

Commit:

```bash
git add app/post_views.py tests/test_post_views.py
git commit -m "feat: count article views with signed markers"
```

---

### Task 3: Public Route Integration And Exclusion Matrix

**Files:**
- Modify: `app/routes.py` imports and `post(post_id)`
- Modify: `tests/test_post_views.py`

**Interfaces:**
- Consumes: all four public functions from `app.post_views` and Flask's `request.cookies`/`make_response`.
- Produces: public detail GET counting and response markers; all POST and non-detail paths remain unchanged.

- [ ] **Step 1: Write failing first-view and refresh tests**

Add to `tests/test_post_views.py`:

```python
def _view_count(application, post_id):
    with application.app_context():
        return db.session.get(Post, post_id).view_count


def test_first_detail_get_counts_and_refresh_does_not(
        client, application, users):
    first = client.get(f'/post/{users["post"]}')
    second = client.get(f'/post/{users["post"]}')

    assert first.status_code == 200
    assert view_cookie_name(users['post']) in first.headers['Set-Cookie']
    assert second.status_code == 200
    assert 'Set-Cookie' not in second.headers
    assert _view_count(application, users['post']) == 1


def test_invalid_marker_counts_again(client, application, users):
    path = f'/post/{users["post"]}'
    client.set_cookie(
        view_cookie_name(users['post']), 'invalid', path=path)

    response = client.get(path)

    assert response.status_code == 200
    assert view_cookie_name(users['post']) in response.headers['Set-Cookie']
    assert _view_count(application, users['post']) == 1
```

- [ ] **Step 2: Write failing cross-article, role, and exclusion tests**

Add `login` and parameterization imports, then add:

```python
import pytest

from tests.conftest import login


def test_different_articles_count_independently(client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.get(Category, 1)
        second = Post(title='Second', body='Second', author=author,
                      category=category)
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    client.get(f'/post/{users["post"]}')
    client.get(f'/post/{second_id}')

    assert _view_count(application, users['post']) == 1
    assert _view_count(application, second_id) == 1


@pytest.mark.parametrize('username', ['author', 'admin', 'other'])
def test_authenticated_roles_follow_the_same_rule(
        client, application, users, username):
    login(client, username)

    client.get(f'/post/{users["post"]}')
    client.get(f'/post/{users["post"]}')

    assert _view_count(application, users['post']) == 1


def test_comment_post_does_not_count(client, application, users):
    response = client.post(f'/post/{users["post"]}', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'body': 'Comment only',
    })

    assert response.status_code == 302
    assert 'Set-Cookie' not in response.headers
    assert _view_count(application, users['post']) == 0


@pytest.mark.parametrize('path', ['/', '/categories', '/rss'])
def test_non_detail_surfaces_do_not_count(
        client, application, users, path):
    response = client.get(path)

    assert response.status_code in (200, 404)
    assert _view_count(application, users['post']) == 0


def test_missing_post_does_not_set_view_cookie(client):
    response = client.get('/post/999999')

    assert response.status_code == 404
    assert 'Set-Cookie' not in response.headers
```

- [ ] **Step 3: Write the failing route-level degradation test**

Add:

```python
def test_count_failure_serves_article_without_marker(
        client, application, users, monkeypatch):
    monkeypatch.setattr('app.routes.record_view', lambda post: False)

    response = client.get(f'/post/{users["post"]}')

    assert response.status_code == 200
    assert 'Set-Cookie' not in response.headers
    assert _view_count(application, users['post']) == 0
```

- [ ] **Step 4: Run route tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_post_views.py -v
```

Expected: route tests FAIL because the public route does not call the service.

- [ ] **Step 5: Integrate counting into the public article route**

Add to `app/routes.py` imports:

```python
from app.post_views import (
    attach_view_cookie, has_recent_view, record_view, view_cookie_name,
)
```

Replace only the final rendering portion of `post(post_id)` so the existing
comment path remains unchanged:

```python
    counted = False
    if request.method == 'GET':
        marker = request.cookies.get(view_cookie_name(post.id))
        if not has_recent_view(post.id, marker):
            counted = record_view(post)

    response = make_response(render_template(
        'post/post.html', title=_('Post'), post=post, form=form,
        comments=post.comments,
    ))
    if counted:
        attach_view_cookie(response, post.id)
    return response
```

Do not add counting to any other route. Do not use `follow_redirects=True` in
the comment POST test because the intentional redirect GET is a real page view.

- [ ] **Step 6: Run focused and adjacent interaction tests**

Run:

```bash
.venv/bin/pytest tests/test_post_views.py tests/test_post_interactions.py tests/test_public_management_separation.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit route integration**

```bash
git add app/routes.py tests/test_post_views.py
git commit -m "feat: track public article detail views"
```

---

### Task 4: Public Count Presentation And Full Verification

**Files:**
- Modify: `app/templates/post/post.html`
- Modify: `app/templates/post/_post.html`
- Modify: `app/static/style.css`
- Modify: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: `Post.view_count` already loaded with each post query.
- Produces: `.post-view-count` on detail and list views, plus `.article-header__meta` for stable wrapping.

- [ ] **Step 1: Write failing detail and list rendering tests**

Add to `tests/test_ui_shell.py`:

```python
from app.models import Post


def test_public_article_surfaces_show_persisted_view_count(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.view_count = 7
        db.session.commit()

    homepage = client.get('/').get_data(as_text=True)
    detail = client.get(f'/post/{users["post"]}').get_data(as_text=True)

    assert 'class="post-view-count">7 views</span>' in homepage
    assert 'class="post-view-count">8 views</span>' in detail
```

The detail count is eight because that client has not viewed the article before
and the detail GET itself is counted. The homepage remains seven because list
rendering never increments.

- [ ] **Step 2: Run the rendering test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_ui_shell.py::test_public_article_surfaces_show_persisted_view_count -v
```

Expected: FAIL because neither template renders `.post-view-count`.

- [ ] **Step 3: Add count metadata to both templates**

In `app/templates/post/post.html`, replace the standalone time element with:

```jinja2
            <div class="article-header__meta">
                <time class="article-header__time">{{ moment(post.timestamp).fromNow() }}</time>
                <span class="post-view-count">{{ post.view_count }} {{ _('views') }}</span>
            </div>
```

In `app/templates/post/_post.html`, insert this immediately before the existing
`<time>`:

```jinja2
    <span class="post-view-count">{{ post.view_count }} {{ _('views') }}</span>
```

Do not add a link, button, tooltip, JavaScript, icon dependency, or extra query.

- [ ] **Step 4: Add restrained responsive styling**

Add beside the existing `.article-header__time` rules in
`app/static/style.css`:

```css
.article-header__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
}

.post-view-count {
    color: var(--text-secondary);
    font-size: 0.85rem;
    white-space: nowrap;
}
```

The existing `var(--text-secondary)` supports both light and dark modes. The
existing mobile `.editorial-post__meta { flex-wrap: wrap; }` prevents overlap;
do not add viewport-scaled typography.

- [ ] **Step 5: Run UI and focused feature tests**

Run:

```bash
.venv/bin/pytest tests/test_ui_shell.py tests/test_ui_pages.py tests/test_post_views.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 6: Rehearse the migration on a disposable SQLite database**

Run with an explicit disposable path, not the production URL:

```bash
scratch_db=$(mktemp /tmp/flog-view-count-XXXXXX.sqlite3)
DATABASE_URL="sqlite:///$scratch_db" SECRET_KEY=test .venv/bin/flask db upgrade
DATABASE_URL="sqlite:///$scratch_db" SECRET_KEY=test .venv/bin/flask db current
```

Expected: upgrade succeeds and current reports `c2f6e8a91d04 (head)`. Leave
cleanup of this disposable file to the execution environment's temporary-file
policy; do not run a broad delete command.

- [ ] **Step 7: Run complete automated verification**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app migrations
git diff --check
```

Expected: the full suite passes (baseline before this feature: 222 tests), Python
compilation succeeds, and `git diff --check` prints no errors.

- [ ] **Step 8: Perform browser checks on desktop and mobile**

Start the development server on an unused port:

```bash
.venv/bin/flask run --port 5001
```

Using the in-app browser, verify at desktop 1440x900 and mobile 390x844:

- The homepage count fits beside author/time metadata for the existing long-title fixture.
- The article detail count increments on the first visit and stays unchanged on refresh.
- A second article increments independently.
- The metadata does not overlap the title, body, actions, or mobile navigation.
- Light and dark modes retain readable contrast.
- No browser console errors occur.

Stop the development server after capturing the verification result.

- [ ] **Step 9: Commit presentation and verification tests**

```bash
git add app/templates/post/post.html app/templates/post/_post.html app/static/style.css tests/test_ui_shell.py
git commit -m "feat: display article view counts"
```

- [ ] **Step 10: Prepare production migration handoff**

Record the new head, focused/full test results, browser checks, and migration
rehearsal in the final handoff. Ask for explicit confirmation before backing up
or upgrading the configured production MySQL database. The eventual deployment
order is backup, `flask db upgrade`, verify `post.view_count` and Alembic head,
then restart the new application code.
