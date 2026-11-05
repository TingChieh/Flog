# Image library

## Goal

Uploaded images are stored under random names in `UPLOAD_FOLDER` with no
database record, so nobody can tell which images exist, who uploaded them or
which article uses them. Add an image library: a record per image with an
editable name and note, an admin page to browse, upload, edit and delete,
usage tracking, and a picker inside the article/page editor.

Out of scope: thumbnail generation, cleaning up unused images in bulk, image
editing/cropping, formats beyond gif/jpg/png.

## Data

New table `image` (model `Image`):

| column | type | notes |
| --- | --- | --- |
| `id` | int PK | |
| `filename` | str(80), unique, indexed | the stored name, `<uuid hex><ext>` |
| `original_name` | str(255) | sanitised uploaded name; for display only |
| `title` | str(120) | editable; defaults to the original name without extension |
| `note` | str(500), nullable | editable description |
| `size` | int | bytes |
| `user_id` | FK `user.id`, nullable, `ON DELETE SET NULL`, indexed | uploader |
| `created_at` | datetime | upload time (file mtime for backfilled files) |

One Alembic migration creates the table; downgrade drops it. Files on disk are
never touched by the migration.

## Shared upload logic: `app/images.py`

- `save_uploaded_image(file, user) -> Image`: moves the existing validation out
  of the `/upload` view unchanged (extension in gif/jpg/jpeg/png, matching magic
  bytes, uuid filename, saved into `UPLOAD_FOLDER`), then inserts and commits
  an `Image` row. Raises `ImageUploadError(message)` for "No file selected." and
  "Image only!".
- `/upload` keeps its JSON contract (`{'uploaded': 1, 'filename': '', 'url':
  ...}` or `{'uploaded': 0, 'error': {'message': ...}}` with 400) and now calls
  `save_uploaded_image`.
- `sync_untracked_images() -> int`: registers files in `UPLOAD_FOLDER` that have
  no row and whose name matches `^[0-9a-f]{32}\.(png|jpe?g|gif)$` (owner
  `NULL`, title = file stem, size and mtime from the file). Idempotent. Called
  when the library list opens. Files that disappeared from disk keep their row
  and show as "文件缺失" (preview hidden); deleting such a row works.
- `image_usage(filenames) -> dict[filename, list[Usage]]` where
  `Usage = (kind, id, title)` and kind is `post`, `draft` or `page`. It scans
  `Post.body`, `PostDraft.body` and `Page.body` for
  `/files/<filename>` (regex `/files/([0-9a-f]{32}\.(?:png|jpe?g|gif))`) in one
  pass and groups by filename. An unpublished post still counts. Revisions are
  ignored. A draft that is attached to a post is reported against the post's
  edit page with kind `draft`.
- `visible_images(user)`: all images for administrators; only
  `user_id == user.id` for everyone else.

## Admin pages (all `@login_required`; members see only their own images)

| route | purpose |
| --- | --- |
| `GET /admin/images` | library grid; `q` searches title, note and original name (case-insensitive substring); shows title, size, upload time and "被 N 处引用"; lazy-loaded images; multi-file upload form |
| `POST /admin/images/upload` | multi-file upload from the library; one row per file; flashes a summary, e.g. "已上传 3 张，1 张失败（文件名：原因）" |
| `GET/POST /admin/images/<id>` | detail: large preview, editable title and note, the image URL with a copy button, list of usages linking to the post/page edit page, delete link |
| `GET/POST /admin/images/<id>/delete` | confirmation page listing usages; if the image is in use the POST needs `force=y` (a second checkbox on the page: "我知道这些位置的图片会失效"); deletes the file and the row |
| `GET /admin/images/picker` | JSON for the editor: `{"images": [{"id", "title", "url", "size"}]}`, newest first, optional `q`, at most 60 entries |

Rules:
- A member requesting someone else's image (detail, edit, delete) gets 403, a
  missing id 404. Anonymous users are redirected to login.
- Title must be 1-120 characters, note at most 500. An empty title falls back to
  the original name.
- All mutations are POST with CSRF.
- Deleting commits the row removal first and then removes the file, so a
  database failure never loses the file; a missing file is not an error. A database
  failure rolls back and flashes the usual "…失败，请重试。".
- `delete_user` (admin user deletion) hands the user's images to the receiver
  together with the posts; when there is no receiver (the user had no posts)
  the images become ownerless and are visible only to administrators.
- Navigation: a new "图片" link in the "工作区" group, visible to everyone,
  marked current on all `admin.images*` endpoints.

## Editor picker

`admin/posts/form.html` and `admin/pages/form.html` add
`data-image-library-url="{{ url_for('admin.image_picker') }}"` next to the
existing `data-image-upload-url`. `markdown-editor.js`:

- adds a custom Vditor toolbar item named `image-library` (label "图片库",
  placed after `upload`) when that attribute is present;
- clicking it opens a `<dialog>` with a search field and a grid of thumbnails
  fetched from the picker URL (`credentials: 'same-origin'`); selecting one
  inserts `![<title>](<url>)` at the cursor through the existing insertion
  path and closes the dialog; Escape and a close button dismiss it;
- shows "没有图片" / "加载失败" states and never throws into the editor;
- titles are escaped for Markdown (`[`, `]`, `\`).

## Styling

Reuse the editorial admin tokens: `.admin-search`, `.admin-form`, quiet
buttons. New classes `.image-grid`, `.image-card`, `.image-detail`,
`.image-picker` with responsive columns (1 / 2 / 4) and the same serif type;
works in light and dark.

## Testing

pytest first:

- model/upload: `/upload` still returns the same JSON, creates a row with
  original name, size and uploader, rejects non-images, library upload of
  several files with one bad file.
- sync: untracked files are registered once, non-matching names ignored,
  existing rows untouched.
- usage: found in post body, draft body and page body; two images in one post;
  absolute-URL form (`http://host/files/…`) matches; unrelated text does not.
- permissions: member sees/edits/deletes only own images (403 otherwise),
  admin sees all, anonymous redirected, ownerless images admin-only.
- edit: title/note saved, validation errors, empty title fallback.
- delete: file and row removed, in-use image requires `force`, missing file
  tolerated, CSRF enforced.
- search, picker JSON (visibility, `q`, limit), navigation entry.
- `delete_user` transfers images.
- migration test: upgrade creates the table, downgrade drops it; head moves to
  the new revision.

node test with the fake-DOM harness for the picker (open, load, select
inserts Markdown, escape, failures), then browser verification (light, dark,
1440 / 390) of the library, detail, delete confirmation and the editor picker.
