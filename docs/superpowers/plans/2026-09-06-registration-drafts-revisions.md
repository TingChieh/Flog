# Registration, Drafts, and Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent registration control, private auto-saved article drafts, and a globally bounded revision timeline that restores into a draft before explicit publication.

**Architecture:** Keep Post as the public article record. Add singleton SiteSettings, one current PostDraft per post, and immutable PostRevision snapshots. Centralize lifecycle rules in app/post_drafts.py so admin endpoints and legacy adapters share the same state changes.

**Tech Stack:** Flask, Flask-Login, Flask-WTF CSRF, SQLAlchemy 2, Alembic, Jinja2, EasyMDE, vanilla JavaScript, pytest, Node.js node:test.

## Global Constraints

- Registration is persistent, defaults open, and the server-side registration POST rejects when disabled.
- New posts are unpublished. Index, profile, category, search, RSS, detail, comments, and likes resolve published posts only.
- Editing a published post changes only PostDraft until an explicit publication action.
- Restoring history changes only PostDraft. It cannot publish by itself.
- Auto-save is debounced one second; leaving an editor with changed content creates one revision.
- post_revision_limit is global, defaults to 20, permits 1 through 100, and immediately trims every post when reduced.
- Preserve existing authorization, CSRF, Markdown/legacy-HTML handling, and legacy edit URLs.

---

## File Structure

- app/models.py: SiteSettings, PostDraft, PostRevision, and Post relationships.
- app/post_drafts.py: draft, publication, restore, snapshot, and retention operations.
- migrations/versions/f6d41a2b9c03_add_site_settings_post_drafts.py: schema and data migration.
- app/admin/settings.py, app/admin/forms.py, app/templates/admin/settings/form.html: global settings UI.
- app/admin/posts.py and post editor templates: JSON autosave endpoints and explicit post actions.
- app/routes.py: registration gate and public visibility helper.
- app/static/markdown-editor.js: debounce, page-exit snapshot, and save status.
- test files: migration, registration, authorization, lifecycle, visibility, and browser coverage.

### Task 1: Add Persistent Models and Migration

**Files:**
- Modify: app/models.py
- Create: migrations/versions/f6d41a2b9c03_add_site_settings_post_drafts.py
- Modify: tests/conftest.py
- Modify: tests/test_migrations.py

**Interfaces:**
- Produces SiteSettings(id=1, registration_open, post_revision_limit) and get_site_settings().
- Produces Post.is_published, Post.draft, and newest-first Post.revisions.
- Produces PostDraft(post_id, title, body, category_id, language, updated_at) and PostRevision(..., created_at).

- [ ] **Step 1: Write failing migration test**

~~~python
def test_drafts_migration_publishes_existing_posts_and_seeds_settings():
    revision = load_drafts_revision()
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
        connection.execute(posts.insert().values(title='Existing', body='Body'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.execute(sa.text(
            'SELECT is_published FROM post')).scalar_one() is True
        assert connection.execute(sa.text(
            'SELECT registration_open, post_revision_limit FROM site_settings'
        )).mappings().one() == {
            'registration_open': True, 'post_revision_limit': 20}
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_migrations.py -k drafts -v

Expected: FAIL because the migration module and models do not exist.

- [ ] **Step 3: Implement models and migration**

~~~python
class SiteSettings(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, default=1)
    registration_open: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
    post_revision_limit: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=20, server_default=sa.text('20'))


class PostDraft(db.Model):
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey('post.id', ondelete='CASCADE'), primary_key=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    body: so.Mapped[str] = so.mapped_column(sa.Text, nullable=False)
    category_id: so.Mapped[int | None] = so.mapped_column(
        sa.ForeignKey('category.id'))
    language: so.Mapped[str | None] = so.mapped_column(sa.String(5))
~~~

Add an analogous immutable PostRevision with indexed created_at. Add delete-orphan Post relationships. Migration must add non-null post.is_published with a true server default, backfill current posts, create settings/draft/revision tables and indexes, seed settings id 1 with true/20, and define downgrade. Seed SiteSettings in tests/conftest.py after db.create_all.

- [ ] **Step 4: Verify green**

Run: pytest tests/test_migrations.py -k drafts -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/models.py migrations/versions/f6d41a2b9c03_add_site_settings_post_drafts.py tests/conftest.py tests/test_migrations.py
git commit -m "feat: persist article drafts and revisions"
~~~

### Task 2: Add Administrator Settings and Registration Gate

**Files:**
- Modify: app/admin/forms.py, app/admin/__init__.py, app/templates/admin/base.html, app/routes.py
- Create: app/admin/settings.py, app/templates/admin/settings/form.html
- Modify: tests/test_roles.py, tests/test_admin_access.py

**Interfaces:**
- Produces SiteSettingsForm(registration_open, post_revision_limit).
- Produces administrator-only GET|POST /admin/settings.
- Consumes get_site_settings from register() and trim_all_post_revisions(limit).

- [ ] **Step 1: Write failing settings tests**

~~~python
def test_closed_registration_rejects_a_valid_submission(client, application):
    with application.app_context():
        get_site_settings().registration_open = False
        db.session.commit()
    response = client.post('/register', data={
        'username': 'blocked', 'email': 'blocked@example.com',
        'password': 'password', 'password2': 'password',
    })
    assert response.status_code == 403
    with application.app_context():
        assert db.session.scalar(sa.select(User).where(
            User.username == 'blocked')) is None


def test_only_administrator_can_change_site_settings(client, users):
    login(client, 'author')
    assert client.get('/admin/settings').status_code == 403
    login(client, 'admin')
    response = client.post('/admin/settings', data={
        'registration_open': '', 'post_revision_limit': '7'})
    assert response.status_code == 302
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_roles.py tests/test_admin_access.py -k "registration or settings" -v

Expected: FAIL because registration is still open and settings route is absent.

- [ ] **Step 3: Implement settings and the gate**

~~~python
class SiteSettingsForm(FlaskForm):
    registration_open = BooleanField('开放用户注册')
    post_revision_limit = IntegerField(
        '每篇文章可回滚版本数量',
        validators=[InputRequired(), NumberRange(min=1, max=100)])
    submit = SubmitField('保存设置')
~~~

Add a settings route protected by login_required and admin_required. On valid POST update settings, call trim_all_post_revisions, commit, and redirect. Add it under System navigation. In register(), reject closed registration before validation and again before User creation with abort(403).

- [ ] **Step 4: Verify green**

Run: pytest tests/test_roles.py tests/test_admin_access.py -k "registration or settings" -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/admin app/routes.py app/templates/admin tests/test_roles.py tests/test_admin_access.py
git commit -m "feat: add registration and revision settings"
~~~

### Task 3: Isolate Unpublished Posts from Public Routes

**Files:**
- Modify: app/routes.py, app/templates/index.html
- Create: tests/test_public_visibility.py
- Modify: tests/test_post_interactions.py, tests/test_post_views.py

**Interfaces:**
- Produces published_post_statement() and public_post_or_404(post_id).
- Public GET/POST post operations resolve only published posts.

- [ ] **Step 1: Write failing visibility tests**

~~~python
@pytest.mark.parametrize('path', [
    '/', '/user/author', '/search?q=private', '/category/1', '/rss',
])
def test_unpublished_posts_are_absent_from_public_collections(
        client, application, users, path):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = False
        post.body = 'private marker'
        db.session.commit()
    response = client.get(path)
    assert response.status_code == 200
    assert 'private marker' not in response.get_data(as_text=True)


def test_unpublished_detail_and_like_are_not_available(client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).is_published = False
        db.session.commit()
    assert client.get('/post/1').status_code == 404
    login(client, 'author')
    assert client.post('/post/1/like').status_code == 404
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_public_visibility.py -v

Expected: FAIL because existing public queries return all posts.

- [ ] **Step 3: Apply the shared predicate**

~~~python
def published_post_statement():
    return sa.select(Post).where(Post.is_published.is_(True))


def public_post_or_404(post_id):
    return db.first_or_404(
        published_post_statement().where(Post.id == post_id))
~~~

Use it in index, user, search, categories, detail, likes, and RSS. Resolve detail before comments/view counting. Change the category rail count to count published posts only.

- [ ] **Step 4: Verify green**

Run: pytest tests/test_public_visibility.py tests/test_post_interactions.py tests/test_post_views.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/routes.py app/templates/index.html tests/test_public_visibility.py tests/test_post_interactions.py tests/test_post_views.py
git commit -m "feat: hide unpublished posts from public routes"
~~~

### Task 4: Build Draft, Publish, Restore, and Retention Service

**Files:**
- Create: app/post_drafts.py
- Modify: tests/test_admin_posts.py

**Interfaces:**
- Produces DraftValues(title, body, category_id), save_draft, publish_draft, unpublish_post, discard_draft, restore_revision, snapshot_draft, and trim_all_post_revisions.
- Services enforce existing ownership and do not call commit.

- [ ] **Step 1: Write failing lifecycle tests**

~~~python
def test_draft_does_not_change_public_content_until_publish(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_draft(actor, post, DraftValues('New', 'private update', 1))
        assert post.body == '<p>safe</p>'
        publish_draft(actor, post.id)
        assert post.body == 'private update'
        assert post.draft is None


def test_restore_revision_updates_only_private_draft(application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        revision = PostRevision(post=post, title='Old', body='old', category_id=1)
        db.session.add(revision)
        db.session.commit()
        restore_revision(db.session.get(User, users['author']), post.id, revision.id)
        assert post.draft.body == 'old'
        assert post.body == '<p>safe</p>'
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_admin_posts.py -k "draft or revision or publish" -v

Expected: FAIL with missing lifecycle imports.

- [ ] **Step 3: Implement lifecycle**

~~~python
@dataclass(frozen=True)
class DraftValues:
    title: str
    body: str
    category_id: int | None


def save_draft(actor, post, values):
    if post is None:
        post = Post(title='', body='', body_format=BODY_FORMAT_MARKDOWN,
                    is_published=False, author=actor)
        db.session.add(post)
    ensure_can_edit(post, actor)
    if post.draft is None:
        post.draft = PostDraft(post=post, title='', body='')
    post.draft.title = values.title.strip()
    post.draft.body = prepare_content_source(values.body, post.body_format)
    post.draft.category_id = values.category_id
    post.draft.language = detect_language(values.body)
    return post
~~~

Publish validates nonblank title/body and valid category, copies draft fields into Post, sets is_published true, and removes the draft. Restore copies a post-owned revision into draft. Snapshot returns None with no draft; otherwise it creates one immutable snapshot and removes oldest records above get_site_settings().post_revision_limit. Unpublish hides Post only; discard removes draft only.

- [ ] **Step 4: Verify green**

Run: pytest tests/test_admin_posts.py -k "draft or revision or publish" -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/post_drafts.py tests/test_admin_posts.py
git commit -m "feat: add article draft lifecycle"
~~~

### Task 5: Add Admin APIs, Forms, and Timeline

**Files:**
- Modify: app/admin/posts.py, app/routes.py, app/forms.py
- Modify: app/templates/admin/posts/form.html, app/templates/admin/posts/list.html
- Modify: tests/test_admin_posts.py, tests/test_legacy_admin_routes.py

**Interfaces:**
- Produces POST /admin/posts/draft, PUT /admin/posts/{post_id}/draft, and POST /admin/posts/{post_id}/leave JSON endpoints.
- Produces POST actions publish, unpublish, discard-draft, and revisions/{revision_id}/restore.

- [ ] **Step 1: Write failing API tests**

~~~python
def test_author_autosaves_private_draft_then_publishes(client, users):
    login(client, 'author')
    saved = client.post('/admin/posts/draft', json={
        'title': 'Half written', 'body': 'draft text', 'category_id': 1})
    assert saved.status_code == 201
    post_id = saved.get_json()['post_id']
    assert client.get(f'/post/{post_id}').status_code == 404
    assert client.post(f'/admin/posts/{post_id}/publish').status_code == 302
    assert client.get(f'/post/{post_id}').status_code == 200


def test_leave_denies_other_author(client, users):
    login(client, 'other')
    assert client.post('/admin/posts/1/leave', json={
        'title': 'stolen', 'body': 'stolen', 'category_id': 1,
    }).status_code == 403
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_admin_posts.py -k "autosave or leave" -v

Expected: FAIL with 404 responses.

- [ ] **Step 3: Implement endpoints and draft-aware rendering**

~~~python
@bp.route('/posts/draft', methods=['POST'])
@login_required
def create_draft():
    post = save_draft(
        current_user, None, draft_values_from_json(request.get_json()))
    db.session.commit()
    return {'post_id': post.id, 'saved_at': post.draft.updated_at.isoformat()}, 201


@bp.route('/posts/<int:post_id>/leave', methods=['POST'])
@login_required
def leave_editor(post_id):
    post = owned_post_or_404(post_id, current_user)
    save_draft(current_user, post, draft_values_from_json(request.get_json()))
    revision = snapshot_draft(current_user, post.id)
    db.session.commit()
    return {'revision_created': revision is not None}
~~~

Validate payload types and category existence, while allowing empty title/body only for drafts. Render draft fields when available. Use state-specific controls: Publish; Publish update and Discard draft; or Unpublish. Render newest-first revision summaries and restore forms with CSRF. Update legacy POST /post/{post_id}/edit to save a draft then publish it in one transaction.

- [ ] **Step 4: Verify green**

Run: pytest tests/test_admin_posts.py tests/test_legacy_admin_routes.py tests/test_admin_access.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/admin/posts.py app/routes.py app/forms.py app/templates/admin/posts tests/test_admin_posts.py tests/test_legacy_admin_routes.py
git commit -m "feat: add article draft editor endpoints"
~~~

### Task 6: Add Browser Auto-Save and Leave Snapshot UX

**Files:**
- Modify: app/static/markdown-editor.js, app/templates/admin/posts/form.html
- Modify: tests/markdown_editor.test.js, tests/test_ui_pages.py

**Interfaces:**
- Consumes data-draft-url, data-leave-url, current post id, and the Flask-WTF token rendered in the editor.
- Produces window.articleDraftEditor with postId, dirty, saveTimer, and lastSavedPayload for deterministic test harnesses.
- Sends CSRF through X-CSRFToken; uses same-origin fetch keepalive for page leave.

- [ ] **Step 1: Write failing browser tests**

~~~javascript
test('debounces editor changes into one draft request', async () => {
  const harness = createDraftHarness();
  harness.execute();
  harness.changeBody('first');
  harness.changeBody('final');
  await harness.advance(1000);
  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].body.body, 'final');
  assert.equal(harness.status.textContent, '已保存');
});

test('page leave saves dirty content and requests one revision', async () => {
  const harness = createDraftHarness({ postId: 7 });
  harness.execute();
  harness.changeBody('snapshot');
  await harness.leavePage();
  assert.equal(harness.requests.at(-1).url, '/admin/posts/7/leave');
  assert.equal(harness.requests.at(-1).keepalive, true);
});
~~~

- [ ] **Step 2: Verify red**

Run: node --test tests/markdown_editor.test.js && pytest tests/test_ui_pages.py -k post_editor -v

Expected: FAIL because auto-save and timeline markup do not exist.

- [ ] **Step 3: Implement client save states**

~~~javascript
function scheduleDraftSave(state) {
  state.dirty = true;
  state.status.textContent = '保存中';
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveDraft(state), 1000);
}
~~~

Hook title, category, and EasyMDE change events to scheduleDraftSave. saveDraft sends Markdown source and only sets 已保存 after a successful response; failures retain dirty state and set 保存失败. On pagehide, compare with lastSavedPayload and send one keepalive leave request only when changed. Timeline restore POSTs CSRF then reloads server-rendered draft. Keep ordinary publish/unpublish/discard forms usable without JavaScript.

- [ ] **Step 4: Verify green**

Run: node --test tests/markdown_editor.test.js && pytest tests/test_ui_pages.py -k post_editor -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add app/static/markdown-editor.js app/templates/admin/posts/form.html tests/markdown_editor.test.js tests/test_ui_pages.py
git commit -m "feat: autosave article drafts and revisions"
~~~

### Task 7: Full Verification

**Files:**
- Modify only files required to correct a demonstrated regression.

- [ ] **Step 1: Run all tests**

Run: pytest && node --test tests/markdown_editor.test.js tests/theme.test.js

Expected: all Python and Node tests pass.

- [ ] **Step 2: Verify migration application**

Run: flask db upgrade

Expected: migration applies with settings, drafts, and revisions.

- [ ] **Step 3: Check final state**

Run: git diff --check && git status --short

Expected: no whitespace errors and no uncommitted application or test changes.

