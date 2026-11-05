# Admin Users, Pages and Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin real user management (search, create, edit, delete with article transfer), a stronger page list, a linked dashboard, and make "about" an ordinary page with no dedicated code.

**Architecture:** Flask blueprint `app/admin` gains routes in `users.py` and `pages.py`; account-deletion rules live next to `change_user_role` in `app/authorization.py`; forms in `app/admin/forms.py`; templates under `app/templates/admin/`. One Alembic migration drops the legacy `about` table. Spec: `docs/superpowers/specs/2026-11-05-admin-users-pages-design.md`.

**Tech Stack:** Flask, SQLAlchemy 2, Flask-WTF, Alembic, pytest (SQLite), lxml.

## Global Constraints

- All admin routes use `@login_required` and `@admin_required`; mutations are POST with CSRF (tests run with `WTF_CSRF_ENABLED=False`).
- Visible admin text is Chinese; flash messages for DB errors follow the existing style (`'…失败，请重试。'`).
- Use `user.set_password()` for passwords; never store plain text.
- Test fixtures (`tests/conftest.py`): `application`, `client`, `users` (ids: `admin`, `author`, `other`, `post` — author owns 1 post), `role_users` (`admin`, `member`), helper `login(client, username)` (password is always `password`).
- Run tests with `python -m pytest -q`; the repo's baseline before this plan is 595 pytest and 50 node tests passing.
- Commit after every task; commit messages `feat(admin): …` / `chore: …` / `test: …`.

---

### Task 1: Make "about" an ordinary page (remove dedicated routes and special cases)

**Files:**
- Create: `tests/test_admin_pages_management.py`
- Delete: `tests/test_admin_about.py`, `app/templates/about/about.html`, `app/templates/about/edit_about.html`
- Modify: `app/routes.py` (remove `about`, `edit_about`, unused imports), `app/admin/pages.py` (remove `about`, `_prefill_from_query`, use plain `PageForm()`), `app/templates/admin/base.html:17`, `app/templates/page/content.html:10-12`, `app/static/style.css:3147-3154`, `tests/test_pages.py`

**Interfaces:**
- Produces: nothing new; removes `admin.about`, `about`, `edit_about`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_pages_management.py`:

```python
from lxml import html as lxml_html

from app import db
from app.models import Page, PageRedirect
from tests.conftest import login


def add_page(application, slug='about', title='关于', **fields):
    values = dict(kind='content', body='hi', is_published=True)
    values.update(fields)
    with application.app_context():
        page = Page(title=title, slug=slug, **values)
        db.session.add(page)
        db.session.commit()
        return page.id


def test_admin_has_no_dedicated_about_entry(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    assert not page.xpath('//nav[@aria-label="管理导航"]//a[@href="/admin/about"]')
    assert client.get('/admin/about').status_code == 404


def test_new_page_form_ignores_query_prefill(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        '/admin/pages/new?title=关于&slug=about&show_in_nav=1'
    ).get_data(as_text=True))
    assert page.xpath('//input[@name="title"]/@value') in ([], [''])
    assert page.xpath('//input[@name="slug"]/@value') in ([], [''])
    assert not page.xpath('//input[@name="show_in_nav"][@checked]')


def test_about_is_an_ordinary_page_edited_like_any_other(
        client, application, users):
    page_id = add_page(application, summary='一句话介绍')
    login(client, 'admin')
    response = client.post(f'/admin/pages/{page_id}/edit', data={
        'title': '我是谁', 'slug': 'whoami', 'summary': '新的摘要',
        'body': '# hi', 'is_published': 'y', 'show_in_nav': 'y',
        'nav_order': '3',
    })
    assert response.status_code == 302
    with application.app_context():
        page = db.session.get(Page, page_id)
        assert (page.title, page.slug, page.summary) == (
            '我是谁', 'whoami', '新的摘要')
        # The old address keeps working through the generic redirect.
        assert db.session.query(PageRedirect).filter_by(
            slug='about', page_id=page_id).count() == 1
    old = client.get('/about')
    assert old.status_code == 301
    assert old.headers['Location'].endswith('/whoami')


def test_legacy_about_edit_route_is_gone(client, application, users):
    add_page(application)
    login(client, 'admin')
    assert client.get('/about/edit').status_code == 404
    assert client.post('/about/edit', data={'body': 'x'}).status_code == 404


def test_about_page_has_no_special_label_or_class(client, application):
    add_page(application, summary='摘要')
    html = client.get('/about').get_data(as_text=True)
    assert 'about-page' not in html
    assert 'public-label' not in html
    assert 'public-page' in html
    assert '摘要' in html


def test_about_page_is_unpublished_when_unpublished(client, application):
    add_page(application, is_published=False)
    assert client.get('/about').status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_admin_pages_management.py -q`
Expected: FAIL — `/admin/about` returns 302, `/about/edit` returns 302/405, prefill is applied, `about-page`/`public-label` present.

- [ ] **Step 3: Remove the dedicated code**

`app/routes.py`: delete the `about` view (`@app.route('/about', …)` through its `render_template`) and the `edit_about` view. Then remove the now-unused names: `AboutForm` from the `from app.forms import …` line, and — after checking with `grep -n` — `save_page` and `PageValidationError` from `from app.pages import …`, and `_page_for_legacy_slug` (used only by `edit_about`; delete the helper). `SQLAlchemyError`, `_commit_legacy_mutation` and `_redirect_to_public_page` are still used elsewhere; keep them. Run `python -m pyflakes app/routes.py` (or `python -c "import app.routes"`) to confirm no unused/missing names.

`app/admin/pages.py`: delete `_prefill_from_query` and the `about` view; in `new_page` replace the `PageForm(data=_prefill_from_query()) if request.method == 'GET' else PageForm()` expression with `form = PageForm()`. Remove the `PageRedirect` import if now unused.

`app/templates/admin/base.html`: delete the line
```
  {{ nav_link('admin.about', '关于', ('admin.about',)) }}
```

`app/templates/page/content.html`: change line 10 to
```
<article class="content-section public-page reading-layout">
```
and delete line 12 (`{% if page.slug == 'about' %}<div class="public-label">…</div>{% endif %}`).

`app/static/style.css` lines 3147-3154: replace the comment and the `.about-page` rules with rules for every content page:

```css
/* Editorial treatments for content pages and the search page. */
.public-site .public-page .public-label { margin-bottom: 10px; }
.public-site .public-page .page-summary { margin: 14px 0 0; color: var(--text-primary); font-size: 20px; line-height: 1.55; }
.public-site .public-page .page-body h2, .public-site .public-page .page-body h3 { margin: 1.6em 0 .6em; font-weight: 700; letter-spacing: -.01em; }
.public-site .public-page .page-body p { margin: 0 0 1.3em; }
.public-site .public-page .page-body blockquote { margin: 1.7em 0; padding: .2em 0 .2em 1.3em; border-left: 2px solid var(--text-secondary); color: var(--text-secondary); }
.public-site .public-page .page-body blockquote p { margin: 0; text-indent: 0; }
.public-site .public-page .page-body ul, .public-site .public-page .page-body ol { padding-left: 1.4em; margin: 0 0 1.5em; }
```
(keep the `.search-count` rules that follow unchanged; the old line `.public-site .public-page .public-label { margin-bottom: 10px; }` is the first line of that block — do not duplicate it).

Delete files: `git rm tests/test_admin_about.py app/templates/about/about.html app/templates/about/edit_about.html`.

`tests/test_pages.py`: remove `About` from the import on line 7 (`from app.models import Page, PageRedirect, Post`); in `test_about_fixed_address_uses_redirect_and_publication_state` delete the line `db.session.add(About(body='<p>Legacy about</p>'))`; delete the whole `test_legacy_about_post_updates_cms_page` test.

- [ ] **Step 4: Run the affected tests**

Run: `python -m pytest tests/test_admin_pages_management.py tests/test_pages.py tests/test_ui_pages.py tests/test_ui_shell.py tests/test_admin_access.py tests/test_typography.py -q`
Expected: PASS. (`tests/test_typography.py` asserts font rules; if it references `.about-page`, update its selector to `.public-page`.)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(admin): about is an ordinary page"
```

---

### Task 2: Drop the legacy `about` table

**Files:**
- Create: `migrations/versions/c8d3a5e7b102_drop_about_table.py`
- Modify: `app/models.py:226-229` (remove `About`), `app/forms.py:95-97` (remove `AboutForm`), `tests/test_migrations.py`

**Interfaces:**
- Produces: Alembic revision `c8d3a5e7b102`, `down_revision = '5a1f9c0d7e42'` (new single head).

- [ ] **Step 1: Write the failing tests**

In `tests/test_migrations.py`, add a path constant next to the others:

```python
ABOUT_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'c8d3a5e7b102_drop_about_table.py')
```

change the head assertion in `test_drafts_revision_is_the_only_head` to `['c8d3a5e7b102']`, and append:

```python
def load_about_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'about_removal', ABOUT_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_about_removal_drops_the_table_and_downgrade_recreates_it_empty():
    revision = load_about_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('about', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('body', sa.Text, nullable=False))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO about (body) VALUES ('<p>x</p>')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            assert 'about' not in sa.inspect(connection).get_table_names()

            revision.downgrade()
            assert 'about' in sa.inspect(connection).get_table_names()
            assert connection.execute(sa.text(
                'SELECT COUNT(*) FROM about')).scalar_one() == 0


def test_about_removal_upgrade_tolerates_a_missing_table():
    revision = load_about_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_migrations.py -q`
Expected: FAIL (file not found / head mismatch).

- [ ] **Step 3: Implement**

Create `migrations/versions/c8d3a5e7b102_drop_about_table.py`:

```python
"""drop the legacy about table

The about text lives in the page table (slug "about") since 9c8e2f3a4b5d.
Upgrade permanently drops the old table; downgrade recreates it empty.

Revision ID: c8d3a5e7b102
Revises: 5a1f9c0d7e42
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'c8d3a5e7b102'
down_revision = '5a1f9c0d7e42'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')


def upgrade():
    connection = op.get_bind()
    if 'about' not in sa.inspect(connection).get_table_names():
        return
    rows = connection.execute(sa.select(sa.func.count()).select_from(
        sa.table('about'))).scalar_one()
    log.info('Dropping table about (%s rows)', rows)
    op.drop_table('about')


def downgrade():
    op.create_table(
        'about',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
```

Check the original table definition in `migrations/versions/c7e939d9973e_add_about_link.py` (lines ~21-27) and make the downgrade columns match it exactly (if `body` there is `sa.Text()` nullable=False, the above is right; copy any difference).

In `app/models.py` delete the `About` class (lines 226-229, the class and its two columns). In `app/forms.py` delete `AboutForm`. Run `grep -rn "About\b" app tests --include=*.py` — the only hits left should be comments/strings, not the model.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_migrations.py tests/test_pages.py -q`
Expected: PASS.

Then verify the real migration chain on a scratch DB created from the models:

```bash
export DATABASE_URL=sqlite:///$SCRATCH/about-check.db  # a scratch directory outside the repository
python -c "from app import app, db; ctx=app.app_context(); ctx.push(); db.create_all()"
flask db stamp 5a1f9c0d7e42 && flask db upgrade && flask db downgrade -1 && flask db upgrade
```
Expected: no errors (`about` table is absent after create_all; the upgrade tolerates that). Delete the scratch DB afterwards.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: drop the legacy about table"
```

---

### Task 3: Page list — search, filters, updated time, publish and nav toggles

**Files:**
- Modify: `app/admin/pages.py`, `app/templates/admin/pages/list.html`, `app/static/style.css` (append), `tests/test_admin_pages_management.py`, `tests/test_admin_editorial_ui.py` (if it asserts the 内容页 filter)

**Interfaces:**
- Produces: routes `admin.toggle_page_publication` (`POST /admin/pages/<int:page_id>/publish`) and `admin.toggle_page_navigation` (`POST /admin/pages/<int:page_id>/nav`); query args `q`, `filter` on `admin.pages`. `PAGE_FILTERS = frozenset({'all','published','unpublished'})`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_pages_management.py`:

```python
import pytest


def test_page_list_search_matches_title_and_slug(client, application, users):
    add_page(application, slug='alpha', title='第一页')
    add_page(application, slug='beta-notes', title='笔记')
    login(client, 'admin')

    by_title = client.get('/admin/pages?q=笔').get_data(as_text=True)
    assert '笔记' in by_title and '第一页' not in by_title

    by_slug = client.get('/admin/pages?q=ALPHA').get_data(as_text=True)
    assert '第一页' in by_slug and '笔记' not in by_slug


def test_page_list_filters_and_keeps_search(client, application, users):
    add_page(application, slug='live', title='已上线', is_published=True)
    add_page(application, slug='wip', title='草稿页', is_published=False)
    login(client, 'admin')

    published = client.get('/admin/pages?filter=published').get_data(as_text=True)
    assert '已上线' in published and '草稿页' not in published
    unpublished = client.get('/admin/pages?filter=unpublished').get_data(as_text=True)
    assert '草稿页' in unpublished and '已上线' not in unpublished
    assert client.get('/admin/pages?filter=content').status_code == 400
    assert client.get('/admin/pages?filter=bogus').status_code == 400

    page = lxml_html.fromstring(
        client.get('/admin/pages?q=live').get_data(as_text=True))
    hrefs = page.xpath('//nav[@aria-label="页面筛选"]//a/@href')
    assert hrefs and all('q=live' in href for href in hrefs)
    assert not page.xpath('//nav[@aria-label="页面筛选"]//a[contains(., "内容页")]')


def test_page_list_shows_last_updated(client, application, users):
    from datetime import datetime
    add_page(application, updated_at=datetime(2024, 5, 6, 7, 8))
    login(client, 'admin')
    assert '2024-05-06' in client.get('/admin/pages').get_data(as_text=True)


def test_toggle_publication_flips_state_and_keeps_query(
        client, application, users):
    page_id = add_page(application, is_published=True)
    login(client, 'admin')

    response = client.post(
        f'/admin/pages/{page_id}/publish?q=abc&filter=published')
    assert response.status_code == 302
    assert response.headers['Location'].endswith(
        '/admin/pages?q=abc&filter=published')
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is False

    client.post(f'/admin/pages/{page_id}/publish')
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is True


def test_toggle_navigation_flips_state(client, application, users):
    page_id = add_page(application, show_in_nav=False)
    login(client, 'admin')
    assert client.post(f'/admin/pages/{page_id}/nav').status_code == 302
    with application.app_context():
        assert db.session.get(Page, page_id).show_in_nav is True
    client.post(f'/admin/pages/{page_id}/nav')
    with application.app_context():
        assert db.session.get(Page, page_id).show_in_nav is False


@pytest.mark.parametrize('suffix', ['publish', 'nav'])
def test_toggles_require_admin_and_post(client, application, users, suffix):
    page_id = add_page(application)
    url = f'/admin/pages/{page_id}/{suffix}'
    assert client.post(url).status_code == 302          # anonymous → login
    login(client, 'author')
    assert client.post(url).status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get(url).status_code == 405
    assert client.post('/admin/pages/9999/' + suffix).status_code == 404


def test_toggles_reject_missing_csrf(client, application, users):
    page_id = add_page(application, is_published=True)
    login(client, 'admin')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post(f'/admin/pages/{page_id}/publish')
        assert response.status_code == 400
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        assert db.session.get(Page, page_id).is_published is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_admin_pages_management.py -q`
Expected: FAIL — no search, `filter=content` accepted, no toggle routes.

- [ ] **Step 3: Implement**

`app/admin/pages.py`: replace `PAGE_FILTERS` and `pages()`; add the two toggles (reuse `DeleteForm` only for CSRF — it requires `confirm`, so create a dedicated `ToggleForm` in `app/admin/forms.py`):

```python
# app/admin/forms.py (add after DeleteForm)
class ToggleForm(FlaskForm):
    """CSRF-only form for one-click state toggles."""
```

```python
# app/admin/pages.py
PAGE_FILTERS = frozenset({'all', 'published', 'unpublished'})


def _like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@bp.route('/pages', methods=['GET'])
@login_required
@admin_required
def pages():
    active_filter = request.args.get('filter', 'all')
    if active_filter not in PAGE_FILTERS:
        abort(400)
    search = request.args.get('q', '').strip()
    query = sa.select(Page).order_by(Page.nav_order, Page.title, Page.id)
    if active_filter == 'published':
        query = query.where(Page.is_published.is_(True))
    elif active_filter == 'unpublished':
        query = query.where(Page.is_published.is_(False))
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            Page.title.ilike(pattern, escape='\\'),
            Page.slug.ilike(pattern, escape='\\')))
    return render_template(
        'admin/pages/list.html', pages=db.session.scalars(query).all(),
        active_filter=active_filter, search=search,
        delete_form=DeleteForm(), toggle_form=ToggleForm())


def _toggle_page_flag(page_id, attribute, message):
    if not ToggleForm().validate_on_submit():
        abort(400)
    page = db.get_or_404(Page, page_id)
    setattr(page, attribute, not getattr(page, attribute))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('页面保存失败，请重试。')
    else:
        flash(message)
    return redirect(url_for(
        'admin.pages', **{key: value for key, value in (
            ('q', request.args.get('q')),
            ('filter', request.args.get('filter'))) if value}))


@bp.route('/pages/<int:page_id>/publish', methods=['POST'])
@login_required
@admin_required
def toggle_page_publication(page_id):
    return _toggle_page_flag(page_id, 'is_published', '页面发布状态已更新。')


@bp.route('/pages/<int:page_id>/nav', methods=['POST'])
@login_required
@admin_required
def toggle_page_navigation(page_id):
    return _toggle_page_flag(page_id, 'show_in_nav', '页面导航显示已更新。')
```

Import `ToggleForm` in `pages.py` (`from app.admin.forms import DeleteForm, PageForm, ToggleForm`). Note: `onupdate` on `updated_at` fires automatically on commit.

`app/templates/admin/pages/list.html` — replace the filter nav and rows:

```html
{% block admin_content %}
<form class="admin-search" method="get" action="{{ url_for('admin.pages') }}" role="search">
  <label class="visually-hidden" for="page-search">搜索页面</label>
  <input id="page-search" class="form-control" type="search" name="q" value="{{ search }}" placeholder="按标题或 slug 搜索">
  {% if active_filter != 'all' %}<input type="hidden" name="filter" value="{{ active_filter }}">{% endif %}
  <button class="button button--quiet" type="submit">搜索</button>
</form>
<nav class="admin-filters" aria-label="页面筛选">
  {% for value, label in [('all', '全部'), ('published', '已发布'), ('unpublished', '未发布')] %}
  <a class="admin-filter{% if active_filter == value %} admin-filter--active{% endif %}"
     href="{{ url_for('admin.pages', filter=value if value != 'all' else None, q=search or None) }}">{{ label }}</a>
  {% endfor %}
</nav>
<div class="admin-list">
  {% for page in pages %}
  <article class="admin-list__row">
    <div class="admin-list__main">
      <a href="{{ url_for('admin.edit_page', page_id=page.id) }}"><strong>{{ page.title }}</strong></a>
      <span>/{{ page.slug }} · 更新于 {{ page.updated_at.strftime('%Y-%m-%d') }}</span>
    </div>
    <div class="admin-list__meta">
      <span>{{ '已发布' if page.is_published else '未发布' }}</span>
      <span>{{ '导航可见' if page.show_in_nav else '导航隐藏' }} · {{ page.nav_order }}</span>
    </div>
    <div class="admin-list__actions">
      <form method="post" action="{{ url_for('admin.toggle_page_publication', page_id=page.id, q=search or None, filter=active_filter if active_filter != 'all' else None) }}">
        {{ toggle_form.hidden_tag() }}
        <button class="button button--quiet" type="submit">{{ '取消发布' if page.is_published else '发布' }}</button>
      </form>
      <form method="post" action="{{ url_for('admin.toggle_page_navigation', page_id=page.id, q=search or None, filter=active_filter if active_filter != 'all' else None) }}">
        {{ toggle_form.hidden_tag() }}
        <button class="button button--quiet" type="submit">{{ '隐藏导航' if page.show_in_nav else '显示导航' }}</button>
      </form>
      <a href="{{ url_for('admin.preview_page', page_id=page.id) }}">预览</a>
      <a href="{{ url_for('admin.edit_page', page_id=page.id) }}">编辑</a>
      <form method="post" action="{{ url_for('admin.delete_page', page_id=page.id) }}">
        {{ delete_form.hidden_tag() }}
        <input type="hidden" name="confirm" value="y">
        <button class="button button--quiet button--danger" type="submit" onclick="return confirm('确定删除此页面？');">删除</button>
      </form>
    </div>
  </article>
  {% else %}
  <div class="empty-state"><p>没有符合条件的页面。</p></div>
  {% endfor %}
</div>
{% endblock %}
```
(Keep the existing `{% extends %}`, `admin_title` and `admin_actions` blocks above this unchanged.) `url_for` drops arguments whose value is `None`, which is what the `or None` relies on.

Append to `app/static/style.css`:

```css

/* Admin: list search. */
.admin-search { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; max-width: 520px; }
.admin-search .form-control { flex: 1 1 auto; min-width: 0; }
@media (width <= 768px) {
    .admin-search .button { min-height: 44px; }
}
```

If `tests/test_admin_editorial_ui.py` or another test references the removed "内容页" filter, update it.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_admin_pages_management.py tests/test_admin_editorial_ui.py tests/test_pages.py tests/test_admin_access.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(admin): page search, filters and inline toggles"
```

---

### Task 4: Account deletion rules in `app/authorization.py`

**Files:**
- Modify: `app/authorization.py`, `tests/test_roles.py`

**Interfaces:**
- Consumes: `RoleChangeError`, `ROLE_ADMIN`, `User`, `Post`, `PostLike`.
- Produces: `delete_user(actor: User, target: User, receiver: User | None) -> None` — raises `RoleChangeError` on guard failure; does **not** commit.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_roles.py` (add `delete_user` to the `from app.authorization import …` list and `PostLike` to the models import):

```python
def make_post(author, title='T'):
    category = db.session.scalar(sa.select(Category)) or Category(name='C')
    post = Post(title=title, body='b', author=author, category=category)
    db.session.add_all([category, post])
    db.session.commit()
    return post


def test_delete_user_transfers_posts_and_removes_likes(
        application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        mine = make_post(member, 'mine')
        theirs = make_post(admin, 'theirs')
        db.session.add_all([PostLike(post_id=theirs.id, user_id=member.id),
                            PostLike(post_id=mine.id, user_id=admin.id)])
        db.session.commit()
        mine_id, member_id = mine.id, member.id

        delete_user(admin, member, admin)
        db.session.commit()

        assert db.session.get(User, member_id) is None
        assert db.session.get(Post, mine_id).user_id == admin.id
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostLike).where(PostLike.user_id == member_id)) == 0
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostLike)) == 1  # the like given to the transferred post stays


def test_delete_user_without_posts_needs_no_receiver(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        member_id = member.id
        delete_user(admin, member, None)
        db.session.commit()
        assert db.session.get(User, member_id) is None


def test_delete_user_with_posts_requires_a_receiver(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        make_post(member)
        with pytest.raises(RoleChangeError, match='receiver'):
            delete_user(admin, member, None)
        with pytest.raises(RoleChangeError, match='receiver'):
            delete_user(admin, member, member)


def test_delete_user_guards(application, role_users):
    with application.app_context():
        admin = db.session.get(User, role_users['admin'])
        member = db.session.get(User, role_users['member'])
        with pytest.raises(RoleChangeError, match='Administrator access'):
            delete_user(member, admin, member)
        with pytest.raises(RoleChangeError, match='yourself'):
            delete_user(admin, admin, member)

        # Another administrator can be deleted by an administrator.
        member.role = 'admin'
        db.session.commit()
        delete_user(admin, member, None)
        db.session.commit()
```

The spec's "cannot delete the last administrator" rule holds structurally: only an administrator can delete, and an administrator cannot delete themselves, so the sole administrator can never be deleted.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_roles.py -q`
Expected: FAIL — `ImportError: cannot import name 'delete_user'`.

- [ ] **Step 3: Implement**

In `app/authorization.py` add imports `from app.models import Post, PostLike, User` and:

```python
def delete_user(actor: User, target: User, receiver: User | None) -> None:
    """Delete ``target``, handing their posts to ``receiver``.

    Raises RoleChangeError on guard failures. The caller commits.
    """
    if not actor.is_admin:
        raise RoleChangeError('Administrator access is required.')
    if actor.id == target.id:
        raise RoleChangeError('You cannot delete yourself.')
    post_count = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.user_id == target.id))
    if post_count:
        if receiver is None or receiver.id == target.id:
            raise RoleChangeError('Choose another user to receive the posts.')
        db.session.execute(sa.update(Post).where(
            Post.user_id == target.id).values(user_id=receiver.id))
    db.session.execute(sa.delete(PostLike).where(PostLike.user_id == target.id))
    db.session.delete(target)
```

Call `db.session.flush()` right after the two bulk statements (before `db.session.delete(target)`) so the post transfer and like removal reach the database first; MySQL enforces the foreign keys, SQLite in tests does not.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_roles.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(admin): delete_user with article transfer"
```

---

### Task 5: User list with search/filter, create and edit (replaces the inline role route)

**Files:**
- Modify: `app/admin/forms.py` (add `UserCreateForm`, `UserEditForm`; remove `RoleForm` once unused), `app/admin/users.py`, `app/templates/admin/users/list.html`, `app/static/style.css` (append), `tests/test_roles.py` (port route tests), `tests/test_admin_editorial_ui.py` (if affected), `tests/test_admin_access.py`
- Create: `app/templates/admin/users/form.html`, `tests/test_admin_users.py`

**Interfaces:**
- Consumes: `change_user_role(actor, target, new_role)` raising `RoleChangeError`.
- Produces: routes `admin.users` (`q`, `role` args), `admin.new_user` (`/admin/users/new`), `admin.edit_user` (`/admin/users/<int:user_id>/edit`). Removes `admin.change_role` (`/admin/users/<id>/role`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_users.py`:

```python
import sqlalchemy as sa
from lxml import html as lxml_html

from app import db
from app.models import User, get_site_settings
from tests.conftest import login


def user_id(application, username):
    with application.app_context():
        return db.session.scalar(
            sa.select(User.id).where(User.username == username))


def test_list_search_and_role_filter(client, users):
    login(client, 'admin')
    by_name = client.get('/admin/users?q=AUTH').get_data(as_text=True)
    assert 'author@example.com' in by_name and 'other@example.com' not in by_name

    by_email = client.get('/admin/users?q=other@').get_data(as_text=True)
    assert 'other@example.com' in by_email and 'author@example.com' not in by_email

    admins = client.get('/admin/users?role=admin').get_data(as_text=True)
    assert 'admin@example.com' in admins and 'author@example.com' not in admins
    plain = client.get('/admin/users?role=user').get_data(as_text=True)
    assert 'author@example.com' in plain and 'admin@example.com' not in plain
    assert client.get('/admin/users?role=owner').status_code == 400


def test_list_rows_link_to_edit(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/users').get_data(as_text=True))
    author = user_id(application, 'author')
    assert page.xpath(f'//a[@href="/admin/users/{author}/edit"]')
    assert page.xpath('//a[@href="/admin/users/new"]')
    assert not page.xpath('//select[@name="role"]')  # role is edited on the form page


def test_create_user(client, application, users):
    login(client, 'admin')
    response = client.post('/admin/users/new', data={
        'username': 'newbie', 'email': 'newbie@example.com',
        'password': 'secret-pass', 'role': 'user'})
    assert response.status_code == 302
    with application.app_context():
        created = db.session.scalar(sa.select(User).where(
            User.username == 'newbie'))
        assert created.role == 'user'
        assert created.check_password('secret-pass')
        assert created.password_hash != 'secret-pass'


def test_create_user_works_while_registration_is_closed(
        client, application, users):
    with application.app_context():
        get_site_settings().registration_open = False
        db.session.commit()
    login(client, 'admin')
    assert client.post('/admin/users/new', data={
        'username': 'closed', 'email': 'closed@example.com',
        'password': 'x', 'role': 'admin'}).status_code == 302
    with application.app_context():
        assert db.session.scalar(sa.select(User.role).where(
            User.username == 'closed')) == 'admin'


def test_create_user_rejects_duplicates_and_bad_input(client, application, users):
    login(client, 'admin')
    base = {'username': 'fresh', 'email': 'fresh@example.com',
            'password': 'pw', 'role': 'user'}
    for override in ({'username': 'author'}, {'email': 'author@example.com'},
                     {'email': 'not-an-email'}, {'password': ''},
                     {'role': 'owner'}, {'username': ''}):
        response = client.post('/admin/users/new', data={**base, **override})
        assert response.status_code == 200, override
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            User)) == 3


def test_edit_user_fields_and_blank_password_keeps_hash(
        client, application, users):
    author = users['author']
    with application.app_context():
        old_hash = db.session.get(User, author).password_hash
    login(client, 'admin')
    response = client.post(f'/admin/users/{author}/edit', data={
        'username': 'writer', 'email': 'writer@example.com',
        'role': 'user', 'password': ''})
    assert response.status_code == 302
    with application.app_context():
        edited = db.session.get(User, author)
        assert (edited.username, edited.email) == ('writer', 'writer@example.com')
        assert edited.password_hash == old_hash


def test_edit_user_sets_new_password_and_role(client, application, users):
    author = users['author']
    login(client, 'admin')
    client.post(f'/admin/users/{author}/edit', data={
        'username': 'author', 'email': 'author@example.com',
        'role': 'admin', 'password': 'brand-new'})
    with application.app_context():
        edited = db.session.get(User, author)
        assert edited.role == 'admin'
        assert edited.check_password('brand-new')


def test_edit_user_uniqueness_ignores_self_but_not_others(
        client, application, users):
    author = users['author']
    login(client, 'admin')
    same = client.post(f'/admin/users/{author}/edit', data={
        'username': 'author', 'email': 'author@example.com', 'role': 'user'})
    assert same.status_code == 302
    clash = client.post(f'/admin/users/{author}/edit', data={
        'username': 'other', 'email': 'author@example.com', 'role': 'user'})
    assert clash.status_code == 200
    with application.app_context():
        assert db.session.get(User, author).username == 'author'


def test_editing_yourself_never_changes_your_role(
        client, application, role_users):
    login(client, 'role-admin')
    admin_id = role_users['admin']
    response = client.post(f'/admin/users/{admin_id}/edit', data={
        'username': 'role-admin-renamed', 'email': 'role-admin@example.com',
        'role': 'user'})
    assert response.status_code == 302
    with application.app_context():
        edited = db.session.get(User, admin_id)
        assert edited.role == 'admin'
        assert edited.username == 'role-admin-renamed'


def test_edit_form_disables_own_role_select(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        f'/admin/users/{users["admin"]}/edit').get_data(as_text=True))
    assert page.xpath('//select[@name="role"][@disabled]')
    other = lxml_html.fromstring(client.get(
        f'/admin/users/{users["author"]}/edit').get_data(as_text=True))
    assert not other.xpath('//select[@name="role"][@disabled]')


def test_user_routes_require_admin(client, users):
    for method, path in (('get', '/admin/users/new'), ('post', '/admin/users/new'),
                         ('get', f'/admin/users/{users["author"]}/edit'),
                         ('post', f'/admin/users/{users["author"]}/edit')):
        assert getattr(client, method)(path).status_code == 302
    login(client, 'author')
    for method, path in (('get', '/admin/users/new'), ('post', '/admin/users/new'),
                         ('get', f'/admin/users/{users["author"]}/edit'),
                         ('post', f'/admin/users/{users["author"]}/edit')):
        assert getattr(client, method)(path).status_code == 403
    login_admin = login(client, 'admin')  # noqa: F841
    assert client.get('/admin/users/9999/edit').status_code == 404
```

In `tests/test_roles.py` rewrite the route tests (lines ~158-230) to post to the edit route through a small helper added above them:

```python
def post_role(client, application, user_id, role):
    with application.app_context():
        target = db.session.get(User, user_id)
        data = {'username': target.username, 'email': target.email,
                'role': role}
    return client.post(f'/admin/users/{user_id}/edit', data=data,
                       follow_redirects=True)
```

Port: promote/demote test (`post_role(..., 'admin')` then `'user'`, check DB; statuses 200 after redirects), non-admin → 403 (`client.post(f'/admin/users/{admin}/edit', data={'username': 'a', 'email': 'a@a.co', 'role': 'user'})`), invalid role `owner` → page re-rendered (200) and role unchanged, missing user → `GET /admin/users/9999/edit` is 404. Delete the two route tests for self-demotion and last-administrator demotion: an administrator editing themselves can no longer submit a role (the select is disabled and the route keeps the current role), so those rules are exercised only by the existing `change_user_role` unit tests, which stay.

Also change `tests/test_roles.py::test_user_management_requires_admin_and_lists_post_counts` only if its assertions break (it should not).

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_admin_users.py tests/test_roles.py -q`
Expected: FAIL (no search, no `/new`, no `/edit`).

- [ ] **Step 3: Implement forms**

In `app/admin/forms.py` replace `RoleForm` with:

```python
from wtforms.validators import Email  # add to the existing validators import

ROLE_CHOICES = [('user', '普通用户'), ('admin', '管理员')]


class _UserFieldsMixin:
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user.id if user is not None else None

    def _unique(self, column, value, message):
        query = sa.select(User).where(column == value)
        if self.user_id is not None:
            query = query.where(User.id != self.user_id)
        if db.session.scalar(query) is not None:
            raise ValidationError(message)

    def validate_username(self, field):
        field.data = field.data.strip()
        self._unique(User.username, field.data, '用户名已被使用。')

    def validate_email(self, field):
        field.data = field.data.strip()
        self._unique(User.email, field.data, '邮箱已被使用。')


class UserCreateForm(_UserFieldsMixin, FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(max=64)])
    email = StringField('邮箱', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('初始密码', validators=[DataRequired()])
    role = SelectField('角色', choices=ROLE_CHOICES,
                       validators=[DataRequired(), AnyOf(('user', 'admin'))])
    submit = SubmitField('创建用户')


class UserEditForm(_UserFieldsMixin, FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(max=64)])
    email = StringField('邮箱', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('新密码', validators=[Optional()])
    role = SelectField('角色', choices=ROLE_CHOICES,
                       validators=[AnyOf(('user', 'admin'))])
    submit = SubmitField('保存')
```

(Add `Optional` to the validators import; import `User` from `app.models` alongside `Category, Page, PageRedirect`. `Email()` needs `email_validator`; the registration form already uses it, so it is installed. The `_UserFieldsMixin.__init__` must come before `FlaskForm` in the MRO, as written. For the edit form, the role `<select>` is rendered `disabled` for the acting admin editing themselves, so a disabled browser field posts nothing: in the route, when `target.id == current_user.id`, set `form.role.data = target.role` **before** validating by building the form with `data={'role': target.role}` and ignoring submitted role — see the route below.)

- [ ] **Step 4: Implement routes**

Replace `app/admin/users.py`:

```python
import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.admin import bp
from app.admin.forms import UserCreateForm, UserEditForm
from app.authorization import RoleChangeError, change_user_role
from app.models import Post, User
from app.security import admin_required


USER_ROLE_FILTERS = frozenset({'all', 'user', 'admin'})


def _like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@bp.route('/users', methods=['GET'])
@login_required
@admin_required
def users():
    role = request.args.get('role', 'all')
    if role not in USER_ROLE_FILTERS:
        abort(400)
    search = request.args.get('q', '').strip()
    post_counts = sa.select(
        Post.user_id.label('user_id'),
        sa.func.count(Post.id).label('post_count'),
    ).group_by(Post.user_id).subquery()
    query = sa.select(
        User, sa.func.coalesce(post_counts.c.post_count, 0)
    ).outerjoin(post_counts, post_counts.c.user_id == User.id)
    if role != 'all':
        query = query.where(User.role == role)
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            User.username.ilike(pattern, escape='\\'),
            User.email.ilike(pattern, escape='\\')))
    rows = db.session.execute(query.order_by(User.username)).all()
    return render_template(
        'admin/users/list.html', user_rows=rows, active_role=role,
        search=search)


@bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    form = UserCreateForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data,
                    role=form.role.data)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户保存失败，请重试。')
        else:
            flash('用户已创建。')
            return redirect(url_for('admin.users'))
    return render_template('admin/users/form.html', form=form, target=None)


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    target = db.session.scalar(sa.select(User).where(
        User.id == user_id).with_for_update())
    if target is None:
        abort(404)
    editing_self = target.id == current_user.id
    if request.method == 'POST':
        form = UserEditForm(user=target)
        if editing_self:
            form.role.data = target.role  # the select is disabled in the page
    else:
        form = UserEditForm(user=target, obj=target)
    if form.validate_on_submit():
        try:
            target.username = form.username.data
            target.email = form.email.data
            change_user_role(current_user, target, form.role.data)
            if form.password.data:
                target.set_password(form.password.data)
            db.session.commit()
        except RoleChangeError as exc:
            db.session.rollback()
            flash(str(exc))
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户保存失败，请重试。')
        else:
            flash('用户已更新。')
            return redirect(url_for('admin.users'))
    return render_template(
        'admin/users/form.html', form=form, target=target,
        editing_self=editing_self)
```

Notes: `change_user_role` already refuses demoting yourself/the last admin and is a no-op when the role is unchanged; after a `RoleChangeError` the rolled-back `target` is reloaded on re-render. The flash text for those errors is the existing English string (`'The final administrator cannot be demoted.'` etc.), which the ported role tests match with `final administrator` / `own administrator role`; test `test_edit_user_role_rules_apply` matches the lowercase word `administrator`.

- [ ] **Step 5: Templates and CSS**

`app/templates/admin/users/list.html`:

```html
{% extends "admin/base.html" %}
{% block admin_title %}用户与角色{% endblock %}

{% block admin_actions %}
<a class="button button--cta" href="{{ url_for('admin.new_user') }}">新建用户</a>
{% endblock %}

{% block admin_content %}
<form class="admin-search" method="get" action="{{ url_for('admin.users') }}" role="search">
  <label class="visually-hidden" for="user-search">搜索用户</label>
  <input id="user-search" class="form-control" type="search" name="q" value="{{ search }}" placeholder="按用户名或邮箱搜索">
  {% if active_role != 'all' %}<input type="hidden" name="role" value="{{ active_role }}">{% endif %}
  <button class="button button--quiet" type="submit">搜索</button>
</form>
<nav class="admin-filters" aria-label="角色筛选">
  {% for value, label in [('all', '全部'), ('admin', '管理员'), ('user', '普通用户')] %}
  <a class="admin-filter{% if active_role == value %} admin-filter--active{% endif %}"
     href="{{ url_for('admin.users', role=value if value != 'all' else None, q=search or None) }}">{{ label }}</a>
  {% endfor %}
</nav>
<div class="admin-list admin-user-list">
  {% for user, post_count in user_rows %}
  <article class="admin-list__row">
    <div class="admin-list__main">
      <a href="{{ url_for('admin.edit_user', user_id=user.id) }}"><strong>{{ user.username }}</strong></a>
      <span class="admin-user-email">{{ user.email }}</span>
    </div>
    <div class="admin-list__meta">
      <span>{{ '管理员' if user.role == 'admin' else '普通用户' }}</span>
      <span>文章 <span>{{ post_count }}</span></span>
      <span>{{ user.last_seen.strftime('%Y-%m-%d %H:%M') if user.last_seen else '从未登录' }}</span>
    </div>
    <div class="admin-list__actions">
      <a href="{{ url_for('admin.edit_user', user_id=user.id) }}">编辑</a>
    </div>
  </article>
  {% else %}
  <div class="empty-state"><p>没有符合条件的用户。</p></div>
  {% endfor %}
</div>
{% endblock %}
```

`app/templates/admin/users/form.html`:

```html
{% extends "admin/base.html" %}
{% block admin_title %}{{ '新建用户' if target is none else '编辑用户' }}{% endblock %}

{% block admin_content %}
<form class="admin-form" method="post" novalidate autocomplete="off">
  {{ form.hidden_tag() }}
  {% for field in (form.username, form.email) %}
  <div class="form-field">
    {{ field.label(class="form-label") }}
    {{ field(class="form-control" + (' is-invalid' if field.errors else '')) }}
    {% for error in field.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
  </div>
  {% endfor %}
  <div class="form-field">
    {{ form.password.label(class="form-label") }}
    {{ form.password(class="form-control" + (' is-invalid' if form.password.errors else ''), autocomplete="new-password") }}
    {% if target is not none %}<div class="form-text">留空则不修改密码。</div>{% endif %}
    {% for error in form.password.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
  </div>
  <div class="form-field">
    {{ form.role.label(class="form-label") }}
    {% if editing_self %}
    {{ form.role(class="form-select", disabled=True) }}
    <div class="form-text">不能修改自己的角色。</div>
    {% else %}
    {{ form.role(class="form-select") }}
    {% endif %}
    {% for error in form.role.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
  </div>
  {{ form.submit(class="button button--cta") }}
</form>
{% endblock %}
```

Pass `editing_self=False` from `new_user` (`render_template(…, target=None, editing_self=False)`) so the template variable always exists; update that `render_template` call in Step 4.

Append to `app/static/style.css`:

```css

/* Admin: user forms reuse .admin-form; keep the helper text quiet. */
.admin-form .form-text { color: var(--text-secondary); font-size: 13px; }
```

- [ ] **Step 6: Remove the old route and run tests**

Delete `RoleForm` from `forms.py` only if `grep -rn RoleForm app tests` shows no remaining use. Update `tests/test_admin_access.py` if it lists `/admin/users` routes (it should still pass).

Run: `python -m pytest tests/test_admin_users.py tests/test_roles.py tests/test_admin_access.py tests/test_admin_editorial_ui.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(admin): user search, create and edit"
```

---

### Task 6: Delete user with article transfer

**Files:**
- Modify: `app/admin/users.py`, `app/admin/forms.py`, `tests/test_admin_users.py`
- Create: `app/templates/admin/users/delete.html`

**Interfaces:**
- Consumes: `delete_user(actor, target, receiver)` from Task 4, `RoleChangeError`.
- Produces: route `admin.delete_user` — `GET/POST /admin/users/<int:user_id>/delete`; form `UserDeleteForm` with `receiver` (`SelectField`, coerce int).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_users.py`:

```python
from app.models import Post, PostLike


def test_delete_confirmation_shows_post_count_and_receivers(
        client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get(
        f'/admin/users/{users["author"]}/delete').get_data(as_text=True))
    assert '1' in page.text_content()
    options = page.xpath('//select[@name="receiver"]/option')
    values = {o.get('value') for o in options}
    assert str(users['author']) not in values
    assert {str(users['admin']), str(users['other'])} <= values
    selected = page.xpath('//select[@name="receiver"]/option[@selected]/@value')
    assert selected == [str(users['admin'])]


def test_list_links_to_delete_except_for_yourself(client, application, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/users').get_data(as_text=True))
    assert page.xpath(f'//a[@href="/admin/users/{users["author"]}/delete"]')
    assert not page.xpath(f'//a[@href="/admin/users/{users["admin"]}/delete"]')


def test_delete_user_transfers_articles_and_removes_account(
        client, application, users):
    login(client, 'admin')
    response = client.post(f'/admin/users/{users["author"]}/delete', data={
        'receiver': str(users['other'])})
    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(User, users['author']) is None
        assert db.session.get(Post, users['post']).user_id == users['other']


def test_delete_user_without_posts_needs_no_receiver(client, application, users):
    login(client, 'admin')
    response = client.post(f'/admin/users/{users["other"]}/delete', data={})
    assert response.status_code == 302
    with application.app_context():
        assert db.session.get(User, users['other']) is None


def test_delete_user_removes_their_likes_but_keeps_others(
        client, application, users):
    with application.app_context():
        db.session.add_all([
            PostLike(post_id=users['post'], user_id=users['author']),
            PostLike(post_id=users['post'], user_id=users['other'])])
        db.session.commit()
    login(client, 'admin')
    client.post(f'/admin/users/{users["author"]}/delete', data={
        'receiver': str(users['admin'])})
    with application.app_context():
        remaining = db.session.scalars(sa.select(PostLike.user_id)).all()
        assert remaining == [users['other']]


def test_delete_user_rejects_bad_receivers(client, application, users):
    login(client, 'admin')
    url = f'/admin/users/{users["author"]}/delete'
    for data in ({}, {'receiver': str(users['author'])},
                 {'receiver': '9999'}, {'receiver': 'abc'}):
        response = client.post(url, data=data)
        assert response.status_code == 200, data
    with application.app_context():
        assert db.session.get(User, users['author']) is not None
        assert db.session.get(Post, users['post']).user_id == users['author']


def test_cannot_delete_yourself(client, application, users):
    login(client, 'admin')
    assert client.get(f'/admin/users/{users["admin"]}/delete').status_code == 400
    assert client.post(f'/admin/users/{users["admin"]}/delete',
                       data={'receiver': str(users['other'])}).status_code == 400
    with application.app_context():
        assert db.session.get(User, users['admin']) is not None


def test_delete_user_requires_admin_post_and_existing_user(client, users):
    url = f'/admin/users/{users["other"]}/delete'
    assert client.post(url).status_code == 302
    login(client, 'author')
    assert client.get(url).status_code == 403
    assert client.post(url).status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get('/admin/users/9999/delete').status_code == 404
    assert client.post('/admin/users/9999/delete').status_code == 404


def test_delete_user_rejects_missing_csrf(client, application, users):
    login(client, 'admin')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post(f'/admin/users/{users["other"]}/delete')
        assert response.status_code == 200  # form re-rendered with a CSRF error
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        assert db.session.get(User, users['other']) is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_admin_users.py -q`
Expected: FAIL (404/BuildError for `delete`).

- [ ] **Step 3: Implement**

`app/admin/forms.py`:

```python
class UserDeleteForm(FlaskForm):
    """CSRF plus an optional receiver; the route decides if it is required."""
    receiver = SelectField('文章转交给', coerce=int, validate_choice=False)
    submit = SubmitField('删除用户')
```

`app/admin/users.py` — extend the imports (the service is aliased so the view can be named `delete_user`, the endpoint used by tests and templates) and add the view:

```python
from app.admin.forms import UserCreateForm, UserDeleteForm, UserEditForm
from app.authorization import RoleChangeError, change_user_role
from app.authorization import delete_user as remove_user
```

```python
@bp.route('/users/<int:user_id>/delete', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_user(user_id):
    target = db.get_or_404(User, user_id)
    if target.id == current_user.id:
        abort(400)
    post_count = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.user_id == target.id))
    candidates = db.session.scalars(sa.select(User).where(
        User.id != target.id).order_by(User.username)).all()
    form = UserDeleteForm()
    form.receiver.choices = [(user.id, user.username) for user in candidates]
    if request.method == 'GET':
        form.receiver.data = current_user.id
    if form.validate_on_submit():
        receiver = db.session.get(User, form.receiver.data) \
            if form.receiver.data else None
        if receiver is not None and receiver.id == target.id:
            receiver = None
        try:
            remove_user(current_user, target, receiver)
            db.session.commit()
        except RoleChangeError:
            db.session.rollback()
            form.receiver.errors.append('请选择接收文章的其他用户。')
        except SQLAlchemyError:
            db.session.rollback()
            flash('用户删除失败，请重试。')
        else:
            flash('用户已删除。')
            return redirect(url_for('admin.users'))
    return render_template(
        'admin/users/delete.html', form=form, target=target,
        post_count=post_count)
```

How each test case maps: `{}` → `coerce=int` on a missing value leaves `data=None`; with `post_count > 0` `remove_user` raises (receiver is None) → error, status 200. `receiver == target` → set to None → same error. `9999` → `db.session.get` returns None → same error. `abc` → coerce fails; WTForms records a `ValueError` on `process_formdata` and `validate_on_submit()` is False → page re-rendered, 200. No-posts user with `{}` → `remove_user(…, None)` succeeds. Missing CSRF → `validate_on_submit()` False → 200. POST to an unknown user → `get_or_404` → 404 before anything else. A non-admin hits 403 from `@admin_required` first.

`app/templates/admin/users/list.html` — add the delete link after the edit link in `.admin-list__actions`:

```html
      {% if user.id != current_user.id %}<a href="{{ url_for('admin.delete_user', user_id=user.id) }}">删除</a>{% endif %}
```

`app/templates/admin/users/delete.html`:

```html
{% extends "admin/base.html" %}
{% block admin_title %}删除用户{% endblock %}

{% block admin_content %}
<form class="admin-form" method="post" novalidate>
  {{ form.hidden_tag() }}
  <p>将删除用户 <strong>{{ target.username }}</strong>（{{ target.email }}）。此操作不可恢复。</p>
  {% if post_count %}
  <p>该用户有 <strong>{{ post_count }}</strong> 篇文章，请选择由谁接收：</p>
  <div class="form-field">
    {{ form.receiver.label(class="form-label") }}
    {{ form.receiver(class="form-select") }}
    {% for error in form.receiver.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
  </div>
  {% else %}
  <p>该用户没有文章，可以直接删除。</p>
  {% endif %}
  <div class="admin-form__actions">
    <button class="button button--cta button--danger" type="submit" onclick="return confirm('确定删除此用户？');">确认删除</button>
    <a class="button button--quiet" href="{{ url_for('admin.users') }}">取消</a>
  </div>
</form>
{% endblock %}
```

Append CSS:

```css

/* Admin: confirmation page actions. */
.admin-form__actions { display: flex; align-items: center; gap: 16px; }
.admin-site .button--cta.button--danger { background: var(--danger); border-color: var(--danger); color: #fff; }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_admin_users.py tests/test_roles.py tests/test_admin_access.py -q`
Expected: PASS (all of Task 5 and Task 6).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(admin): delete users and transfer their articles"
```

---

### Task 7: Dashboard cards

**Files:**
- Modify: `app/admin/routes.py:10-17`, `app/templates/admin/dashboard.html`, `app/static/style.css` (append), `tests/test_admin_pages_management.py` or a new `tests/test_admin_dashboard.py`
- Create: `tests/test_admin_dashboard.py`

**Interfaces:**
- Produces: template context `metrics` — a list of dicts `{'label': str, 'value': str, 'endpoint': str}` ordered for display.

- [ ] **Step 1: Write the failing tests**

`tests/test_admin_dashboard.py`:

```python
from lxml import html as lxml_html

from app import db
from app.models import Page, PostComment
from tests.conftest import login


def cards(client):
    page = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    return {a.xpath('string(.//*[contains(@class,"admin-metric__label")])').strip():
            (a.get('href'), a.xpath('string(.//*[contains(@class,"admin-metric__value")])').strip())
            for a in page.xpath('//a[contains(@class,"admin-metric")]')}


def test_member_sees_only_own_posts_card(client, users):
    login(client, 'author')
    assert cards(client) == {'我的文章': ('/admin/posts', '1')}


def test_admin_sees_linked_metric_cards(client, application, users):
    with application.app_context():
        db.session.add_all([
            Page(title='A', slug='a', kind='content', is_published=True),
            Page(title='B', slug='b', kind='content', is_published=False),
            PostComment(post_id=users['post'], name='n', email='e@e.co', body='b')])
        db.session.commit()
    login(client, 'admin')
    assert cards(client) == {
        '我的文章': ('/admin/posts', '0'),
        '全部文章': ('/admin/posts', '1'),
        '页面': ('/admin/pages', '1 / 2'),
        '评论': ('/admin/comments', '1'),
        '用户': ('/admin/users', '3'),
    }
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_admin_dashboard.py -q`
Expected: FAIL — cards are `<article>` not `<a>`.

- [ ] **Step 3: Implement**

`app/admin/routes.py`:

```python
from app.models import Page, Post, PostComment, User  # extend the existing import


def _count(model, *conditions):
    return db.session.scalar(
        sa.select(sa.func.count()).select_from(model).where(*conditions))


@bp.route('/', methods=['GET'], strict_slashes=False)
@login_required
def dashboard():
    metrics = [{'label': '我的文章', 'endpoint': 'admin.posts',
                'value': str(_count(Post, Post.user_id == current_user.id))}]
    if current_user.is_admin:
        published = _count(Page, Page.is_published.is_(True))
        metrics += [
            {'label': '全部文章', 'endpoint': 'admin.posts',
             'value': str(_count(Post))},
            {'label': '页面', 'endpoint': 'admin.pages',
             'value': f'{published} / {_count(Page)}'},
            {'label': '评论', 'endpoint': 'admin.comments',
             'value': str(_count(PostComment))},
            {'label': '用户', 'endpoint': 'admin.users',
             'value': str(_count(User))},
        ]
    return render_template('admin/dashboard.html', metrics=metrics)
```

Keep the existing imports at the top of the file (`current_user`, `login_required`, `sa`, `db`, `bp`, `render_template`); add whatever is missing. `_count(Post)` with no conditions works because `.where()` with no arguments is a no-op.

`app/templates/admin/dashboard.html`:

```html
{% extends "admin/base.html" %}

{% block admin_actions %}
<a class="button button--cta" href="{{ url_for('admin.new_post') }}">新建文章</a>
{% endblock %}

{% block admin_content %}
<section class="admin-dashboard" aria-label="概览数据">
  {% for metric in metrics %}
  <a class="admin-metric" href="{{ url_for(metric.endpoint) }}">
    <span class="admin-metric__label">{{ metric.label }}</span>
    <span class="admin-metric__value">{{ metric.value }}</span>
  </a>
  {% endfor %}
</section>
{% endblock %}
```

Append CSS:

```css

/* Admin: dashboard cards are links. */
.admin-site a.admin-metric { display: block; color: var(--text-primary); text-decoration: none; }
.admin-site a.admin-metric .admin-metric__label, .admin-site a.admin-metric .admin-metric__value { display: block; }
.admin-site a.admin-metric:hover .admin-metric__label, .admin-site a.admin-metric:focus-visible .admin-metric__label { color: var(--text-primary); text-decoration: underline; }
```

Update any existing dashboard test (`grep -rn "admin-metric\|own_post_count" tests`) that relied on the old `<article>` markup or the `own_post_count` context.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_admin_dashboard.py tests/test_admin_access.py tests/test_admin_editorial_ui.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(admin): linked dashboard cards"
```

---

### Task 8: Full verification, browser check, docs

**Files:**
- Modify: `README.md` (admin section / migration warning), possibly CSS tweaks found during the visual check

- [ ] **Step 1: Full test suites**

Run: `python -m pytest -q && node --test tests/*.test.js`
Expected: all pass (pytest count grows from 595; node stays 50).

- [ ] **Step 2: README**

In `README.md` add to the migration warnings list: the new `c8d3a5e7b102` migration drops the legacy `about` table (the about text lives in the page table). In the admin description mention user management (create, edit, delete with article transfer) and that "关于" is an ordinary page managed under 页面管理.

- [ ] **Step 3: Browser check**

Use a scratch DB and helper scripts kept outside the repository (seed script, login, screenshot and Playwright wrapper scripts). Seed a few users (one with posts) and pages, run the app, then screenshot at 1440 and 390 widths, light and dark: `/admin/` (cards), `/admin/users`, `/admin/users?q=…`, `/admin/users/new`, `/admin/users/<id>/edit`, `/admin/users/<id>/delete`, `/admin/pages`, and the public `/about`. Check: rows do not overflow at 390px (the page-list action cluster now has five controls — if it wraps badly, let `.admin-list__actions` `flex-wrap: wrap` and left-align at ≤768px), the search field and filters line up, the danger button is readable in dark mode, and focus outlines are visible.

- [ ] **Step 4: Fix findings, rerun tests, commit**

```bash
python -m pytest -q
git add -A
git commit -m "docs: document admin user and page management"
```
