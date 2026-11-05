# Markdown Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace CKEditor with a Markdown-first EasyMDE editor for articles and ordinary CMS pages while preserving existing HTML bodies without conversion.

**Architecture:** Add an explicit `body_format` discriminator to posts and pages, store source text in the existing `body` columns, and render both formats through one server-side sanitizer. Existing rows remain HTML; creation paths explicitly select Markdown, while edit paths preserve the stored format. EasyMDE progressively enhances only Markdown form fields.

**Tech Stack:** Flask 3.1, SQLAlchemy 2, Alembic, WTForms, Python-Markdown 3.8, Bleach 6.2, EasyMDE 2.20, DOMPurify 3.2, pytest, MySQL 8-compatible DDL.

## Global Constraints

- Do not rewrite or automatically convert any existing `post.body` or `page.body` value.
- Existing records migrate to `body_format='html'`; new articles and ordinary pages use `body_format='markdown'`.
- Unknown or null formats render defensively as HTML, but application writes are limited to `html` and `markdown`.
- Markdown output must pass through the same Bleach allowlist as HTML before it is marked safe.
- Comments, guestbook messages, profile fields, and private messages remain plain text.
- EasyMDE assets load only on opted-in editing forms; the textarea remains usable when JavaScript fails.
- No WYSIWYG mode and no rendered-HTML cache column.

## File Map

- Create `app/content.py`: format constants, source persistence policy, Markdown rendering, and sanitization boundary.
- Create `migrations/versions/b1d4e6f70819_add_content_body_formats.py`: reversible post/page format migration after `9c8e2f3a4b5d`.
- Create `app/static/markdown-editor.js`: opt-in EasyMDE initialization and theme synchronization.
- Modify `app/models.py`: mapped `body_format` columns on `Post` and `Page`.
- Modify `app/security.py`: keep the HTML allowlist and sanitizer; rendering moves to `app/content.py`.
- Modify `app/__init__.py`: register `render_content` and remove Flask-CKEditor initialization.
- Modify `app/forms.py` and `app/admin/forms.py`: use ordinary textareas instead of `CKEditorField`.
- Modify `app/admin/posts.py`, `app/pages.py`, `app/admin/pages.py`, and legacy routes in `app/routes.py`: select and preserve content format.
- Modify article/page/public/preview templates: render with format and opt forms into EasyMDE.
- Modify `app/templates/base.html`: remove global CKEditor and add overridable style/script asset blocks.
- Modify `app/static/style.css`: stable editor dimensions, mobile toolbar wrapping, legacy notice, and dark theme.
- Modify `requirements.txt`: add Python-Markdown and remove Flask-CKEditor.
- Modify focused tests in `tests/test_migrations.py`, `tests/test_security.py`, `tests/test_admin_posts.py`, `tests/test_pages.py`, and `tests/test_ui_pages.py`.

---

### Task 1: Persist The Content Format Without Rewriting Bodies

**Files:**
- Create: `migrations/versions/b1d4e6f70819_add_content_body_formats.py`
- Modify: `app/models.py`
- Modify: `tests/test_migrations.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Produces: `Post.body_format: str` and `Page.body_format: str`, with the stored values `html` or `markdown`.
- Produces: Alembic revision `b1d4e6f70819`, down revision `9c8e2f3a4b5d`.
- Consumes: existing `post.body` and `page.body` columns without mutating them.

- [ ] **Step 1: Write a migration test that snapshots bodies and checks HTML defaults**

Add a revision loader and a test that creates minimal `post` and `page` tables, inserts representative HTML, runs the upgrade, and asserts both the format and original bytes:

```python
MARKDOWN_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'b1d4e6f70819_add_content_body_formats.py')


def load_markdown_revision():
    spec = importlib.util.spec_from_file_location(
        'content_body_formats', MARKDOWN_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_content_format_migration_preserves_existing_bodies():
    revision = load_markdown_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table('post', metadata,
                     sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('body', sa.Text, nullable=False))
    pages = sa.Table('page', metadata,
                     sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('body', sa.Text))
    metadata.create_all(engine)
    post_body = '<table><tr><td>legacy</td></tr></table>'
    page_body = '<p data-old="yes">legacy page</p>'

    with engine.begin() as connection:
        connection.execute(posts.insert().values(body=post_body))
        connection.execute(pages.insert().values(body=page_body))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            assert connection.execute(sa.text(
                'SELECT body, body_format FROM post')).mappings().one() == {
                    'body': post_body, 'body_format': 'html'}
            assert connection.execute(sa.text(
                'SELECT body, body_format FROM page')).mappings().one() == {
                    'body': page_body, 'body_format': 'html'}
            revision.downgrade()

        assert 'body_format' not in {
            column['name'] for column in sa.inspect(connection).get_columns('post')}
```

- [ ] **Step 2: Run the focused test and verify the revision is missing**

Run: `pytest tests/test_migrations.py::test_content_format_migration_preserves_existing_bodies -v`

Expected: FAIL because `b1d4e6f70819_add_content_body_formats.py` does not exist.

- [ ] **Step 3: Implement the staged Alembic migration**

Create the revision with a server default that makes existing and older-writer rows safe:

```python
"""add content body formats"""
from alembic import op
import sqlalchemy as sa

revision = 'b1d4e6f70819'
down_revision = '9c8e2f3a4b5d'
branch_labels = None
depends_on = None


def upgrade():
    for table_name in ('post', 'page'):
        op.add_column(table_name, sa.Column(
            'body_format', sa.String(length=20), nullable=False,
            server_default=sa.text("'html'")))


def downgrade():
    op.drop_column('page', 'body_format')
    op.drop_column('post', 'body_format')
```

Use direct non-null additions because both SQLite and MySQL backfill the constant server default atomically; the test proves body preservation. Do not issue any `UPDATE body` statement.

- [ ] **Step 4: Map the new fields with backward-compatible defaults**

Add the same mapping to `Post` and `Page`:

```python
body_format: so.Mapped[str] = so.mapped_column(
    sa.String(20), nullable=False, default='html',
    server_default=sa.text("'html'"))
```

The Python default remains HTML because tests, scripts, and older internal callers that construct models with HTML must not silently change meaning. HTTP creation paths will explicitly choose Markdown in Task 3.

- [ ] **Step 5: Run migration and model tests**

Run: `pytest tests/test_migrations.py tests/test_models.py -v`

Expected: PASS, including exact preservation of both legacy bodies.

- [ ] **Step 6: Commit the persistence boundary**

```bash
git add migrations/versions/b1d4e6f70819_add_content_body_formats.py app/models.py tests/test_migrations.py
git commit -m "feat: persist article and page body formats"
```

---

### Task 2: Render Markdown And Legacy HTML Through One Safety Boundary

**Files:**
- Create: `app/content.py`
- Modify: `app/__init__.py`
- Modify: `app/templates/post/post.html`
- Modify: `app/templates/page/content.html`
- Modify: `app/templates/admin/pages/preview.html`
- Modify: `app/routes.py`
- Modify: `requirements.txt`
- Modify: `tests/test_security.py`
- Modify: `tests/test_pages.py`
- Test: `tests/test_security.py`, `tests/test_pages.py`

**Interfaces:**
- Consumes: `sanitize_html(value: str) -> str` from `app.security`.
- Produces: `BODY_FORMAT_HTML`, `BODY_FORMAT_MARKDOWN`, and `CONTENT_FORMATS`.
- Produces: `render_content(value: str | None, body_format: str | None) -> Markup`.
- Produces: Jinja filter usage `body|render_content(body_format)`.

- [ ] **Step 1: Add failing rendering and sanitization tests**

Add tests that prove standard Markdown output and unsafe raw HTML share one sanitizer:

```python
from app.content import render_content


def test_render_content_supports_markdown_and_sanitizes_raw_html(application):
    with application.app_context():
        rendered = str(render_content(
            '# Heading\n\n- one\n- two\n\n'
            '[safe link](https://example.com)\n\n'
            '```python\nprint("code")\n```\n\n'
            '| A | B |\n| - | - |\n| 1 | 2 |\n\n'
            '<img src="javascript:alert(1)" onerror="alert(2)">',
            'markdown'))

    assert '<h1>Heading</h1>' in rendered
    assert '<li>one</li>' in rendered
    assert 'href="https://example.com"' in rendered
    assert '<pre><code' in rendered
    assert '<table>' in rendered
    assert 'javascript:' not in rendered
    assert 'onerror' not in rendered


def test_render_content_defaults_unknown_formats_to_legacy_html(application):
    with application.app_context():
        rendered = str(render_content('<strong>legacy</strong>', 'unexpected'))

    assert rendered == '<strong>legacy</strong>'
```

Add route tests with one Markdown post and one Markdown page, asserting rendered headings are present and source markers such as `# Heading` are absent.

- [ ] **Step 2: Run the focused tests and verify the module is missing**

Run: `pytest tests/test_security.py tests/test_pages.py -k 'render_content or markdown' -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.content'`.

- [ ] **Step 3: Add the pinned server renderer dependency**

In `requirements.txt`, add:

```text
Markdown==3.8.2
```

Install with the project environment's normal dependency command before rerunning tests.

- [ ] **Step 4: Implement the renderer**

Create `app/content.py`:

```python
from flask import current_app
from markdown import markdown
from markupsafe import Markup, escape

from app.security import sanitize_html

BODY_FORMAT_HTML = 'html'
BODY_FORMAT_MARKDOWN = 'markdown'
CONTENT_FORMATS = frozenset({BODY_FORMAT_HTML, BODY_FORMAT_MARKDOWN})


def normalize_body_format(value):
    return value if value in CONTENT_FORMATS else BODY_FORMAT_HTML


def render_content(value, body_format):
    source = value or ''
    if normalize_body_format(body_format) == BODY_FORMAT_MARKDOWN:
        try:
            source = markdown(source, extensions=['extra', 'sane_lists'])
        except Exception:
            current_app.logger.exception('Markdown rendering failed')
            return Markup(escape(value or ''))
    return Markup(sanitize_html(source))
```

The broad exception is intentional at the public rendering boundary: it logs an unexpected renderer failure and returns escaped source rather than unsafe or a 500 response.

- [ ] **Step 5: Register and consume the filter everywhere full bodies render**

In `app/__init__.py`, register:

```python
from app.content import render_content
app.jinja_env.filters['render_content'] = render_content
```

Update article, public page, and admin preview templates:

```jinja2
{{ post.body|render_content(post.body_format) }}
{{ page.body|render_content(page.body_format) }}
```

In `rss_feed()`, replace raw `post.body` with:

```python
fe.description(str(render_content(post.body, post.body_format)))
```

Keep `safe_html` registered for legacy guestbook and message call sites that are outside this feature.

- [ ] **Step 6: Run renderer, route, and RSS tests**

Run: `pytest tests/test_security.py tests/test_pages.py -v`

Expected: PASS with rendered Markdown and sanitized dangerous content.

- [ ] **Step 7: Commit the rendering boundary**

```bash
git add app/content.py app/__init__.py app/templates/post/post.html app/templates/page/content.html app/templates/admin/pages/preview.html app/routes.py requirements.txt tests/test_security.py tests/test_pages.py
git commit -m "feat: render markdown through the html sanitizer"
```

---

### Task 3: Store Markdown For New Content And Preserve Legacy Edit Formats

**Files:**
- Modify: `app/content.py`
- Modify: `app/forms.py`
- Modify: `app/admin/forms.py`
- Modify: `app/admin/posts.py`
- Modify: `app/admin/pages.py`
- Modify: `app/pages.py`
- Modify: `app/routes.py`
- Modify: `tests/test_admin_posts.py`
- Modify: `tests/test_pages.py`
- Test: `tests/test_admin_posts.py`, `tests/test_pages.py`

**Interfaces:**
- Consumes: format constants and `normalize_body_format()` from Task 2.
- Produces: `prepare_content_source(value: str | None, body_format: str | None) -> str`.
- Preserves: existing HTML format on every edit path, including compatibility POST routes.

- [ ] **Step 1: Write failing new-content and legacy-edit tests**

Extend the article CRUD test to submit actual Markdown and assert raw source plus format:

```python
created = client.post('/admin/posts/new', data={
    'title': 'Markdown article',
    'category': str(category_id),
    'post': '# Stored as source',
})
assert created.status_code == 302
with application.app_context():
    post = db.session.scalar(sa.select(Post).where(
        Post.title == 'Markdown article'))
    assert post.body == '# Stored as source'
    assert post.body_format == 'markdown'
```

Add a separate test that creates `Post(body='<p>Legacy</p>', body_format='html')`, edits it through `/admin/posts/<id>/edit`, and asserts the format stays HTML and an injected script is sanitized. Add equivalent page create/edit assertions, including a legacy page that keeps `html`.

- [ ] **Step 2: Run the focused tests and verify new rows are still sanitized HTML**

Run: `pytest tests/test_admin_posts.py tests/test_pages.py -k 'markdown or legacy_format' -v`

Expected: FAIL because creation paths do not select Markdown and still sanitize submitted source.

- [ ] **Step 3: Add the source persistence helper**

In `app/content.py`:

```python
def prepare_content_source(value, body_format):
    source = value or ''
    if normalize_body_format(body_format) == BODY_FORMAT_MARKDOWN:
        return source
    return sanitize_html(source)
```

- [ ] **Step 4: Replace CKEditor field classes with textareas**

Remove `flask_ckeditor` imports from both form modules and declare:

```python
post = TextAreaField(_l('Say something'), validators=[DataRequired()])
body = TextAreaField('正文')
```

Change `AboutForm.body` to `TextAreaField` as well. `/about/edit` is a compatibility route whose GET redirects to the page CMS, but retaining this small form preserves CSRF and required-field validation for old POST clients.

Do not change `CommentForm` or `PostCommentForm` to Markdown. `CommentForm.body` becomes a standard `TextAreaField` if it still uses `CKEditorField`.

- [ ] **Step 5: Update article creation and every article edit path**

In `app/admin/posts.py`, new articles explicitly select Markdown:

```python
post = Post(
    title=form.title.data.strip(),
    body=prepare_content_source(form.post.data, BODY_FORMAT_MARKDOWN),
    body_format=BODY_FORMAT_MARKDOWN,
    author=current_user,
    language=detect_language(form.post.data),
    category_id=form.category.data,
)
```

For edits, preserve the record discriminator:

```python
post.body = prepare_content_source(form.post.data, post.body_format)
```

Make the same replacement in the legacy `/post/<id>/edit` POST route so it cannot reinterpret a legacy record or sanitize away Markdown syntax.

- [ ] **Step 6: Update page creation, `save_page()`, and About compatibility**

Construct new ordinary pages with `body_format=BODY_FORMAT_MARKDOWN`. In
`save_page()`, preserve or accept the explicit discriminator and store source by
format:

```python
if kind == PAGE_CONTENT:
    page.body_format = normalize_body_format(
        values.get('body_format', page.body_format))
    page.body = prepare_content_source(
        values.get('body', page.body), page.body_format)
else:
    page.body = None
```

Module pages keep their existing format default because they have no body. The
legacy About POST calls `save_page()` without a new format and therefore
preserves the page's current value.

- [ ] **Step 7: Run all persistence and authorization tests**

Run: `pytest tests/test_admin_posts.py tests/test_pages.py tests/test_roles.py tests/test_security.py -v`

Expected: PASS; ownership and admin boundaries remain unchanged.

- [ ] **Step 8: Commit the save-path compatibility work**

```bash
git add app/content.py app/forms.py app/admin/forms.py app/admin/posts.py app/admin/pages.py app/pages.py app/routes.py tests/test_admin_posts.py tests/test_pages.py
git commit -m "feat: store new content as markdown source"
```

---

### Task 4: Replace CKEditor With An Opt-In EasyMDE Interface

**Files:**
- Create: `app/static/markdown-editor.js`
- Modify: `app/templates/base.html`
- Modify: `app/templates/admin/posts/form.html`
- Modify: `app/templates/admin/pages/form.html`
- Modify: `app/templates/about/edit_about.html` only if its ordinary textarea needs cleanup after the CKEditor field removal.
- Modify: `app/static/style.css`
- Modify: `app/routes.py`
- Modify: `app/__init__.py`
- Modify: `requirements.txt`
- Modify: `tests/test_ui_pages.py`
- Modify: `tests/test_security.py`
- Test: `tests/test_ui_pages.py`, `tests/test_security.py`

**Interfaces:**
- Consumes: `body_format` on form records from Tasks 1 and 3.
- Produces: textarea opt-in `data-markdown-editor`, initialized only for Markdown.
- Produces: read-only presentation flag `legacy_html` passed by article/page form views.
- Produces: optional template blocks `page_styles` and `page_scripts` in `base.html`.

- [ ] **Step 1: Replace the obsolete CKEditor UI test with failing asset-scope tests**

Replace `test_ckeditor_instances_disable_the_insecure_version_warning` with:

```python
def test_markdown_editor_assets_are_scoped_to_markdown_admin_forms(client, users):
    client.post('/login', data={'username': 'admin', 'password': 'password'})

    editor = client.get('/admin/pages/new').get_data(as_text=True)
    public = client.get('/').get_data(as_text=True)

    assert 'data-markdown-editor' in editor
    assert 'easymde@2.20.0' in editor
    assert 'dompurify@3.2.6' in editor
    assert 'markdown-editor.js' in editor
    assert 'easymde@2.20.0' not in public
    assert 'CKEDITOR' not in editor + public
```

Add a legacy article/page form test that asserts `旧版 HTML 内容` is visible, `data-markdown-editor` is absent, and the original HTML source is present in the textarea. Add assertions that `/comment` and an article comment form contain no Markdown editor attribute.

- [ ] **Step 2: Run UI tests and verify they fail against CKEditor**

Run: `pytest tests/test_ui_pages.py tests/test_security.py -k 'editor or comment' -v`

Expected: FAIL because CKEditor is global and no Markdown opt-in exists.

- [ ] **Step 3: Add scoped template asset blocks and explicit content forms**

In `base.html`, add empty blocks after the site stylesheet and before the closing body scripts:

```jinja2
{% block page_styles %}{% endblock %}
{# Existing body and global scripts remain between these two extension points. #}
{% block page_scripts %}{% endblock %}
```

Remove the global CKEditor script and initializer. Rewrite the article quick form
as explicit WTForms fields so the body textarea can receive
`data-markdown-editor` only when `not legacy_html`. Apply the same rule to the
ordinary page form:

```jinja2
{% if legacy_html %}
<div class="admin-notice">旧版 HTML 内容：保存时会继续按 HTML 处理，不会自动转换。</div>
{% endif %}
{{ form.body(
    class="form-control" + (' is-invalid' if form.body.errors else ''),
    rows="18",
    **({'data-markdown-editor': ''} if not legacy_html else {})
) }}
```

If Jinja keyword expansion is not accepted by the installed version, use two
explicit branches that render the field with and without
`data_markdown_editor=''`; do not add a global textarea selector.

Override the asset blocks only in the article and page form templates, pinned to
EasyMDE `2.20.0`:

```jinja2
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/easymde@2.20.0/dist/easymde.min.css">
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/easymde@2.20.0/dist/easymde.min.js"></script>
<script src="{{ url_for('static', filename='markdown-editor.js') }}"></script>
```

- [ ] **Step 4: Implement progressive EasyMDE initialization**

Create `app/static/markdown-editor.js`:

```javascript
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('textarea[data-markdown-editor]').forEach((field) => {
    if (typeof EasyMDE === 'undefined' || typeof DOMPurify === 'undefined') return;
    const editor = new EasyMDE({
      element: field,
      autofocus: false,
      forceSync: true,
      spellChecker: false,
      status: false,
      minHeight: '320px',
      renderingConfig: {
        singleLineBreaks: false,
        sanitizerFunction: (html) => DOMPurify.sanitize(html),
      },
      toolbar: [
        'bold', 'italic', 'heading', '|', 'quote', 'unordered-list',
        'ordered-list', 'code', 'link', 'image', 'table', '|',
        'preview', 'side-by-side', 'fullscreen', '|', 'guide',
      ],
    });
    field.markdownEditor = editor;
  });
});
```

`forceSync` guarantees the submitted textarea contains the latest source.
DOMPurify prevents raw HTML from executing inside the authoring preview; this is
in addition to, not a replacement for, server sanitization. The early return
preserves a functional textarea when either CDN dependency fails.

- [ ] **Step 5: Add responsive and dark-theme editor styles**

Append scoped rules to `app/static/style.css`:

```css
.admin-form .EasyMDEContainer { min-width: 0; }
.admin-form .CodeMirror { min-height: 320px; color: var(--text-primary); background: var(--surface); }
.admin-form .editor-toolbar { display: flex; flex-wrap: wrap; border-color: var(--border); }
.admin-form .editor-toolbar button { flex: 0 0 30px; color: var(--text-primary); }
.admin-form .editor-preview { color: var(--text-primary); background: var(--page-bg); }
[data-theme="dark"] .admin-form .CodeMirror-cursor { border-left-color: var(--text-primary); }

@media (max-width: 640px) {
  .admin-form .CodeMirror { min-height: 260px; }
  .admin-form .editor-toolbar { padding: 6px; }
}
```

Use the repository's actual surface variable names when implementing; do not
introduce a duplicate palette.

- [ ] **Step 6: Remove Flask-CKEditor without removing file-serving compatibility**

Delete CKEditor imports/initialization and remove `Flask-CKEditor==1.0.0` from
`requirements.txt`. Keep `/files/<filename>` so existing embedded images continue
to render. Replace `upload_success`/`upload_fail` in `/upload` with Flask JSON
responses if the endpoint remains covered by security tests:

```python
return {'uploaded': 1, 'url': url}, 200
return {'uploaded': 0, 'error': {'message': 'Image only!'}}, 400
```

Preserve authentication, signature validation, randomized filenames, and upload
directory containment. Adjust existing tests to assert JSON and the intentional
400 status. Do not expose upload controls in EasyMDE in this task; its image
button inserts Markdown image URLs.

- [ ] **Step 7: Verify dependency and repository cleanup**

Run: `rg -n "CKEditor|ckeditor|flask_ckeditor|Flask-CKEditor" app requirements.txt tests`

Expected: no matches.

Run: `pytest tests/test_ui_pages.py tests/test_security.py tests/test_admin_posts.py tests/test_pages.py -v`

Expected: PASS, including scoped assets, fallback textarea, and plain-text comments.

- [ ] **Step 8: Commit the editor replacement**

```bash
git add app/static/markdown-editor.js app/templates/base.html app/templates/admin/posts/form.html app/templates/admin/pages/form.html app/static/style.css app/routes.py app/__init__.py requirements.txt tests/test_ui_pages.py tests/test_security.py
git commit -m "feat: replace ckeditor with markdown editing"
```

---

### Task 5: Full Regression, MySQL Migration Rehearsal, And Browser QA

**Files:**
- Modify only files required by failures found in this task.
- Verify: all application, migration, template, stylesheet, and dependency files changed in Tasks 1-4.

**Interfaces:**
- Consumes: Alembic revision `b1d4e6f70819` and all content/editor interfaces from Tasks 1-4.
- Produces: evidence that the complete feature works on SQLite tests, MySQL migration rehearsal, desktop/mobile layouts, and light/dark themes.

- [ ] **Step 1: Run static and complete automated checks**

Run:

```bash
git diff --check
pytest -q
```

Expected: no whitespace errors and all tests pass (baseline before this feature was 192 tests).

- [ ] **Step 2: Verify migration graph and generated schema**

Run:

```bash
flask db heads
flask db current
```

Expected: exactly one head, `b1d4e6f70819`; the current development database may still report the prior revision until the rehearsal upgrade.

- [ ] **Step 3: Rehearse upgrade and downgrade on a disposable MySQL copy**

Create a new explicitly named scratch database; do not modify or delete the two retained `flog_admin_cms_scratch_*` databases. Import the current production backup or schema into the new scratch database, capture checksums for all `post.id/body` and `page.id/body` pairs, and export its concrete SQLAlchemy URL as the task-specific `MARKDOWN_SCRATCH_DATABASE_URL`. Verify `SELECT DATABASE()` returns the newly created `flog_markdown_scratch_YYYYMMDD_HHMMSS` name before running:

```bash
DATABASE_URL="$MARKDOWN_SCRATCH_DATABASE_URL" flask db upgrade
```

Query `alembic_version`, both `body_format` columns, and the before/after body checksums. Expected: revision `b1d4e6f70819`, every pre-existing format is `html`, and all body checksums are identical. Run `flask db downgrade 9c8e2f3a4b5d`, verify both added columns disappear, then upgrade again and recheck.

- [ ] **Step 4: Start the application and perform browser QA**

Start the development server on an unused local port. Check at desktop
`1440x900` and mobile `390x844`:

- new article and ordinary page show EasyMDE and accept headings, lists, links,
  fenced code, tables, and long titles;
- preview, side-by-side, and fullscreen controls work without resizing the
  surrounding admin layout;
- validation errors retain the submitted Markdown source;
- a legacy HTML article/page shows the notice, editable HTML source, and no
  Markdown toolbar;
- dark-mode editor, preview, toolbar focus, and cursor remain legible;
- mobile toolbar wraps, sidebar drawer works, and no horizontal page overflow
  occurs;
- public article/page output contains no admin controls;
- comment and guestbook forms remain ordinary textareas;
- with the EasyMDE request blocked, the underlying textarea remains editable and
  submits successfully.

Capture screenshots for desktop Markdown editing, mobile editing, legacy notice,
validation error, and dark mode.

- [ ] **Step 5: Inspect browser console and rendered safety cases**

Expected: no JavaScript exceptions, blocked mixed content, missing asset errors,
or accessibility-related duplicate IDs. Submit Markdown containing a script,
event handler, and `javascript:` link in the scratch environment and confirm none
appear executable in the public DOM.

- [ ] **Step 6: Fix only verified failures and rerun affected checks**

For each failure, first add or tighten the smallest reproducing automated test,
run it to see the failure, apply the minimal fix, and rerun the focused test.
After all fixes, rerun `pytest -q` and `git diff --check`.

- [ ] **Step 7: Request final code review**

Use the `requesting-code-review` skill to review the complete diff against
`docs/superpowers/specs/2026-08-21-markdown-editor-design.md`. Resolve all
correctness, security, migration, and regression findings, then repeat the full
suite.

- [ ] **Step 8: Commit any verification fixes**

If Task 5 required code changes:

```bash
git add app/content.py app/routes.py app/static/markdown-editor.js app/static/style.css app/templates/base.html app/templates/admin/posts/form.html app/templates/admin/pages/form.html tests/test_admin_posts.py tests/test_pages.py tests/test_security.py tests/test_ui_pages.py
git commit -m "fix: address markdown editor verification findings"
```

If no files changed, do not create an empty commit.
