# Remove The Built-in Site Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Links, Guestbook, Todo and Movie modules (routes, models, forms, templates, admin, CSS) and drop their data with one Alembic migration, leaving custom content pages as the only page kind.

**Architecture:** A new migration deletes `kind='module'` pages (and their redirects) and drops the four tables. The admin, then the public side and models, then the page logic are removed in separate commits so the full suite is green after each. `Page.kind` / `Page.module_key` columns and their CHECK constraints stay in the schema.

**Tech Stack:** Flask, SQLAlchemy 2.x, Alembic, Flask-Babel, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-05-remove-site-modules-design.md`.
- Work on branch `feat/remove-modules` (already created from `main`). Never commit to `main`.
- Run tests from the repo root with `.venv/bin/python -m pytest -q`; JS tests with `node --test tests/*.test.js`. Baseline before this plan: **628 pytest passed, 40 node passed**.
- Keep `PostComment`, `PostCommentForm`, article comments, `_pager.html`, `.search-pagination`, About (a content page), `_commit_legacy_mutation`, `_page_for_legacy_slug`.
- Do not change the `Page` table schema, its CHECK constraints, or the `Page` model columns.
- Migration: SQLAlchemy/Alembic operations only (no dialect-specific SQL); delete `page_redirect` rows explicitly (SQLite does not enforce `ON DELETE CASCADE`); drop each table only if it exists; log removed row counts; downgrade recreates the four tables empty.
- New migration revision id `bad2dd157a5f`, `down_revision = 'b5e1a7c9d234'`.
- A removed test is deleted only when it exercises a removed feature; any other failing test must be fixed, not deleted.
- Each commit stages only the files it changes. Never `git add -A`.
- The site UI is Chinese-only; user-visible strings use `_()` or Chinese literals like the surrounding code.

## File Structure

- Create `migrations/versions/bad2dd157a5f_remove_site_modules.py`.
- Create `tests/test_site_modules_removed.py` (behaviour tests for Tasks 2-4).
- Modify `tests/test_migrations.py` (new loader, three migration tests, head id).
- Modify `app/admin/modules.py`, `app/admin/forms.py`, `app/admin/pages.py`, `app/templates/admin/base.html`, `app/templates/admin/comments/list.html`, `app/templates/admin/pages/list.html`, `app/templates/admin/pages/form.html`.
- Modify `app/routes.py`, `app/forms.py`, `app/models.py`, `app/pages.py`.
- Delete templates: `links.html`, `edit_link.html`, `movie/`, `todo/`, `comment/`, `admin/modules/`.
- Modify `app/static/style.css`, `README.md`, `app/translations/zh/LC_MESSAGES/messages.{po,mo}`.
- Delete or trim tests that covered the removed features (named per task).

---

### Task 1: Migration

**Files:**
- Create: `migrations/versions/bad2dd157a5f_remove_site_modules.py`
- Modify: `tests/test_migrations.py` (add near the other `*_REVISION_PATH` constants and loaders; update `test_drafts_revision_is_the_only_head`)

**Interfaces:**
- Produces: head revision `bad2dd157a5f`; module attribute names `upgrade()` / `downgrade()`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_migrations.py`, after `EDITOR_ORDERING_REVISION_PATH`, add:

```python
MODULE_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'bad2dd157a5f_remove_site_modules.py')
```

After `load_editor_ordering_revision`, add:

```python
def load_module_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_site_modules', MODULE_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Change the head assertion in `test_drafts_revision_is_the_only_head` to `['bad2dd157a5f']`. Append at the end of the file:

```python
def _module_removal_tables(metadata):
    users = sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False))
    pages = sa.Table(
        'page', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('slug', sa.String(120), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('module_key', sa.String(20)))
    redirects = sa.Table(
        'page_redirect', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('slug', sa.String(120), nullable=False),
        sa.Column('page_id', sa.Integer, sa.ForeignKey('page.id'), nullable=False))
    legacy = {
        'todo': sa.Table('todo', metadata, sa.Column('id', sa.Integer, primary_key=True),
                         sa.Column('title', sa.String(120))),
        'movie': sa.Table('movie', metadata, sa.Column('id', sa.Integer, primary_key=True),
                          sa.Column('title', sa.String(60))),
        'link': sa.Table('link', metadata, sa.Column('id', sa.Integer, primary_key=True),
                         sa.Column('name', sa.String(64))),
        'comment': sa.Table('comment', metadata, sa.Column('id', sa.Integer, primary_key=True),
                            sa.Column('name', sa.String(64))),
    }
    return users, posts, pages, redirects, legacy


def test_module_removal_upgrade_drops_module_data_and_keeps_content(caplog):
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _, posts, pages, redirects, legacy = _module_removal_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(id=7, title='Preserved'))
        connection.execute(pages.insert(), [
            {'id': 1, 'slug': 'about', 'kind': 'content', 'module_key': None},
            {'id': 2, 'slug': 'links', 'kind': 'module', 'module_key': 'links'},
            {'id': 3, 'slug': 'guestbook', 'kind': 'module', 'module_key': 'guestbook'},
            {'id': 4, 'slug': 'notes', 'kind': 'content', 'module_key': None},
        ])
        connection.execute(redirects.insert(), [
            {'id': 1, 'slug': 'old-links', 'page_id': 2},
            {'id': 2, 'slug': 'old-notes', 'page_id': 4},
        ])
        for table in legacy.values():
            connection.execute(table.insert().values(id=1))
        context = MigrationContext.configure(connection)
        with caplog.at_level(logging.INFO, logger='alembic.runtime.migration'):
            with Operations.context(context):
                revision.upgrade()

        tables = sa.inspect(connection).get_table_names()
        assert {'todo', 'movie', 'link', 'comment'}.isdisjoint(tables)
        assert connection.execute(sa.text(
            'SELECT slug FROM page ORDER BY id')).scalars().all() == ['about', 'notes']
        assert connection.execute(sa.text(
            'SELECT slug FROM page_redirect')).scalars().all() == ['old-notes']
        assert connection.execute(sa.text(
            'SELECT title FROM post')).scalars().all() == ['Preserved']
    messages = ' '.join(record.getMessage() for record in caplog.records)
    for name in ('todo', 'movie', 'link', 'comment', 'module pages'):
        assert name in messages


def test_module_removal_upgrade_tolerates_missing_tables():
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('page', metadata, sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('kind', sa.String(20), nullable=False))
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
        assert sa.inspect(connection).get_table_names() == ['page']

    bare = sa.create_engine('sqlite://')
    with bare.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()


def test_module_removal_downgrade_recreates_empty_tables():
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _module_removal_tables(metadata)
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()
        inspector = sa.inspect(connection)
        columns = {name: {c['name'] for c in inspector.get_columns(name)}
                   for name in ('todo', 'movie', 'link', 'comment')}
        assert columns['todo'] == {'id', 'title', 'complete'}
        assert columns['movie'] == {'id', 'title', 'year'}
        assert columns['link'] == {'id', 'name', 'email', 'text', 'url', 'created_at'}
        assert columns['comment'] == {'id', 'email', 'name', 'body', 'timestamp'}
        for name in columns:
            assert connection.execute(sa.text(
                f'SELECT COUNT(*) FROM {name}')).scalar_one() == 0
        assert {'ix_comment_timestamp'} <= {
            index['name'] for index in inspector.get_indexes('comment')}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -q -k "module_removal or only_head"`
Expected: FAIL (revision file missing / head mismatch).

- [ ] **Step 3: Create the migration**

`migrations/versions/bad2dd157a5f_remove_site_modules.py`:

```python
"""remove the built-in site modules

Upgrade permanently deletes module pages (and their redirects) and drops the
todo, movie, link and comment (guestbook) tables with all their rows.
Downgrade recreates the four tables empty; deleted rows and module pages are
unrecoverable.

Revision ID: bad2dd157a5f
Revises: b5e1a7c9d234
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'bad2dd157a5f'
down_revision = 'b5e1a7c9d234'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')
MODULE_TABLES = ('todo', 'movie', 'link', 'comment')


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())

    if 'page' in tables:
        page = sa.table('page', sa.column('id'), sa.column('kind'))
        module_ids = sa.select(page.c.id).where(page.c.kind == 'module')
        if 'page_redirect' in tables:
            redirect = sa.table('page_redirect', sa.column('page_id'))
            result = connection.execute(
                sa.delete(redirect).where(redirect.c.page_id.in_(module_ids)))
            log.info('Removed %s redirects of module pages', result.rowcount)
        result = connection.execute(
            sa.delete(page).where(page.c.kind == 'module'))
        log.info('Removed %s module pages', result.rowcount)

    for name in MODULE_TABLES:
        if name not in tables:
            continue
        rows = connection.execute(sa.select(sa.func.count()).select_from(
            sa.table(name))).scalar_one()
        log.info('Dropping table %s (%s rows)', name, rows)
        op.drop_table(name)


def downgrade():
    op.create_table(
        'todo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'movie',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=60), nullable=False),
        sa.Column('year', sa.String(length=5), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'link',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('text', sa.String(length=128), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('body', sa.String(length=240), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_comment_timestamp', 'comment', ['timestamp'])
```

Note for the downgrade test: the hand-built `todo` table in `_module_removal_tables` has only `id, title`; `upgrade()` drops it, `downgrade()` recreates it with the full column set, which is what the test asserts.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 5: Verify against a real upgrade path**

Run (from the repo root; scratch DB path in the scratchpad directory, never `instance/`):

```bash
S="$SCRATCH"  # a scratch directory outside the repository
rm -f $S/migrate.sqlite3
DATABASE_URL=sqlite:///$S/migrate.sqlite3 .venv/bin/flask --app flog.py db upgrade b5e1a7c9d234
DATABASE_URL=sqlite:///$S/migrate.sqlite3 .venv/bin/flask --app flog.py db upgrade
sqlite3 $S/migrate.sqlite3 ".tables"
```
Expected: the second upgrade logs `Removed 4 module pages` and the `Dropping table ...` lines; `.tables` lists neither `todo`, `movie`, `link` nor `comment`, and still lists `page`, `post`, `post_comment`. Then `flask db downgrade` recreates the four empty tables.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/bad2dd157a5f_remove_site_modules.py tests/test_migrations.py
git commit -m "feat(db): migration removing site modules and their tables"
```

---

### Task 2: Admin

**Files:**
- Modify: `app/admin/modules.py`, `app/admin/forms.py`, `app/admin/pages.py`
- Modify: `app/templates/admin/base.html`, `app/templates/admin/comments/list.html`, `app/templates/admin/pages/list.html`, `app/templates/admin/pages/form.html`
- Delete: `app/templates/admin/modules/links.html`, `movies.html`, `todos.html`
- Create: `tests/test_site_modules_removed.py`
- Modify: `tests/test_admin_modules.py`, `tests/test_admin_access.py`, `tests/test_pages.py`, `tests/test_ui_pages.py`

**Interfaces:**
- Produces: `tests/test_site_modules_removed.py` with `admin_get(client, users, path)`; later tasks append tests.

- [ ] **Step 1: Write the failing tests**

`tests/test_site_modules_removed.py`:

```python
from lxml import html as lxml_html

from app import db
from app.models import Post, PostComment
from tests.conftest import login


def admin_get(client, users, path):
    login(client, 'admin')
    return client.get(path)


def test_admin_navigation_has_no_module_data_group(client, users):
    response = admin_get(client, users, '/admin/')
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '模块数据' not in text
    assert '友情链接' not in text
    assert 'Todo 数据' not in text
    assert '评论与留言' not in text
    assert '>评论<' in text


def test_admin_module_routes_are_gone(client, users):
    login(client, 'admin')
    for path in ('/admin/todos', '/admin/movies', '/admin/links'):
        assert client.get(path).status_code == 404, path


def test_admin_comments_page_lists_only_article_comments(client, application, users):
    with application.app_context():
        db.session.add(PostComment(
            name='Reader', email='r@example.com', body='Nice article',
            post=db.session.get(Post, users['post'])))
        db.session.commit()
    response = admin_get(client, users, '/admin/comments')
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert response.status_code == 200
    assert 'Nice article' in page.text_content()
    assert '留言' not in [h.text_content() for h in page.xpath('//h2')]
    assert client.post('/admin/comments/guestbook/1/delete').status_code in (404, 405)


def test_admin_page_list_has_no_module_filter(client, users):
    login(client, 'admin')
    assert client.get('/admin/pages?filter=module').status_code == 400
    text = client.get('/admin/pages').get_data(as_text=True)
    assert '模块页' not in text
```

Check `PostComment`'s constructor fields (`grep -n "class PostComment" -A12 app/models.py`) and adjust the keyword names in the test if they differ.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_site_modules_removed.py -q`
Expected: FAIL.

- [ ] **Step 3: Remove admin module code**

`app/admin/modules.py`:
- Delete the functions `todos`, `edit_todo`, `toggle_todo`, `delete_todo`, `movies`, `edit_movie`, `delete_movie`, `links`, `edit_link`, `delete_link`, `delete_guestbook_comment` (with their `@bp.route`, `@login_required`, `@admin_required` decorators).
- Rewrite `comments()`:

```python
@bp.route('/comments', methods=['GET'])
@login_required
@admin_required
def comments():
    post_comments = db.session.scalars(sa.select(PostComment).order_by(
        PostComment.timestamp.desc())).all()
    return render_template(
        'admin/comments/list.html', post_comments=post_comments,
        delete_form=DeleteForm())
```
- Imports become `from app.admin.forms import CategoryAdminForm, DeleteForm` and `from app.models import Category, Post, PostComment` (keep `Post` only if still used in the file; check with `grep -n "Post\b" app/admin/modules.py`).

`app/admin/forms.py`: delete `TodoAdminForm`, `MovieAdminForm`, `normalize_http_url`, `LinkAdminForm`, `ActionForm` (confirm `grep -rn "ActionForm\|normalize_http_url" app tests` shows no remaining users except tests you delete in Step 5), `PageForm.module_key` and `PageForm.validate_module_key`; drop imports that became unused (`urlsplit`, `Regexp`, `Email`, `AnyOf`, `HiddenField`, `Optional` only if no other class uses them: check each with `grep -n`).

`app/admin/pages.py`: `PAGE_FILTERS = frozenset({'all', 'content', 'published', 'unpublished'})`; in `pages()` change `if active_filter in {'content', 'module'}:` to `if active_filter == 'content':`.

Templates:
- `admin/base.html`: delete the `<p class="admin-nav__group admin-nav__group--spaced">模块数据</p>` line and the three links under it (`admin.todos`, `admin.movies`, `admin.links`); change `评论与留言` to `评论`.
- `admin/comments/list.html`: set `admin_title` to `评论`; delete the whole `留言` `<section>`; keep the `文章评论` section.
- `admin/pages/list.html`: remove `('module', '模块页'), ` from the filter list; replace `{{ page.module_key or '内容页' }}` with `内容页`; replace the `{% if page.kind == 'content' %}` ... `{% endif %}` wrapper around the delete form with the bare form (all pages are content pages).
- `admin/pages/form.html`: delete the `{% if page and page.kind == 'module' %}` notice block (lines 6-8) and simplify the `(not page or page.kind == 'content')` conditions to their truthy branch (the editor is always shown).

Then `git rm app/templates/admin/modules/links.html app/templates/admin/modules/movies.html app/templates/admin/modules/todos.html`.

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_site_modules_removed.py -q`
Expected: PASS.

- [ ] **Step 5: Fix tests that exercised the removed admin features**

Run the full suite and handle each failure:
- `tests/test_admin_modules.py`: delete `test_admin_can_create_complete_edit_and_delete_todo`, `test_movie_form_validates_year_and_supports_crud`, `test_link_urls_are_normalized_and_unsafe_schemes_rejected`, `test_public_module_pages_have_no_management_actions`, `test_public_guestbook_submission_remains_available`, `test_admin_module_management_remains_available_when_public_pages_hidden`; trim `test_admin_can_delete_guestbook_and_article_comments` to article comments only and rename it `test_admin_can_delete_article_comments`. Delete the file if nothing is left.
- `tests/test_admin_access.py`: update `test_admin_sees_complete_admin_navigation` (drop the module links) and remove `/admin/todos`, `/admin/movies`, `/admin/links` from the parametrized admin paths.
- `tests/test_pages.py`: delete `test_module_page_cannot_be_deleted`, `test_admin_cannot_delete_module_page`, `test_only_one_page_per_module_key`, `test_module_singleton_is_enforced_by_form_and_database`.
- `tests/test_ui_pages.py`: delete `test_admin_link_form_preserves_action_fields_and_csrf`, `test_module_page_form_does_not_load_markdown_editor_assets`.
- Any other failure must be traced to the removed admin routes before deleting it.

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/admin app/templates/admin tests
git commit -m "refactor(admin): remove module data management and guestbook comments"
```

---

### Task 3: Public routes, models and forms

**Files:**
- Modify: `app/routes.py`, `app/forms.py`, `app/models.py`
- Delete: `app/templates/links.html`, `app/templates/edit_link.html`, `app/templates/movie/`, `app/templates/todo/`, `app/templates/comment/`
- Modify: `tests/test_site_modules_removed.py` and the tests named in Step 5

**Interfaces:**
- Consumes: `admin_get` from Task 2 (not required here).
- Produces: `public_page(slug)` serves content pages only; `Page(kind='module')` rows return 404.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site_modules_removed.py`:

```python
import pytest

from app.models import Page


@pytest.mark.parametrize('path', ['/movie', '/todo', '/links', '/comment'])
def test_old_module_urls_are_not_found(client, path):
    assert client.get(path).status_code == 404


def test_old_module_urls_reject_post(client):
    assert client.post('/comment', data={'name': 'a'}).status_code in (404, 405)


def test_leftover_module_page_row_is_not_served(client, application):
    with application.app_context():
        db.session.add(Page(title='Todo', slug='todo', kind='module',
                            module_key='todo', is_published=True,
                            show_in_nav=True))
        db.session.commit()
    assert client.get('/todo').status_code == 404


def test_custom_page_can_reuse_a_former_module_slug(client, application):
    with application.app_context():
        db.session.add(Page(title='友链', slug='links', kind='content',
                            body='<p>My friends</p>', is_published=True,
                            show_in_nav=True))
        db.session.commit()
    response = client.get('/links')
    assert response.status_code == 200
    assert 'My friends' in response.get_data(as_text=True)


def test_removed_models_and_forms_are_gone():
    import app.forms as forms
    import app.models as models
    for name in ('Link', 'Movie', 'Todo', 'Comment'):
        assert not hasattr(models, name), name
    for name in ('CommentForm', 'TodoForm', 'TodoEditForm', 'LinkForm'):
        assert not hasattr(forms, name), name
    assert hasattr(models, 'PostComment')
    assert hasattr(forms, 'PostCommentForm')
```

(`db` is imported at the top of the file from Task 2.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_site_modules_removed.py -q`
Expected: FAIL (the leftover-page test and the model checks).

- [ ] **Step 3: Remove public code**

`app/routes.py`:
- Delete the route functions `movie`, `movie_edit`, `delete` (the movie delete route), `comment`, `delete_comment`, `todo`, `update_todo`, `delete_todo` (the `/todo/delete` one), `todo_edit`, `links`, `edit_link`, `delete_link`, together with the `# Display all links` comment, and the helper `_module_page`.
- In `public_page`, replace everything after `page, is_redirect = resolved` with:

```python
    if request.method == 'POST':
        abort(405)
    if is_redirect:
        return _redirect_to_public_page(page)
    if page.kind != PAGE_CONTENT:
        abort(404)
    return render_template('page/content.html', title=page.title, page=page)
```
- Fix imports: drop `CommentForm` from the `app.forms` import; change the `app.models` import to `from app.models import Category, Notification, Message, User, Post, Page, PageRedirect, PostComment, PostLike, get_site_settings`; change the `app.admin.forms` import to `from app.admin.forms import CategoryAdminForm`; remove `from urllib.parse import urlsplit` only if `grep -n "urlsplit" app/routes.py` shows no remaining use; remove `sanitize_html` only if unused.

`app/forms.py`: delete `CommentForm`, `TodoForm`, `TodoEditForm`, `LinkForm`; drop `BooleanField` from the imports only if nothing else uses it.

`app/models.py`: delete classes `Movie`, `Comment`, `Todo`, `Link` (with their `avatar` methods and any now-unused imports such as `md5` if `grep -n md5 app/models.py` shows no other use).

Then:

```bash
git rm -r app/templates/links.html app/templates/edit_link.html app/templates/movie app/templates/todo app/templates/comment
```

Verify nothing references the removed endpoints or classes:

```bash
grep -rnE "url_for\('(movie|todo|links|comment|movie_edit|todo_edit|edit_link|delete_link|update_todo|delete_todo|delete_comment|delete)'|admin\.(todos|movies|links|edit_todo|toggle_todo|delete_todo|edit_movie|delete_movie|edit_link|delete_link|delete_guestbook_comment)" app
grep -rnE "\b(Movie|Todo|Link|Comment)\b" app --include='*.py' | grep -v "PostComment\|translations"
```
Expected: no output from either command.

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_site_modules_removed.py -q`
Expected: PASS.

- [ ] **Step 5: Fix tests that exercised the removed public features**

Run the full suite and handle each failure:
- `tests/test_legacy_admin_routes.py`: delete `test_legacy_module_editors_require_admin`, `test_legacy_movie_editor_uses_admin_year_validation`, `test_legacy_todo_toggle_preserves_post_semantics`; keep the tests for post editors.
- `tests/test_pages.py`: delete the tests about module public behaviour: `test_published_visible_module_is_public_and_in_navigation`, `test_published_hidden_module_is_public_but_absent_from_navigation`, `test_unpublished_module_rejects_canonical_and_legacy_get_and_hides_nav`, `test_missing_module_configuration_fails_closed`, `test_changed_module_slug_redirects_old_fixed_address`, `test_unpublished_module_fixed_address_is_not_found`, `test_renamed_guestbook_accepts_post_at_fixed_legacy_address`, `test_unavailable_guestbook_post_is_not_found_without_insert`, `test_published_renamed_guestbook_legacy_post_creates_once_and_redirects`, `test_renamed_module_legacy_redirect_preserves_query_string`, `test_renamed_module_legacy_redirect_preserves_raw_query_string`, `test_non_guestbook_public_pages_reject_post`, `test_renamed_todo_pagination_uses_canonical_slug`. Content-page redirect tests that do not involve modules stay.
- `tests/test_ui_pages.py`: delete `test_friend_links_use_dedicated_card_markup`, `test_todo_pagination_preserves_page_urls`, `test_friend_link_name_is_the_external_link_and_shows_domain`, `test_comment_textareas_do_not_opt_in_to_markdown_editor` (or trim its guestbook half if it also covers the article comment form: keep that part), and remove `/comment`, `/links`, `/movie`, `/todo` from `test_public_pages_render_in_the_shared_design`'s parametrization plus the helpers `MODULE_BY_PATH`/`add_published_module_for_path` if no test uses them any more. `test_authenticated_member_sees_no_public_about_or_todo_controls`: remove the todo half.
- `tests/test_ui_shell.py`: delete `test_friend_link_cards_define_responsive_aligned_grid`; keep `test_empty_page_navigation_does_not_restore_hardcoded_modules`.
- `tests/test_public_pages_consistency.py`: delete `test_movie_page_uses_public_list`, `test_todo_pagination_uses_pager_links`, `test_completed_todo_uses_done_class`; in `test_new_public_page_strings_are_chinese` drop the movie lines and the `Movie` import; remove the now-unused `publish_module` helper and `Movie`, `Todo` imports.
- Any other failing test must be traced to the removal before it is deleted.

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app tests
git commit -m "refactor: remove Links, Guestbook, Todo and Movie routes, models and forms"
```

---

### Task 4: Page logic

**Files:**
- Modify: `app/pages.py`
- Modify: `tests/test_site_modules_removed.py`, `tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site_modules_removed.py`:

```python
from app.pages import PageValidationError, save_page


def test_pages_can_only_be_content_pages(application):
    import app.pages as pages
    assert not hasattr(pages, 'MODULE_KEYS')
    assert not hasattr(pages, 'PAGE_MODULE')
    with application.app_context():
        with pytest.raises(PageValidationError):
            save_page(Page(), {'title': 'Todo', 'slug': 'todo-page',
                               'kind': 'module', 'module_key': 'todo'})
        with pytest.raises(PageValidationError):
            save_page(Page(), {'title': 'X', 'slug': 'x-page',
                               'kind': 'content', 'module_key': 'todo'})
        page = save_page(Page(), {'title': 'Notes', 'slug': 'notes',
                                  'body': 'hello'})
        assert (page.kind, page.module_key) == ('content', None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_site_modules_removed.py -q -k content_pages`
Expected: FAIL.

- [ ] **Step 3: Simplify `app/pages.py`**

- Delete `PAGE_MODULE` and `MODULE_KEYS`.
- Replace `_validate_page_identity` with:

```python
def _validate_page_identity(kind, module_key):
    if kind != PAGE_CONTENT:
        raise PageValidationError('Unknown page kind.')
    if module_key is not None:
        raise PageValidationError('Content pages cannot have a module key.')
```
- In `save_page`, call `_validate_page_identity(kind, module_key)` (no `page` argument), and replace the trailing body block with the content branch only:

```python
    page.body_format = normalize_body_format(
        values.get('body_format', page.body_format))
    page.body = prepare_content_source(
        values.get('body', page.body), page.body_format)
```
(remove the `if kind == PAGE_CONTENT: ... else: page.body = None` wrapper). Leave `page.kind = kind` and `page.module_key = module_key` assignments as they are.
- `delete_content_page`: leave as is (it still guards `kind != PAGE_CONTENT`).

- [ ] **Step 4: Run tests and fix leftovers**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. In `tests/test_pages.py` delete any remaining test that imports `PAGE_MODULE` / `MODULE_KEYS` or builds module pages through `save_page` (find them with `grep -n "PAGE_MODULE\|MODULE_KEYS\|kind='module'\|module_key" tests/test_pages.py`); keep tests that insert a raw `Page(kind='module', ...)` row only where they assert the row is ignored.

- [ ] **Step 5: Commit**

```bash
git add app/pages.py tests
git commit -m "refactor(pages): pages are content-only"
```

---

### Task 5: CSS, README, translations, verification

**Files:**
- Modify: `app/static/style.css`, `README.md`, `app/translations/zh/LC_MESSAGES/messages.po`, `messages.mo`
- Modify: `tests/test_ui_shell.py` (if CSS-asserting tests break)

- [ ] **Step 1: Remove dead CSS**

List candidates:

```bash
grep -nE "friend-link|friend-links|\.movie|\.imdb|\.totoro|todo-title|\.btn-complete|\.btn-incomplete|guestbook|comment-form|\.link-" app/static/style.css
```
For each selector, run `grep -rn "<class-name>" app/templates app/static/*.js` (class name without the dot). Delete a rule block only when no template or script references the class; leave `.comment-row` and anything used by article comments. Keep `.search-pagination`. After editing, confirm braces balance: `python3 -c "s=open('app/static/style.css').read(); assert s.count('{')==s.count('}')"`.

- [ ] **Step 2: Update the README**

Run `grep -nE "友链|友情链接|留言|待办|Todo|电影|Movie|Links|Guestbook|模块" README.md docs/admin-cms-migration.md` and edit each hit: remove the module features from the feature list and any module-specific instructions; in `docs/admin-cms-migration.md` add one line noting that the module pages and tables were removed by migration `bad2dd157a5f`. Add to the README upgrade section: "升级到包含迁移 `bad2dd157a5f` 的版本会永久删除友链、留言簿、Todo 和电影的数据，请先备份数据库再执行 `flask db upgrade`。"

- [ ] **Step 3: Update translations**

```bash
export PATH="$PWD/.venv/bin:$PATH"
pybabel extract -F babel.cfg -k _l -o messages.pot . && pybabel update -i messages.pot -d app/translations && rm -f messages.pot
```
Then list fuzzy/untranslated zh entries with the same script used earlier (babel `read_po`, print entries where `fuzzy` or empty string) and fix any that appear for strings still in use (clear the fuzzy flag after correcting); obsolete `#~` entries may stay. Finish with `pybabel compile -d app/translations`.

- [ ] **Step 4: Full verification**

```bash
.venv/bin/python -m pytest -q
node --test tests/*.test.js
```
Expected: all pass (counts will be lower than the baseline because tests of removed features were deleted; record the new numbers).

- [ ] **Step 5: Visual verification (playwright skill)**

Seed a scratch DB under the scratchpad directory with the migrations applied (`flask db upgrade`), create an admin user, one content page `友链` in nav, and a few posts; run `flask run -p 5055`. Use `bash $HOME/.claude/skills/playwright/scripts/playwright_cli.sh` (the script is not executable directly) to confirm: the public nav shows only the content page, 站内信 and user items; `/movie`, `/todo`, `/links` (when no such custom page exists), `/comment` render the 404 page; the admin nav has no "模块数据" group and the comments page lists only article comments; no console errors. Stop the server afterwards.

- [ ] **Step 6: Commit**

```bash
git add app/static/style.css README.md docs/admin-cms-migration.md app/translations tests
git commit -m "chore: remove module CSS and docs, refresh translations"
```

---

## Self-Review

- **Spec coverage:** public routes, legacy routes, `_module_page`, `public_page` simplification (Task 3); models/forms (Tasks 2, 3); templates (Tasks 2, 3); admin routes, nav group, comments page, page filter, `module_key` field, form notice (Task 2); `pages.py` (Task 4); CSS, README, translations (Task 5); migration with explicit redirect deletion, table-exists guards, row-count logging, empty-table downgrade, single head (Task 1); migration tests, behaviour tests, manual SQLite upgrade, playwright check (Tasks 1, 3, 5); `Page` schema untouched (Global Constraints).
- **Placeholders:** none; removed tests are named, and the "any other failure" fallback requires tracing to the removal.
- **Consistency:** revision id `bad2dd157a5f` and head assertion match; `admin_get` defined in Task 2 and not relied on by later tasks; `_validate_page_identity(kind, module_key)` signature is introduced and used within Task 4 only.
- **Risks to watch:** unused imports after deletions (checked via grep steps); the `PostComment` constructor kwargs in the Task 2 test; MySQL behaviour of the migration is untested here.
