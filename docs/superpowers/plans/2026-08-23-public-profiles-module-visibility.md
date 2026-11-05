# Public Profiles And Module Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove following and its stored relationships, expose read-only user profiles publicly, and make Todo, Movie, Links, and Guestbook publication and navigation entirely authoritative from Page CMS.

**Architecture:** Remove the follow association from both the SQLAlchemy model and Flask/UI surfaces, with one destructive Alembic revision that drops only `followers`. Public profiles become anonymous-safe by guarding protected actions in Jinja, while built-in module routes resolve their existing `Page(kind='module')` record through one fail-closed helper; navigation renders only `visible_navigation_pages()`.

**Tech Stack:** Flask 3.1, Flask-Login, Flask-SQLAlchemy/SQLAlchemy 2.0, Alembic/Flask-Migrate, Jinja, pytest, MySQL production and SQLite tests.

## Global Constraints

- Permanently delete every existing follow relationship during upgrade; downgrade recreates an empty `followers` table and cannot restore deleted rows.
- A missing `followers` table is a migration error; do not silently skip the destructive upgrade.
- Do not change users, posts, roles, article content, view counts, Page CMS rows, or module data in the migration.
- Anonymous profile visitors may see avatar, username, about text, last-seen time, and paginated authored posts, but no edit, export, private-message, or follow action.
- Authenticated owners retain Edit Profile and Export Posts; authenticated non-owners retain Send Private Message.
- Keep edit-profile, export-posts, and send-message routes protected by their existing authentication rules.
- Remove `/following`, `/follow/<username>`, `/unfollow/<username>`, all follow model APIs, all follow UI, and the Following navigation entry.
- Remove `following` from the Page CMS reserved-slug set.
- Use the existing `Page.is_published`, `Page.show_in_nav`, and `Page.nav_order` fields as the only module visibility state.
- Missing or unpublished Todo, Movie, Links, or Guestbook Page records return 404 from every public address; hidden-but-published modules remain directly accessible.
- An unpublished or missing Guestbook Page must reject POST before inserting a comment.
- Authorized admin module routes remain available while the corresponding public module is unpublished.
- Remove the hard-coded public navigation fallback; Home, authenticated-only items, and Search retain their current behavior.
- Preserve published legacy GET redirects to renamed canonical module slugs and all query parameters.
- Preserve the current Guestbook legacy POST contract: validate publication first, create once, then redirect to its canonical slug.
- Do not run the destructive production MySQL migration without a fresh, separate user confirmation after code, tests, scratch migration rehearsal, and browser verification.

## File Structure

- Create `migrations/versions/d4a7c9e20f13_remove_followers.py`: drop `followers` on upgrade and recreate its empty former schema on downgrade.
- Create `tests/test_public_profiles.py`: own follow-removal, anonymous profile, action-boundary, popup, pagination, and protected-route regression tests.
- Modify `tests/test_migrations.py`: load and exercise the destructive revision, preservation guarantees, downgrade constraints, and singular migration head.
- Modify `app/models.py`: remove the followers table declaration, relationships, and helper/query methods.
- Modify `app/routes.py`: remove follow routes/feed and dead `EmptyForm` use, expose the profile route, and make module lookup fail closed.
- Modify `app/templates/user/user.html`: remove follow UI and guard owner/member actions for anonymous rendering.
- Modify `app/templates/user/user_popup.html`: retain public identity/about/last-seen content without follow form access.
- Modify `app/templates/base.html`: remove Following and the hard-coded Page navigation fallback.
- Modify `app/pages.py`: release `following` as a valid content-page slug.
- Modify `tests/test_pages.py`: cover the complete four-module publication/navigation/legacy/missing-record matrix and Guestbook write protection.
- Modify `tests/test_admin_modules.py`: prove admin module management is independent from public publication.
- Modify `tests/test_ui_shell.py`: prove no follow/fallback navigation markup and stable Page-driven order.
- Modify `tests/test_ui_pages.py`: give existing public module UI tests explicit published Page records under the new fail-closed contract.

---

### Task 1: Destructive Followers Table Migration

**Files:**
- Create: `migrations/versions/d4a7c9e20f13_remove_followers.py`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: Alembic head `c2f6e8a91d04`; existing `followers(follower_id, followed_id)` table with foreign keys to `user.id` and a composite primary key.
- Produces: Alembic head `d4a7c9e20f13`; upgrade schema without `followers`; downgrade schema with an empty `followers` table and no data-restoration promise.

- [ ] **Step 1: Add a revision loader and failing preservation test**

Add beside the existing revision constants and loaders in `tests/test_migrations.py`:

```python
FOLLOW_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / (
    'versions/d4a7c9e20f13_remove_followers.py')


def load_follow_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_followers', FOLLOW_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Add a focused migration test that creates only the tables and rows the
revision must preserve:

```python
def test_follow_removal_upgrade_drops_only_followers_and_preserves_content():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(64), nullable=False),
    )
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id')),
    )
    pages = sa.Table(
        'page', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('module_key', sa.String(32)),
        sa.Column('is_published', sa.Boolean, nullable=False),
        sa.Column('show_in_nav', sa.Boolean, nullable=False),
        sa.Column('nav_order', sa.Integer, nullable=False),
    )
    followers = sa.Table(
        'followers', metadata,
        sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
        sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(users.insert(), [
            {'id': 1, 'username': 'author'},
            {'id': 2, 'username': 'reader'},
        ])
        connection.execute(posts.insert().values(
            id=7, title='Preserved', user_id=1))
        connection.execute(pages.insert().values(
            id=9, module_key='todo', is_published=False,
            show_in_nav=True, nav_order=27))
        connection.execute(followers.insert().values(
            follower_id=2, followed_id=1))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

        inspector = sa.inspect(connection)
        assert 'followers' not in inspector.get_table_names()
        assert connection.execute(sa.text(
            'SELECT id, username FROM user ORDER BY id'
        )).mappings().all() == [
            {'id': 1, 'username': 'author'},
            {'id': 2, 'username': 'reader'},
        ]
        assert connection.execute(sa.text(
            'SELECT id, title, user_id FROM post')).mappings().one() == {
                'id': 7, 'title': 'Preserved', 'user_id': 1}
        assert connection.execute(sa.text(
            'SELECT id, module_key, is_published, show_in_nav, nav_order '
            'FROM page')).mappings().one() == {
                'id': 9, 'module_key': 'todo', 'is_published': False,
                'show_in_nav': True, 'nav_order': 27}
```

- [ ] **Step 2: Run the migration test and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_migrations.py::test_follow_removal_upgrade_drops_only_followers_and_preserves_content -v
```

Expected: FAIL while importing the absent
`d4a7c9e20f13_remove_followers.py` revision.

- [ ] **Step 3: Add the remaining failing migration-contract tests**

Append to `tests/test_migrations.py`:

```python
def test_follow_removal_downgrade_recreates_empty_table_with_constraints():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'followers', metadata,
        sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
        sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()

        inspector = sa.inspect(connection)
        assert connection.execute(sa.text(
            'SELECT COUNT(*) FROM followers')).scalar_one() == 0
        assert inspector.get_pk_constraint('followers')[
            'constrained_columns'] == ['follower_id', 'followed_id']
        foreign_keys = inspector.get_foreign_keys('followers')
        assert {tuple(item['constrained_columns']) for item in foreign_keys} == {
            ('follower_id',), ('followed_id',)}
        assert {item['referred_table'] for item in foreign_keys} == {'user'}


def test_follow_removal_upgrade_refuses_missing_followers_table():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with pytest.raises(sa.exc.OperationalError):
                revision.upgrade()


def test_follow_removal_revision_is_the_only_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations = Path(__file__).parents[1] / 'migrations'
    config = Config(str(migrations / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations))

    assert ScriptDirectory.from_config(config).get_heads() == [
        'd4a7c9e20f13']
```

Run:

```bash
.venv/bin/pytest tests/test_migrations.py::test_follow_removal_downgrade_recreates_empty_table_with_constraints tests/test_migrations.py::test_follow_removal_upgrade_refuses_missing_followers_table tests/test_migrations.py::test_follow_removal_revision_is_the_only_head -v
```

Expected: FAIL because the new revision is still absent and the current only
head remains `c2f6e8a91d04`.

- [ ] **Step 4: Create the destructive migration**

Create `migrations/versions/d4a7c9e20f13_remove_followers.py`:

```python
"""remove followers

Upgrade permanently deletes all follow relationships. Downgrade restores only
the empty association-table schema; deleted relationship rows are unrecoverable.

Revision ID: d4a7c9e20f13
Revises: c2f6e8a91d04
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a7c9e20f13'
down_revision = 'c2f6e8a91d04'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('followers')


def downgrade():
    op.create_table(
        'followers',
        sa.Column('follower_id', sa.Integer(), nullable=False),
        sa.Column('followed_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['followed_id'], ['user.id']),
        sa.ForeignKeyConstraint(['follower_id'], ['user.id']),
        sa.PrimaryKeyConstraint('follower_id', 'followed_id'),
    )
```

Do not add an inspector guard around `drop_table`: Alembic must stop if the
expected source table is missing.

- [ ] **Step 5: Run migration tests and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_migrations.py -v
.venv/bin/flask db heads
```

Expected: all migration tests PASS and exactly
`d4a7c9e20f13 (head)` is reported.

- [ ] **Step 6: Commit the migration**

```bash
git add migrations/versions/d4a7c9e20f13_remove_followers.py tests/test_migrations.py
git commit -m "feat: remove persisted follow relationships"
```

---

### Task 2: Follow Removal And Anonymous-Safe Public Profiles

**Files:**
- Create: `tests/test_public_profiles.py`
- Modify: `app/models.py:19-120`
- Modify: `app/routes.py:10-52,147-225`
- Modify: `app/templates/base.html:54-58`
- Modify: `app/templates/user/user.html:1-53`
- Modify: `app/templates/user/user_popup.html:1-27`
- Modify: `app/pages.py:14-18`

**Interfaces:**
- Consumes: `User.posts`, `User.avatar(size)`, `User.last_seen`, Flask-Login's anonymous `current_user`, and existing protected `edit_profile`, `export_posts`, and `send_message` endpoints.
- Produces: public `GET /user/<username>` and `GET /user/<username>/popup`; no follow-related model attribute or route endpoint; `normalize_slug('following') == 'following'`.

- [ ] **Step 1: Write failing model and route-removal tests**

Create `tests/test_public_profiles.py`:

```python
import sqlalchemy as sa

from app import app, db
from app.models import Post, User


FOLLOW_ATTRIBUTES = (
    'following', 'followers', 'follow', 'unfollow', 'is_following',
    'followers_count', 'following_count', 'following_posts',
)


def test_user_model_and_metadata_have_no_follow_api(application):
    with application.app_context():
        assert 'followers' not in db.metadata.tables
        for attribute in FOLLOW_ATTRIBUTES:
            assert not hasattr(User, attribute)


def test_old_follow_routes_are_absent(client, application, users):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/following' not in rules
    assert '/follow/<username>' not in rules
    assert '/unfollow/<username>' not in rules
    assert client.get('/following').status_code == 404
    assert client.post('/follow/author').status_code == 404
    assert client.post('/unfollow/author').status_code == 404
```

Add the released-slug assertion to `tests/test_pages.py`:

```python
def test_removed_following_route_releases_page_slug():
    assert normalize_slug('following') == 'following'
```

- [ ] **Step 2: Run removal tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_public_profiles.py::test_user_model_and_metadata_have_no_follow_api tests/test_public_profiles.py::test_old_follow_routes_are_absent tests/test_pages.py::test_removed_following_route_releases_page_slug -v
```

Expected: FAIL because the association/model methods/routes still exist and
`following` is still reserved.

- [ ] **Step 3: Remove all follow model, route, navigation, and slug ownership**

In `app/models.py`, delete the module-level `followers = sa.Table(...)`, both
`User` relationships, and these methods in full:

```python
def follow(self, user): ...
def unfollow(self, user): ...
def is_following(self, user): ...
def followers_count(self): ...
def following_count(self): ...
def following_posts(self): ...
```

In `app/routes.py`, delete the full `/following`, `/follow/<username>`, and
`/unfollow/<username>` route blocks. Remove `EmptyForm` from the `app.forms`
import because no remaining route uses it.

In `app/templates/base.html`, delete only:

```jinja2
<li><a href="{{ url_for('following') }}">{{ _('Following') }}</a></li>
```

In `app/pages.py`, change the reserved portion to:

```python
RESERVED_SLUGS = frozenset({
    'admin', 'login', 'logout', 'register', 'reset-password', 'post', 'user',
    'static', 'files', 'upload', 'rss', 'index', 'search',
    'messages', 'notifications', 'categories', 'category',
})
```

- [ ] **Step 4: Run removal tests and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_public_profiles.py::test_user_model_and_metadata_have_no_follow_api tests/test_public_profiles.py::test_old_follow_routes_are_absent tests/test_pages.py::test_removed_following_route_releases_page_slug -v
```

Expected: all selected tests PASS.

- [ ] **Step 5: Write failing anonymous profile content tests**

Extend `tests/test_public_profiles.py`:

```python
def test_anonymous_profile_shows_public_fields_and_authored_posts(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        author.about_me = 'Public biography'
        author.last_seen = author.last_seen.replace(microsecond=0)
        db.session.commit()

    response = client.get('/user/author')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'author' in html
    assert 'Public biography' in html
    assert 'Last seen on' in html
    assert 'Test' in html
    assert 'cravatar.cn/avatar/' in html


def test_anonymous_profile_pagination_keeps_profile_endpoint(
        client, application, users, monkeypatch):
    monkeypatch.setitem(application.config, 'POSTS_PER_PAGE', 1)
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.get(Post, users['post']).category
        db.session.add(Post(
            title='Older profile post', body='Body', author=author,
            category=category))
        db.session.commit()

    response = client.get('/user/author?page=1')
    assert response.status_code == 200
    assert 'href="/user/author?page=2"' in response.get_data(as_text=True)


def test_unknown_public_profile_is_not_found(client):
    assert client.get('/user/missing-reader').status_code == 404


def test_anonymous_profile_popup_renders_public_fields(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        author.about_me = 'Popup biography'
        db.session.commit()

    response = client.get('/user/author/popup')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'author' in html
    assert 'Popup biography' in html
    assert 'Last seen on' in html
    assert 'cravatar.cn/avatar/' in html
```

- [ ] **Step 6: Run public profile tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_public_profiles.py::test_anonymous_profile_shows_public_fields_and_authored_posts tests/test_public_profiles.py::test_anonymous_profile_pagination_keeps_profile_endpoint tests/test_public_profiles.py::test_unknown_public_profile_is_not_found tests/test_public_profiles.py::test_anonymous_profile_popup_renders_public_fields -v
```

Expected: the full-profile tests FAIL with a login redirect, and popup rendering
fails while it still calls follow methods.

- [ ] **Step 7: Make profile routes and templates anonymous-safe**

Change the profile routes in `app/routes.py` to remove `login_required`, form
construction, and the now-unused template argument while keeping pagination:

```python
@app.route('/user/<username>')
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    page = request.args.get('page', 1, type=int)
    query = user.posts.select().order_by(Post.timestamp.desc())
    posts = db.paginate(
        query, page=page, per_page=app.config['POSTS_PER_PAGE'],
        error_out=False)
    next_url = url_for('user', username=user.username, page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('user', username=user.username, page=posts.prev_num) \
        if posts.has_prev else None
    return render_template(
        'user/user.html', title=_('User Profile'), user=user,
        posts=posts.items, next_url=next_url, prev_url=prev_url)


@app.route('/user/<username>/popup')
def user_popup(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    return render_template('user/user_popup.html', user=user)
```

Replace the follow/count action region in `app/templates/user/user.html` with:

```jinja2
{% if current_user.is_authenticated %}
<div class="profile-actions">
  {% if user == current_user %}
  <a href="{{ url_for('edit_profile') }}" class="btn btn-secondary">{{ _('Edit your profile') }}</a>
  {% if not current_user.get_task_in_progress('export_posts') %}
  <a href="{{ url_for('export_posts') }}" class="btn btn-secondary">{{ _('Export your posts') }}</a>
  {% endif %}
  {% else %}
  <a href="{{ url_for('send_message', recipient=user.username) }}" class="btn btn-outline-primary">{{ _('Send private message') }}</a>
  {% endif %}
</div>
{% endif %}
```

Delete the follower count and all forms from
`app/templates/user/user_popup.html`, leaving avatar, linked username, about
text, clearfix, and last-seen time.

- [ ] **Step 8: Add action-boundary and protected-route tests**

Extend `tests/test_public_profiles.py` and import `login`:

```python
from tests.conftest import login


def test_anonymous_profile_has_no_protected_or_follow_actions(client, users):
    html = client.get('/user/author').get_data(as_text=True)
    for forbidden in (
        '/edit_profile', '/export_posts', '/send_message/', '/follow/',
        '/unfollow/', 'followers', 'following',
    ):
        assert forbidden not in html


def test_owner_profile_keeps_edit_and_export_actions(client, users):
    login(client, 'author')
    html = client.get('/user/author').get_data(as_text=True)
    assert 'href="/edit_profile"' in html
    assert 'href="/export_posts"' in html
    assert '/send_message/' not in html


def test_authenticated_non_owner_keeps_private_message_action(client, users):
    login(client, 'other')
    html = client.get('/user/author').get_data(as_text=True)
    assert 'href="/send_message/author"' in html
    assert '/edit_profile' not in html
    assert '/export_posts' not in html


def test_profile_popup_has_no_follow_surface(client, users):
    html = client.get('/user/author/popup').get_data(as_text=True)
    for forbidden in (
        '/follow/', '/unfollow/', 'followers', 'following', '<form',
    ):
        assert forbidden not in html


def test_profile_mutation_routes_stay_login_protected(client, users):
    assert client.get('/edit_profile').status_code == 302
    assert client.get('/export_posts').status_code == 302
    response = client.get('/send_message/author')
    assert response.status_code == 302
    assert '/login?next=' in response.headers['Location']
```

- [ ] **Step 9: Run the complete profile/removal suite and inspect references**

Run:

```bash
.venv/bin/pytest tests/test_public_profiles.py tests/test_pages.py::test_removed_following_route_releases_page_slug -v
rg -n "followers_count|following_count|is_following|following_posts|url_for\('follow'|url_for\('unfollow'|url_for\('following'" app --glob '!translations/**'
```

Expected: all selected tests PASS and `rg` returns no application-code match.

- [ ] **Step 10: Commit follow removal and public profiles**

```bash
git add app/models.py app/routes.py app/pages.py app/templates/base.html app/templates/user/user.html app/templates/user/user_popup.html tests/test_public_profiles.py tests/test_pages.py
git commit -m "feat: publish user profiles without following"
```

---

### Task 3: Page-Authoritative Module Publication And Navigation

**Files:**
- Modify: `app/routes.py:229-245,263-273,313-352,366-389,691-700,792-811`
- Modify: `app/templates/base.html:59-72`
- Modify: `tests/test_pages.py:413-564`
- Modify: `tests/test_admin_modules.py`
- Modify: `tests/test_ui_shell.py`
- Modify: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: `Page.module_key`, `Page.slug`, `Page.is_published`, `Page.show_in_nav`, `Page.nav_order`, `page_for_public_slug(slug)`, and `visible_navigation_pages()`.
- Produces: `_module_page(module_key: str, legacy_slug: str, page_config: Page | None = None) -> tuple[Page, Response | None]`, where missing/unpublished configuration aborts 404 and a published renamed legacy GET produces a 301 response.

- [ ] **Step 1: Add a module-matrix helper and failing access tests**

Add to `tests/test_pages.py`:

```python
MODULE_CASES = (
    pytest.param('todo', 'todo', 'tasks-cms', id='todo'),
    pytest.param('movie', 'movie', 'films-cms', id='movie'),
    pytest.param('links', 'links', 'bookmarks-cms', id='links'),
    pytest.param('guestbook', 'comment', 'guestbook-cms', id='guestbook'),
)


def add_module_page(module_key, slug, *, published=True, visible=True,
                    nav_order=10):
    page = Page(kind='module', module_key=module_key)
    save_page(page, {
        'title': f'{module_key.title()} CMS',
        'slug': slug,
        'is_published': published,
        'show_in_nav': visible,
        'nav_order': nav_order,
    })
    return page


@pytest.mark.parametrize(('module_key', 'legacy_slug', 'canonical_slug'),
                         MODULE_CASES)
def test_published_visible_module_is_public_and_in_navigation(
        client, application, module_key, legacy_slug, canonical_slug):
    with application.app_context():
        add_module_page(module_key, canonical_slug, published=True,
                        visible=True)
        db.session.commit()

    canonical = client.get(f'/{canonical_slug}')
    legacy = client.get(f'/{legacy_slug}')
    navigation = client.get('/').get_data(as_text=True)

    assert canonical.status_code == 200
    assert legacy.status_code == 301
    assert legacy.headers['Location'].endswith(f'/{canonical_slug}')
    assert f'href="/{canonical_slug}"' in navigation


@pytest.mark.parametrize(('module_key', 'legacy_slug', 'canonical_slug'),
                         MODULE_CASES)
def test_published_hidden_module_is_public_but_absent_from_navigation(
        client, application, module_key, legacy_slug, canonical_slug):
    with application.app_context():
        add_module_page(module_key, canonical_slug, published=True,
                        visible=False)
        db.session.commit()

    assert client.get(f'/{canonical_slug}').status_code == 200
    assert f'href="/{canonical_slug}"' not in client.get(
        '/').get_data(as_text=True)
```

- [ ] **Step 2: Run published module tests and establish baseline**

Run:

```bash
.venv/bin/pytest tests/test_pages.py::test_published_visible_module_is_public_and_in_navigation tests/test_pages.py::test_published_hidden_module_is_public_but_absent_from_navigation -v
```

Expected: selected cases PASS under the current Page-backed happy path. This
step records preserved behavior before tightening missing/unpublished handling.

- [ ] **Step 3: Write failing missing/unpublished matrix tests**

Add to `tests/test_pages.py`:

```python
@pytest.mark.parametrize(('module_key', 'legacy_slug', 'canonical_slug'),
                         MODULE_CASES)
def test_unpublished_module_rejects_canonical_and_legacy_get_and_hides_nav(
        client, application, module_key, legacy_slug, canonical_slug):
    with application.app_context():
        add_module_page(module_key, canonical_slug, published=False,
                        visible=True)
        db.session.commit()

    assert client.get(f'/{canonical_slug}').status_code == 404
    assert client.get(f'/{legacy_slug}').status_code == 404
    assert f'href="/{canonical_slug}"' not in client.get(
        '/').get_data(as_text=True)


@pytest.mark.parametrize(('module_key', 'legacy_slug', 'canonical_slug'),
                         MODULE_CASES)
def test_missing_module_configuration_fails_closed(
        client, module_key, legacy_slug, canonical_slug):
    assert client.get(f'/{legacy_slug}').status_code == 404
    assert client.get(f'/{canonical_slug}').status_code == 404
```

The missing-record legacy cases are expected to expose the current fallback,
which serves Todo, Movie, Links, and Guestbook without a Page row.

- [ ] **Step 4: Run fail-closed tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_pages.py::test_unpublished_module_rejects_canonical_and_legacy_get_and_hides_nav tests/test_pages.py::test_missing_module_configuration_fails_closed -v
```

Expected: unpublished cases PASS, while each missing-record legacy request
FAILS because it currently returns 200.

- [ ] **Step 5: Make the shared module resolver fail closed**

Replace `_module_page()` in `app/routes.py` with:

```python
def _module_page(module_key, legacy_slug, page_config=None):
    if page_config is None:
        page_config = db.session.scalar(sa.select(Page).where(
            Page.module_key == module_key))
    if page_config is None or not page_config.is_published:
        abort(404)
    if request.path == f'/{legacy_slug}' and page_config.slug != legacy_slug:
        target_values = request.args.to_dict(flat=True)
        target_values['slug'] = page_config.slug
        return page_config, redirect(
            url_for('public_page', **target_values), code=301)
    return page_config, None
```

Update Guestbook so both methods resolve visibility before constructing or
validating the form, while POST avoids redirecting before form processing:

```python
@app.route('/comment', methods=['GET', 'POST'])
def comment(page_config=None):
    if request.method == 'POST':
        if page_config is None:
            page_config = db.session.scalar(sa.select(Page).where(
                Page.module_key == 'guestbook'))
        if page_config is None or not page_config.is_published:
            abort(404)
    else:
        page_config, compatibility = _module_page(
            'guestbook', 'comment', page_config)
        if compatibility is not None:
            return compatibility
```

After this change, the `page_config else` route/title fallbacks in module views
are unreachable. Leave their cosmetic cleanup out of this feature unless a
test demonstrates a behavior problem.

- [ ] **Step 6: Run the module matrix and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_pages.py::test_published_visible_module_is_public_and_in_navigation tests/test_pages.py::test_published_hidden_module_is_public_but_absent_from_navigation tests/test_pages.py::test_unpublished_module_rejects_canonical_and_legacy_get_and_hides_nav tests/test_pages.py::test_missing_module_configuration_fails_closed -v
```

Expected: all 16 parameterized module cases PASS.

- [ ] **Step 7: Add Guestbook mutation and redirect regression tests**

Add to `tests/test_pages.py`:

```python
@pytest.mark.parametrize('configured', [True, False], ids=['unpublished',
                                                           'missing'])
def test_unavailable_guestbook_post_is_not_found_without_insert(
        client, application, configured):
    with application.app_context():
        if configured:
            add_module_page('guestbook', 'guestbook-cms', published=False)
            db.session.commit()

    response = client.post('/comment', data={
        'name': 'Reader', 'email': 'reader@example.com', 'body': 'Blocked',
    })

    assert response.status_code == 404
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            Comment)) == 0


def test_published_renamed_guestbook_legacy_post_creates_once_and_redirects(
        client, application):
    with application.app_context():
        add_module_page('guestbook', 'guestbook-cms', published=True)
        db.session.commit()

    response = client.post('/comment', data={
        'name': 'Reader', 'email': 'reader@example.com', 'body': 'Accepted',
    })

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/guestbook-cms')
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            Comment)) == 1


def test_renamed_module_legacy_redirect_preserves_query_string(
        client, application):
    with application.app_context():
        add_module_page('todo', 'tasks-cms', published=True)
        db.session.commit()

    response = client.get('/todo?page=3')
    assert response.status_code == 301
    assert response.headers['Location'].endswith('/tasks-cms?page=3')
```

- [ ] **Step 8: Add failing no-fallback navigation tests**

Add to `tests/test_ui_shell.py`:

```python
def test_empty_page_navigation_does_not_restore_hardcoded_modules(client):
    html = client.get('/').get_data(as_text=True)

    for href in ('/movie', '/comment', '/todo', '/links', '/about'):
        assert f'href="{href}"' not in html
    assert 'href="/"' in html
    assert 'action="/search"' in html


def test_page_navigation_keeps_database_order_without_following(
        client, application):
    with application.app_context():
        db.session.add_all([
            Page(title='Later', slug='later-nav', kind='content',
                 body='Later', is_published=True, show_in_nav=True,
                 nav_order=30),
            Page(title='First', slug='first-nav', kind='content',
                 body='First', is_published=True, show_in_nav=True,
                 nav_order=10),
        ])
        db.session.commit()

    html = client.get('/').get_data(as_text=True)
    assert html.index('href="/first-nav"') < html.index('href="/later-nav"')
    assert 'Following' not in html
    assert 'href="/following"' not in html
```

- [ ] **Step 9: Remove the hard-coded navigation fallback**

Replace the Page navigation condition in `app/templates/base.html` with an
unconditional loop:

```jinja2
{% for page in navigation_pages %}
<li><a href="{{ url_for('public_page', slug=page.slug) }}">{{ page.title }}</a></li>
{% endfor %}
```

Do not add any fallback links when `navigation_pages` is empty.

- [ ] **Step 10: Update existing public module UI tests for explicit Page configuration**

In `tests/test_ui_pages.py`, add this helper below the imports:

```python
MODULE_BY_PATH = {
    '/todo': ('todo', 'Todo'),
    '/movie': ('movie', 'Movie'),
    '/links': ('links', 'Links'),
    '/comment': ('guestbook', 'Guestbook'),
}


def add_published_module_for_path(path):
    module_key, title = MODULE_BY_PATH[path]
    db.session.add(Page(
        title=title, slug=path.removeprefix('/'), kind='module',
        module_key=module_key, is_published=True, show_in_nav=True,
        nav_order=10))
```

In `test_public_pages_render_in_the_shared_design`, extend its application
context setup so module paths call the helper before commit:

```python
with application.app_context():
    if path == '/about':
        db.session.add(Page(
            title='About', slug='about', kind='content',
            body='<p>About</p>', is_published=True))
    elif path in MODULE_BY_PATH:
        add_published_module_for_path(path)
    db.session.commit()
```

Seed the needed module Page in each existing test before its public request:

```python
with application.app_context():
    add_published_module_for_path('/comment')
    db.session.commit()
```

Use that block in `test_comment_textareas_do_not_opt_in_to_markdown_editor`.
In `test_authenticated_member_sees_no_public_about_or_todo_controls`, add an
`application` argument and seed both pages before login:

```python
with application.app_context():
    db.session.add(Page(
        title='About', slug='about', kind='content', body='<p>About</p>',
        is_published=True, show_in_nav=True, nav_order=5))
    add_published_module_for_path('/todo')
    db.session.commit()
```

In `test_todo_pagination_preserves_page_urls`, call
`add_published_module_for_path('/todo')` in the existing application context
before adding the two Todo rows. Keep each assertion unchanged so the tests
still verify the intended rendered UI rather than a 404 response.

- [ ] **Step 11: Update existing admin/public separation tests and prove admin availability**

In `tests/test_admin_modules.py`, add this helper after imports:

```python
PUBLIC_MODULES = {
    '/todo': ('todo', 'todo', 'Todo'),
    '/movie': ('movie', 'movie', 'Movie'),
    '/links': ('links', 'links', 'Links'),
    '/comment': ('guestbook', 'comment', 'Guestbook'),
}


def add_published_module(module_key, legacy_slug, title):
    db.session.add(Page(
        title=title, slug=legacy_slug, kind='module', module_key=module_key,
        is_published=True, show_in_nav=True, nav_order=10))
```

Import `Page` from `app.models`. In
`test_public_module_pages_have_no_management_actions`, create the Page
alongside its visible data and strengthen the request assertion:

```python
if path in PUBLIC_MODULES:
    add_published_module(*PUBLIC_MODULES[path])

response = client.get(path)
assert response.status_code == 200
assert forbidden_fragment not in response.get_data(as_text=True)
```

In `test_public_guestbook_submission_remains_available`, seed:

```python
with application.app_context():
    add_published_module('guestbook', 'comment', 'Guestbook')
    db.session.commit()
```

Then retain its existing `302` and persisted-comment assertions.

Add to `tests/test_admin_modules.py` and import `Page`:

```python
@pytest.mark.parametrize('path', [
    '/admin/todos', '/admin/movies', '/admin/links', '/admin/comments',
])
def test_admin_module_management_remains_available_when_public_pages_hidden(
        client, application, users, path):
    with application.app_context():
        db.session.add_all([
            Page(title='Todo', slug='todo', kind='module', module_key='todo',
                 is_published=False, show_in_nav=False, nav_order=20),
            Page(title='Movie', slug='movie', kind='module', module_key='movie',
                 is_published=False, show_in_nav=False, nav_order=30),
            Page(title='Links', slug='links', kind='module', module_key='links',
                 is_published=False, show_in_nav=False, nav_order=40),
            Page(title='Guestbook', slug='guestbook', kind='module',
                 module_key='guestbook', is_published=False,
                 show_in_nav=False, nav_order=50),
        ])
        db.session.commit()

    login(client, 'admin')
    assert client.get(path).status_code == 200
```

- [ ] **Step 12: Run focused Page, navigation, admin, and UI suites**

Run:

```bash
.venv/bin/pytest tests/test_pages.py tests/test_admin_modules.py tests/test_ui_shell.py tests/test_ui_pages.py -v
```

Expected: all selected tests PASS, including the four-module matrix, no-write
Guestbook cases, Page-driven order, and admin/public separation.

- [ ] **Step 13: Commit module publication and navigation behavior**

```bash
git add app/routes.py app/templates/base.html tests/test_pages.py tests/test_admin_modules.py tests/test_ui_shell.py tests/test_ui_pages.py
git commit -m "feat: control public modules from page settings"
```

---

### Task 4: Full Verification And Production Migration Handoff

**Files:**
- Modify only files required by failures reproduced during this task.
- Verify all application, migration, template, and test files changed in Tasks 1-3.
- Create untracked browser evidence under `instance/backups/public-profiles-modules-2026-08-23/` only when screenshots are useful; do not commit production data or backups.

**Interfaces:**
- Consumes: Alembic revision `d4a7c9e20f13`, public profile routes, fail-closed module resolver, and Page-only navigation.
- Produces: passing focused/full tests, a reversible scratch migration rehearsal, browser evidence, code review resolution, and a separately gated production deployment checklist.

- [ ] **Step 1: Run static checks and the complete automated suite**

Run:

```bash
git diff --check
.venv/bin/python -m compileall -q app migrations tests
.venv/bin/pytest -q
.venv/bin/flask db heads
```

Expected: no whitespace or compilation errors; every test passes (baseline was
248 passed with one pre-existing SQLAlchemy `Query.get()` warning); exactly
`d4a7c9e20f13 (head)` is reported.

- [ ] **Step 2: Rehearse upgrade/downgrade on disposable SQLite**

Create a temporary database without touching the configured development or
production database:

```bash
PUBLIC_PROFILE_SCRATCH_DIR="$(mktemp -d /tmp/flog-public-profiles.XXXXXX)"
PUBLIC_PROFILE_SCRATCH_URL="sqlite:///$PUBLIC_PROFILE_SCRATCH_DIR/rehearsal.db"
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db upgrade c2f6e8a91d04
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db current
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db upgrade d4a7c9e20f13
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db current
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db downgrade c2f6e8a91d04
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask db upgrade d4a7c9e20f13
```

Expected: current changes from `c2f6e8a91d04` to `d4a7c9e20f13`; upgrade
removes `followers`; downgrade recreates it empty; the final upgrade succeeds.
Remove only the exact `PUBLIC_PROFILE_SCRATCH_DIR` after verifying its path
starts with `/tmp/flog-public-profiles.`.

- [ ] **Step 3: Start an isolated local server for browser checks**

Use a disposable SQLite database, seed two users, a long profile title/about
value, posts, and all four module Page rows, then start Flask on an unused port.
Do not point browser QA at production MySQL. A concrete default command is:

```bash
DATABASE_URL="$PUBLIC_PROFILE_SCRATCH_URL" .venv/bin/flask run --host 127.0.0.1 --port 5012
```

Expected: the application is reachable at `http://127.0.0.1:5012/`. If 5012
is occupied, choose the next unused port and record it in the verification
notes.

- [ ] **Step 4: Verify anonymous and authenticated profile states**

Using the in-app browser, check desktop `1440x900` and mobile `390x844`:

- anonymous long-username profile and popup show avatar, username, about,
  last-seen time, and posts without login redirect or server error;
- anonymous HTML has no Edit Profile, Export Posts, Send Private Message,
  Follow, Unfollow, follower count, or following count;
- the owner sees Edit Profile and Export Posts;
- a signed-in non-owner sees Send Private Message but no owner actions;
- pagination remains on `/user/<username>?page=N`;
- protected edit/export/message URLs still redirect anonymous requests to login;
- long username/about text wraps with no clipping, overlap, or horizontal
  overflow in both light and dark mode.

- [ ] **Step 5: Verify full, partial, and empty module navigation states**

Through `/admin/pages`, exercise the existing publication, navigation, and
order fields for Todo, Movie, Links, and Guestbook:

- all published and visible: all four appear in `nav_order` and open normally;
- one published but hidden: it disappears from navigation and remains directly
  accessible at its configured slug;
- one unpublished with `show_in_nav` still checked: canonical and legacy GET
  return 404 and it remains absent from navigation;
- unpublished Guestbook POST returns 404 and creates no row;
- renamed published modules redirect legacy GET addresses to canonical slugs;
- with all Page rows hidden/unpublished, no hard-coded Movie, Guestbook, Todo,
  Links, or About entries reappear;
- admin Todo/Movie/Links/Comments screens remain accessible in all public states.

At both viewports, open and close the mobile sidebar and verify no overlap,
horizontal overflow, broken navigation toggle, failed network request, or
console error. Repeat one full and one empty navigation state in dark mode.

- [ ] **Step 6: Search for dead follow references and inspect the final diff**

Run:

```bash
rg -n "followers_count|following_count|is_following|following_posts|url_for\('follow'|url_for\('unfollow'|url_for\('following'" app tests --glob '!translations/**'
git diff c2f6e8a91d04..HEAD -- app migrations tests
git status --short
```

Expected: the reference search returns no application/test match; the diff
contains only the approved migration, follow/profile removal, Page visibility,
navigation, and tests; browser screenshots and database files are not staged.

- [ ] **Step 7: Request final code review and resolve verified findings**

Use the `requesting-code-review` skill against
`docs/superpowers/specs/2026-08-23-public-profiles-module-visibility-design.md`.
For each valid finding, write or tighten the smallest reproducing test, verify
RED, apply the minimal fix, and rerun the focused test. Then repeat Step 1.

- [ ] **Step 8: Commit verification fixes only when needed**

If review or browser verification required changes, stage the exact changed
source and test files and commit:

```bash
git add app migrations/versions/d4a7c9e20f13_remove_followers.py tests
git commit -m "fix: address public profile verification findings"
```

If verification made no tracked changes, do not create an empty commit.

- [ ] **Step 9: Prepare the production MySQL preflight without upgrading**

After all prior steps pass, request a fresh explicit confirmation. Only after
approval, load `.env` without printing secrets and derive a timestamped backup
filename. Before `flask db upgrade`, record:

```sql
SELECT DATABASE();
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS follower_rows FROM followers;
SELECT COUNT(*) AS user_rows FROM user;
SELECT COUNT(*) AS post_rows FROM post;
SELECT module_key, slug, is_published, show_in_nav, nav_order
FROM page
WHERE module_key IN ('todo', 'movie', 'links', 'guestbook')
ORDER BY module_key;
```

Create a consistent timestamped `mysqldump` backup under `instance/backups/`,
run `shasum -a 256` on it, verify the file is non-empty, and record the checksum.
Do not continue if the selected database, current revision, counts, module
state, backup, or checksum differs from the approved target.

- [ ] **Step 10: Upgrade production only after the separate confirmation**

Run the exact production upgrade through the application's configured
`DATABASE_URL`:

```bash
.venv/bin/flask db upgrade d4a7c9e20f13
.venv/bin/flask db current
```

Expected: revision is `d4a7c9e20f13`; querying
`information_schema.tables` confirms `followers` is absent; user/post counts
and all four module Page rows exactly match Step 9. Restart/deploy application
code only after schema verification, then smoke-test an anonymous profile and
all four public modules.

- [ ] **Step 11: Record the irreversible-data warning in the handoff**

The completion report must state the backup path and checksum, the before/after
revision, deleted relationship-row count, preserved user/post counts, preserved
module Page states, smoke-test results, and this exact limitation: downgrading
recreates an empty `followers` table but cannot restore deleted follow
relationships.
