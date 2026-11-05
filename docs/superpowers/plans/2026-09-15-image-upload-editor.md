# Article Editor Image Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a consistent image-writing workflow to Markdown editors: toolbar selection, drag-and-drop, and clipboard paste upload images and insert Markdown at the current cursor.

**Architecture:** Keep the existing authenticated `/upload` endpoint and implement a client-side upload coordinator in `app/static/markdown-editor.js`. Every initialized EasyMDE instance gets one coordinator that owns the hidden file input, drop/paste listeners, upload status, and cursor bookmark; successful responses insert Markdown and naturally trigger existing draft autosave. Templates provide the upload URL and CSRF token through the nearest form, while editor-scoped CSS supplies accessible light/dark drag and status affordances.

**Tech Stack:** Flask/Jinja templates, existing `/upload` route, EasyMDE 2.20.0, CodeMirror selection/bookmark APIs, vanilla JavaScript, Node `node:test`, pytest.

## Global Constraints

- Use the existing `/upload` endpoint and `post` multipart field; do not create a media-library model or route.
- Server-side authentication, CSRF, signature validation, randomized filenames, and `/files/<filename>` serving remain authoritative.
- Legacy HTML editors, comments, guestbook messages, and other plain-text fields must not initialize the upload workflow.
- Insert source as `![图片描述](/files/<random-name>.<ext>)`; default description is `图片`.
- Editor JavaScript is progressive enhancement: a failed asset load leaves the underlying textarea and manual Markdown workflow usable.
- Existing EasyMDE URL insertion remains available alongside the new upload action.
- Preserve current draft autosave behavior; inserted Markdown must arrive through the existing CodeMirror `change` listener.

---

### Task 1: Add failing browser tests for the upload coordinator

**Files:**
- Modify: `tests/markdown_editor.test.js`
- Test: `tests/markdown_editor.test.js`

**Interfaces:**
- Consumes: current `markdown-editor.js` DOMContentLoaded/EasyMDE initialization and draft harness.
- Produces: deterministic harness coverage for `upload-image`, `change`, `drop`, and `paste` behavior that Task 2 must satisfy.

- [ ] **Step 1: Extend the EasyMDE test harness with editor and DOM seams**

Add fake CodeMirror methods used by the coordinator (`getWrapperElement`,
`getDoc`, `getCursor`, `setSelection`, `replaceRange`) and fake DOM elements that
record listeners, attributes, children, clicks, and selected files. Add a fake
`FormData` that records `append('post', file)`, and a fake `fetch` returning the
existing success shape `{uploaded: 1, url: '/files/abc.png'}` or a non-OK error.

The harness must expose the wrapper's `drop`/`paste` listeners, the generated
file input's `change` listener, the toolbar custom action, the editor source,
and the live status element so tests can assert behavior without a browser.

- [ ] **Step 2: Write failing tests for toolbar selection and cursor insertion**

Cover selecting one image through the generated file input: the request uses
`POST /upload`, sends the file under `post`, and inserts exactly
`![图片](/files/abc.png)` through `replaceRange` at the bookmarked cursor.
Assert the status transitions from uploading to success and the change listener
is invoked once.

- [ ] **Step 3: Write failing tests for drop, paste, and multiple files**

Assert that image drops call `preventDefault`, upload only image files from a
mixed drop, preserve file order, and insert multiple images separated by a
blank line. Assert that clipboard image blobs use the same path and ordinary
text paste does not call `preventDefault` or upload.

- [ ] **Step 4: Write failing tests for errors and editor boundaries**

Assert a rejected upload leaves the source unchanged, reports a safe error in
the `aria-live` status, and does not invoke the editor change callback. For a
multi-file batch, a later failure must also leave the document unchanged. Add a
regression assertion that a legacy/no-editor harness has no upload input or
listeners and that the existing stylesheet-failure tests still pass.

- [ ] **Step 5: Run the focused tests and verify they fail for the missing behavior**

Run:

~~~bash
node --test tests/markdown_editor.test.js
~~~

Expected: existing tests pass, and each new upload test fails because the
coordinator and upload toolbar action do not exist yet.

- [ ] **Step 6: Commit the test-only change**

~~~bash
git add tests/markdown_editor.test.js
git commit -m "test: specify markdown editor image uploads"
~~~

### Task 2: Implement the shared image upload coordinator

**Files:**
- Modify: `app/static/markdown-editor.js`
- Test: `tests/markdown_editor.test.js`

**Interfaces:**
- Consumes: `textarea[data-markdown-editor]`, the nearest form's hidden `csrf_token`, and `data-image-upload-url`.
- Produces: one coordinator per EasyMDE instance with toolbar, input, drop, paste, status, and upload behavior; no public API is required outside the editor instance.

- [ ] **Step 1: Add editor initialization hooks for upload metadata**

When constructing EasyMDE, add a custom toolbar item named `upload-image`
next to the existing `image` item. After construction call
`initializeImageUpload(editor, field)` only once per field. Resolve the upload
URL from `field.form.dataset.imageUploadUrl` and the CSRF token from
`field.form.querySelector('input[name="csrf_token"]')?.value`; if either is
missing, keep the normal editor and URL-image action but skip upload controls.

- [ ] **Step 2: Implement the hidden file input and accessible status**

Create an `input[type=file]` with `accept="image/gif,image/jpeg,image/png"`,
`multiple = true`, and a visually hidden class; append it beside the editor
wrapper. Add a generated status node with `role="status"`,
`aria-live="polite"`, and `hidden` state. The custom toolbar action calls
`input.click()`, and the input change handler passes `Array.from(input.files)`
to the shared upload function before clearing `input.value`.

- [ ] **Step 3: Implement cursor-safe asynchronous insertion**

Before the first upload, capture `doc = editor.codemirror.getDoc()` and a
CodeMirror bookmark from `editor.codemirror.getCursor()` with
`doc.setBookmark(cursor, {insertLeft: true})`. Collect each successful response
as `![图片](${payload.url})` without touching the document. After the entire
batch succeeds, join snippets with `\n\n` and call
`doc.replaceRange(text, bookmark.find())` exactly once. Clear the bookmark
after the batch and let CodeMirror fire the existing change event. If any
response is malformed or non-OK, throw a user-safe error, clear the bookmark,
and leave the document byte-for-byte unchanged.

- [ ] **Step 4: Implement upload requests and status lifecycle**

For each file, create `FormData`, append the file under `post`, and call:

~~~js
fetch(uploadUrl, {
  method: 'POST',
  headers: {'X-CSRFToken': csrfToken},
  body: formData,
})
~~~

Accept only `{uploaded: 1, url: string}`. Upload files sequentially so order
is deterministic, show `正在上传 N 张图片…`, then `图片已插入` on success. On
network, auth, CSRF, non-OK, or malformed responses set `上传失败：<safe message>`
and keep source unchanged. Do not display server HTML or exception text.

- [ ] **Step 5: Wire drag-and-drop and clipboard paste**

Attach listeners to `editor.codemirror.getWrapperElement()`. On `dragover`,
prevent default only when image files are present and add a
`markdown-editor--dragging` class; remove it on `dragleave`/`drop`. On `drop`,
upload image files in `dataTransfer.files`. On `paste`, collect image blobs from
`clipboardData.items` with `kind === 'file'` and an `image/*` type; prevent the
default only when at least one image exists. Text-only paste remains untouched.

- [ ] **Step 6: Run focused tests and fix until green**

Run:

~~~bash
node --test tests/markdown_editor.test.js
~~~

Expected: all existing draft/publication tests and all new upload coordinator
tests pass.

- [ ] **Step 7: Commit the coordinator implementation**

~~~bash
git add app/static/markdown-editor.js tests/markdown_editor.test.js
git commit -m "feat: upload images from markdown editor"
~~~

### Task 3: Add template metadata and editor-scoped visual affordances

**Files:**
- Modify: `app/templates/admin/posts/form.html`
- Modify: `app/templates/admin/pages/form.html`
- Modify: `app/static/style.css`
- Test: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: Task 2's `field.form.dataset.imageUploadUrl` and nearest hidden CSRF input lookup.
- Produces: Markdown forms that can upload to the correct route and clear visual feedback for drag/upload state.

- [ ] **Step 1: Add the upload URL to Markdown forms only**

Add `data-image-upload-url="{{ url_for('upload') }}"` to the article form and
to the ordinary content-page form. Do not add it to legacy HTML or module forms.
Keep existing `csrf_token()` hidden inputs unchanged.

- [ ] **Step 2: Add drag and status styles**

Add editor-scoped rules such as:

```css
.admin-form .markdown-editor--dragging { outline: 2px dashed var(--accent); outline-offset: 4px; }
.admin-form .markdown-upload-status { color: var(--text-secondary); font-size: 12px; margin-top: 6px; }
.admin-form .markdown-upload-status[data-state="error"] { color: var(--danger); }
```

Use existing theme variables, maintain visible focus, and ensure the rules do
not create horizontal overflow on narrow screens or affect public article HTML.

- [ ] **Step 3: Add server-rendered UI assertions**

In `tests/test_ui_pages.py`, assert new Markdown article and content-page forms
contain `data-image-upload-url` and the Markdown editor script, while legacy
HTML forms and public/comment pages contain neither upload metadata nor editor
initialization attributes.

- [ ] **Step 4: Run UI and JavaScript tests**

Run:

```bash
node --test tests/markdown_editor.test.js
pytest -q tests/test_ui_pages.py
```

Expected: both suites pass with the new metadata and styles.

- [ ] **Step 5: Commit template and style changes**

```bash
git add app/templates/admin/posts/form.html app/templates/admin/pages/form.html app/static/style.css tests/test_ui_pages.py
git commit -m "feat: add markdown image upload affordances"
```

### Task 4: Run full verification and perform manual interaction checks

**Files:**
- Modify: none unless verification exposes a regression.
- Test: `tests/test_security.py`, `tests/markdown_editor.test.js`, `tests/test_ui_pages.py`, full test suite.

**Interfaces:**
- Consumes: Tasks 1–3's upload coordinator, form metadata, and styles.
- Produces: verified feature behavior and a clean handoff with evidence.

- [ ] **Step 1: Run upload/security regression tests**

Run:

```bash
pytest -q tests/test_security.py tests/test_ui_pages.py
```

Expected: authenticated upload success, unauthenticated redirect, fake-image
rejection, file serving, and editor-boundary assertions all pass.

- [ ] **Step 2: Run the complete automated suite**

Run:

```bash
node --test tests/*.test.js
pytest -q
```

Expected: no failures, with any unrelated pre-existing failure recorded before
claiming completion.

- [ ] **Step 3: Manually verify the authoring flow**

Open a new Markdown article and content page in a logged-in browser and verify:

1. toolbar upload opens an image picker and inserts at the cursor;
2. dropping and pasting screenshots insert images in order;
3. the first `图片` alt text can be replaced immediately;
4. upload status is readable in light and dark themes and on a narrow viewport;
5. a rejected file leaves source intact and shows an error;
6. autosave marks the article dirty and persists inserted Markdown;
7. legacy HTML and public pages show no upload controls.

- [ ] **Step 4: Inspect the final diff and report verification evidence**

Run `git diff --check` and `git status --short`, confirm no generated uploads or
unrelated files are included, and summarize the exact commands and outcomes.

- [ ] **Step 5: Commit any verification-only fixes**

```bash
git add app/static/markdown-editor.js app/templates/admin/posts/form.html app/templates/admin/pages/form.html app/static/style.css tests/markdown_editor.test.js tests/test_ui_pages.py
git commit -m "fix: polish markdown image upload verification findings"
```
