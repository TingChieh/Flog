# Image Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-11-05-image-library-design.md`.

**Goal:** Add an `image` table, an admin image library (browse, upload, edit name/note, usage tracking, delete) and an editor picker.

**Architecture:** `app/images.py` holds model-independent helpers (upload, sync, usage, visibility); routes live in `app/admin/images.py`; templates in `app/templates/admin/images/`; the editor gets a custom Vditor toolbar item in `markdown-editor.js`.

**Tech Stack:** Flask, SQLAlchemy 2, Alembic, Flask-WTF, pytest + lxml, node:test with `vm`.

## Global Constraints

- Tests: `.venv/bin/python -m pytest -q` (baseline 546 passing) and `node --test tests/*.test.js` (baseline 50). Fixtures in `tests/conftest.py`: `application`, `client`, `users` (ids `admin`, `author`, `other`, `post`), `login(client, name)`; `UPLOAD_FOLDER` is a per-test tmp dir.
- Admin routes use `@login_required`; members only see own images; CSRF on POST; Chinese UI text; DB-failure flash `'…失败，请重试。'`.
- Image rules unchanged: gif/jpg/jpeg/png with matching magic bytes, uuid filenames, 20 MB request limit.
- Filename pattern everywhere: `^[0-9a-f]{32}\.(png|jpe?g|gif)$`; usage regex `/files/([0-9a-f]{32}\.(?:png|jpe?g|gif))`.
- Commit after each task.

---

### Task 1: `Image` model, migration, shared upload helper, `/upload` uses it

**Files:** Create `app/images.py`, `migrations/versions/d5e7b9c1f203_add_image_table.py`, `tests/test_images.py`; Modify `app/models.py` (add `Image`), `app/routes.py` (`/upload`), `tests/test_migrations.py` (head + new test).

**Interfaces:** Produces `Image` model; `ImageUploadError(ValueError)`; `save_uploaded_image(file, user) -> Image`; `IMAGE_NAME_RE`, `USAGE_RE`.

- [ ] Write failing tests in `tests/test_images.py`: (a) POST `/upload` with a tiny PNG (`b'\x89PNG\r\n\x1a\n' + b'0'*20`) as `post` creates one `Image` with `original_name`, `size`, `user_id`, `title` = stem, and the response JSON is `{'uploaded': 1, 'filename': '', 'url': '/files/<name>'}`; (b) a text file named `x.png` is rejected with 400 `{'uploaded': 0, 'error': {'message': 'Image only!'}}` and creates no row; (c) missing file → 400 `No file selected.`; (d) anonymous → 302.
- [ ] Add migration test: load `d5e7b9c1f203_add_image_table.py`, upgrade on an in-memory SQLite with a `user` table, assert `image` table with columns `id, filename, original_name, title, note, size, user_id, created_at` and unique index on `filename`; downgrade drops it; `test_drafts_revision_is_the_only_head` expects `['d5e7b9c1f203']`.
- [ ] Run: tests fail. Implement `Image` (columns per spec; `user_id` FK `ondelete='SET NULL'`), the migration (`down_revision = 'c8d3a5e7b102'`), `app/images.py` with the validation moved out of `routes.py`, and make `/upload` call `save_uploaded_image` mapping `ImageUploadError` to the same JSON/400.
- [ ] Run full pytest; commit `feat(images): image table and shared upload helper`.

### Task 2: Sync, usage tracking and visibility helpers

**Files:** Modify `app/images.py`, `tests/test_images.py`.

**Interfaces:** `sync_untracked_images() -> int`; `Usage = NamedTuple(kind, id, title, post_id)`; `image_usage(filenames) -> dict[str, list[Usage]]`; `visible_images(user)` returning a select statement; `image_url(image)`.

- [ ] Failing tests: sync registers valid unknown files once (second call returns 0), ignores `notes.txt` and `short.png`, keeps existing rows; usage found in post body, `PostDraft.body`, `Page.body`, absolute-URL form, two images in one post, unrelated text not matched, unpublished post counted, revisions ignored; `visible_images` gives all to admin, only own to a member, never ownerless to a member.
- [ ] Implement with one pass over `Post`, `PostDraft`, `Page` bodies using `USAGE_RE.findall`.
- [ ] Run, commit `feat(images): sync and usage helpers`.

### Task 3: Library list, library upload, picker JSON, navigation

**Files:** Create `app/admin/images.py`, `app/templates/admin/images/list.html`, `tests/test_admin_images.py`; Modify `app/admin/__init__.py` (import), `app/templates/admin/base.html` (nav "图片" in 工作区 for everyone, current on `admin.images`, `admin.image_detail`, `admin.delete_image`), `app/static/style.css`.

**Interfaces:** Endpoints `admin.images` (`GET /admin/images`, `q`), `admin.upload_images` (`POST /admin/images/upload`), `admin.image_picker` (`GET /admin/images/picker`).

- [ ] Failing tests: list shows title/size/usage count, search by title, note, original name; member sees only own; list auto-registers untracked files; library upload of 2 valid + 1 invalid file creates 2 rows and flashes a summary containing `已上传 2 张` and the failed name; upload without files flashes an error; picker JSON shape, newest first, `q`, limit 60, member visibility; anonymous redirected; nav link present for member and admin and marked current.
- [ ] Implement routes, template (grid of `<img loading="lazy">`, search form, upload form `multiple` with `enctype="multipart/form-data"` and CSRF hidden tag), nav entry, CSS (`.image-grid`, `.image-card`).
- [ ] Run, commit `feat(images): library page, upload and picker data`.

### Task 4: Detail/edit and delete

**Files:** Modify `app/admin/images.py`, `app/admin/forms.py` (`ImageEditForm`: `title` Length 1-120 optional→fallback, `note` Length ≤500; `ImageDeleteForm`: `force` BooleanField), create `app/templates/admin/images/detail.html`, `delete.html`, extend `tests/test_admin_images.py`, CSS.

**Interfaces:** `admin.image_detail` (`GET/POST /admin/images/<int:image_id>`), `admin.delete_image` (`GET/POST /admin/images/<int:image_id>/delete`); helper `_image_or_404(image_id)` enforcing ownership (403) and existence (404).

- [ ] Failing tests: edit saves title/note; empty title falls back to original name; over-long values re-render with errors; detail lists usages with edit links (post → `/admin/posts/<id>/edit`, page → `/admin/pages/<id>/edit`); member gets 403 on another's image for detail/edit/delete; missing id 404; delete unused image removes file and row; delete in-use image without `force` keeps everything (200, warning shown), with `force=y` deletes; missing file tolerated; CSRF 400; ownerless image 403 for member, ok for admin.
- [ ] Implement; delete removes the file (`Path.unlink(missing_ok=True)`) then the row, rolling back on `SQLAlchemyError`.
- [ ] Run, commit `feat(images): edit and delete images`.

### Task 5: `delete_user` hands over images

**Files:** Modify `app/authorization.py`, `tests/test_roles.py`.

- [ ] Failing tests: deleting a user with posts and images moves both to the receiver; deleting a user with images but no posts and no receiver sets `Image.user_id` to `NULL`.
- [ ] Implement with Core `update(Image)` before the user delete (receiver id, or `None`).
- [ ] Run, commit `feat(images): transfer images when a user is deleted`.

### Task 6: Editor picker (JS)

**Files:** Modify `app/static/markdown-editor.js`, `app/templates/admin/posts/form.html`, `app/templates/admin/pages/form.html`, `app/static/style.css` (`.image-picker`), `tests/markdown_editor.test.js`, add a python test in `tests/test_admin_images.py` asserting both forms carry `data-image-library-url="/admin/images/picker"`.

- [ ] Read `tests/markdown_editor.test.js` harness first (do not guess its fake-DOM API); extend it with tests: toolbar contains the custom `image-library` item when the attribute is set and not otherwise; clicking opens a dialog and fetches the picker URL; choosing an image calls the editor's insert with `![title](url)` (with `[`, `]`, `\` escaped in the title); Escape/close dismisses; fetch failure shows "加载失败" and does not throw; empty list shows "没有图片".
- [ ] Implement the toolbar item (`{ name: 'image-library', tip: '图片库', icon: …, click: openPicker }`) and a `createImagePicker(url, onSelect)` helper in the same file; use `vditor.insertValue(markdown)`.
- [ ] Run node and pytest, commit `feat(images): pick images from the library in the editor`.

### Task 7: Verification, docs, merge

- [ ] Full pytest and node runs; README: add the image library to the feature list and a note that `flask db upgrade` creates `image`.
- [ ] Browser check with the scratchpad scripts (seed users, upload via the library, open detail, delete confirmation, editor picker) in light/dark and 1440/390; fix findings.
- [ ] Commit; present the finishing menu.
