# Article Editor Image Upload Design

## Goal

Make image insertion in Markdown article writing feel native to the editor by
supporting toolbar selection, drag-and-drop, and clipboard paste. Uploaded
images are inserted at the current cursor position as Markdown image syntax
without requiring authors to copy URLs manually.

## Scope

The shared Markdown editor used by new and editable Markdown articles and
ordinary CMS content pages gains the image upload workflow. Legacy HTML editors,
comments, guestbook messages, and other plain-text fields remain unchanged.

The existing authenticated `/upload` endpoint remains the upload API. This
feature does not add a media library, image transformations, captions stored in
separate fields, or a new persistence model.

## Approaches Considered

1. Extend only EasyMDE's existing image toolbar action. This is the smallest
   change, but drag-and-drop and clipboard workflows remain inconsistent.
2. Add one upload coordinator around the editor and route toolbar, drop, and
   paste events through it. This keeps behavior consistent, reuses the current
   endpoint, and preserves progressive enhancement. This is the selected
   approach.
3. Build a reusable media library. This would support image reuse, but adds
   management UI, storage lifecycle questions, and scope unrelated to the
   immediate writing flow.

## Interaction Design

- The toolbar image action opens a hidden image-only file input.
- Dropping one or more image files on the editor starts uploads and prevents the
  browser's default navigation behavior.
- Pasting clipboard image data starts an upload when the clipboard contains one
  or more image blobs; ordinary text paste is untouched.
- Multiple files are uploaded in selection order. Each successful result is
  inserted in that same order at the cursor, separated by blank lines.
- The insertion format is `![图片描述](/files/<random-name>.<ext>)`.
  The description defaults to `图片`; after insertion, the description text is
  selected when practical so the author can replace it immediately.
- Uploading shows a non-blocking status message near the editor. A failed file
  leaves existing source untouched and reports the server's safe error message.
  The author can retry by selecting, dropping, or pasting again.
- The existing URL-based EasyMDE image behavior remains available as a fallback
  for authors who want to reference a remote image.

## Architecture And Data Flow

`markdown-editor.js` owns a small upload coordinator per initialized EasyMDE
instance:

1. An input, drop, or paste handler extracts image `File` objects.
2. The coordinator creates `FormData` with the existing `post` field and sends
   one CSRF-protected request per file to `/upload`.
3. The response must contain `uploaded: 1` and a URL. Invalid or non-OK
   responses become user-visible upload errors without inserting source.
4. The coordinator inserts Markdown through EasyMDE's CodeMirror selection API,
   preserving the current cursor/selection and triggering the existing change
   listener used by draft autosave.
5. Existing draft persistence treats inserted Markdown exactly like typed text.

The server route remains the source of truth for authentication, CSRF, file
signature validation, randomized names, and storage. No client-side preview is
trusted or persisted as HTML.

## Error Handling And Accessibility

- Non-image clipboard or dropped files are ignored without preventing ordinary
  text operations; mixed drops/pastes upload only image files.
- Network errors, authentication failures, CSRF failures, and malformed success
  payloads produce a concise status message and never insert a broken URL.
- The hidden file input has an accessible label via the toolbar button. Status
  text uses `aria-live="polite"`, and drag-over affordances do not depend on
  color alone.
- Upload controls are unavailable for legacy HTML editors because those forms do
  not initialize the Markdown editor.
- If editor JavaScript or its assets fail, the underlying textarea remains
  usable for manually authored Markdown and existing server behavior is intact.

## Styling

Add only editor-scoped styles for drag-over indication, upload status, and any
compact retry affordance. Styles must work in the existing light and dark theme,
wrap on narrow screens, and avoid changing public article rendering.

## Verification

Automated browser-side tests cover:

- toolbar selection uploads an image and inserts Markdown at the cursor;
- drag-and-drop and clipboard image uploads use the same coordinator;
- multiple files preserve order and blank-line separation;
- upload failures leave source unchanged and expose a safe status message;
- ordinary text paste remains unchanged;
- draft change listeners observe inserted Markdown;
- legacy HTML and non-editor pages do not initialize upload behavior.

Server-side regression tests retain authentication, CSRF, signature validation,
randomized filename, and file-serving coverage for `/upload`.

Manual verification covers desktop and narrow article/page forms, light/dark
themes, selection replacement, a slow upload, a rejected file, and a browser
with editor scripts blocked.

## Non-Goals

- Media-library browsing, deletion, or reuse management.
- Image resizing, compression, thumbnails, EXIF processing, or alt-text storage
  separate from Markdown.
- Uploading non-image attachments.
- Changing the current upload directory, URL shape, or server-side allowlist.
