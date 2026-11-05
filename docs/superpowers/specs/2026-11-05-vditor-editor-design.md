# Typora-style Markdown Editor (Vditor)

## Goal

Replace the EasyMDE source-plus-preview editor with Vditor in "instant
rendering" mode (Typora-like) for articles and content pages, self-hosted with
no external requests, restyled to match the site. Articles remain Markdown
source stored as before and rendered by the server (Python-Markdown `extra`,
`sane_lists`, `codehilite`).

## Why Vditor, which version

Vditor is plain-JS, Chinese-native, MIT, and offers instant rendering, split
preview and WYSIWYG modes. Version **4.0.1** is the npm `latest` tag, published
2026-10-18 (more than two weeks old). A newer 4.0.2 alpha exists and is not
used. If 4.0.1 shows regressions during verification the fallback is 3.11.3.
EasyMDE is dropped together with the FontAwesome CDN stylesheet it injects
(`maxcdn.bootstrapcdn.com/font-awesome/latest`) and with DOMPurify, which only
the old editor used.

## Assets (self-hosted, no CDN)

Under `app/static/vendor/vditor/4.0.1/`, keeping Vditor's own layout so that
`cdn: '/static/vendor/vditor/4.0.1'` resolves everything:

- `dist/index.min.js` (~290 KB), `dist/index.css` (~48 KB)
- `dist/js/lute/lute.min.js` (3.7 MB, ~0.6 MB gzipped; Vditor's Markdown engine)
- `dist/js/i18n/zh_CN.js`, `dist/js/icons/ant.js`
- `dist/css/content-theme/light.css`, `dark.css`
- `dist/js/highlight.js/styles/github.min.css` (requested even with highlighting
  off)
- `LICENSE` and a `README.md` recording the version, the file list and the npm
  `dist.integrity` of the tarball the files came from.

Not vendored: highlight.js, mermaid, katex, mathjax, echarts, graphviz, abcjs,
markmap, plantuml, wavedrom, smiles-drawer, flowchart, emoji images. Code-block
and math preview are turned off in the editor so nothing tries to fetch them.

## Behaviour

- **Modes**: instant rendering is the default; split preview is available from
  the mode menu. The pure WYSIWYG entry is removed from that menu because it
  rewrites Markdown source formatting.
- **Toolbar** (only what the server renderer supports): headings, bold, italic,
  quote, unordered list, ordered list, code block, inline code, link, table,
  horizontal rule, image upload, undo, redo, mode menu, fullscreen. No
  strikethrough, task list, emoji, math, mark, sup/sub, outline or export.
- **Markdown options** matching Python-Markdown: `inlineMath`, `mathBlockPreview`,
  `codeBlockPreview`, `callout`, `mark`, `sup`, `sub`, `gfmAutoLink` all false;
  `footnotes` true; `sanitize` true; `cache.enable` false (drafts are saved by
  the server, not localStorage); `preview.hljs.enable` false.
- **Form integration**: the original `textarea[data-markdown-editor]` stays in
  the form (hidden) and is the submitted field. Vditor's `input` callback copies
  the Markdown into it; a `submit` listener copies it once more.
- **Editor adapter**: `field.markdownEditor = {value(), onChange(fn), insertImages,
  vditor}`. `value()` returns the textarea value until Vditor has finished
  loading, then `vditor.getValue()`. The draft autosave, leave/BFCache and
  publication-state logic keep their code and only use `value()` and
  `onChange()`.
- **Images**: Vditor's `upload.handler(files)` reuses the existing flow (field
  `post`, `X-CSRFToken`, response `{uploaded: 1, url}`, `![图片](url)` snippets
  inserted in order in one batch, status line with `role="status"`). Toolbar
  button, drag-and-drop and paste all go through it. Accepted types stay
  gif/jpeg/png and server-side validation stays authoritative.
- **Theme**: follows `html[data-theme]` live through a `MutationObserver`
  calling `vditor.setTheme('dark'|'classic', 'dark'|'light')`.
- **Styling**: Vditor's CSS variables and classes are overridden with the site
  tokens (surface, border, text, link colour, serif body font), square-ish 6px
  radii, quiet toolbar icons; on narrow screens the toolbar wraps
  (overflow scrolling would clip its dropdown panels). The old `.EasyMDEContainer`, `.CodeMirror`, `.editor-toolbar`
  rules are removed.
- Legacy HTML articles and pages keep the plain textarea (no editor), as now.

## Known differences from the published page

The editor renders with Lute, the site with Python-Markdown, so details can
differ (soft line breaks, footnote numbering, definition lists and other
`extra` syntax Lute does not render). The server remains the source of truth;
the pages are not changed.

## Testing

- `tests/markdown_editor.test.js` is rewritten around a mock `Vditor`: init
  options (mode, cdn, toolbar, cache off, markdown flags), textarea sync on
  input and submit, adapter `value()` before and after ready, draft autosave
  debounce and leave/BFCache behaviours (existing cases kept), upload through
  `handler` (order, one batch, failure leaves the document unchanged, safe
  error text, non-image files ignored), theme change calls `setTheme`.
- pytest: editor pages link the vendored Vditor files and `markdown-editor.js`,
  carry `data-markdown-editor` and `data-image-upload-url`, never reference
  easymde, dompurify or any external CDN; public pages and legacy-HTML editors
  load none of it; the vendored file list and licence exist.
- Browser (playwright): no cross-origin request on the editor page; typing in
  instant rendering mode; paste and drag an image; mode switch; light/dark
  switch; autosave then reload shows identical content; 390px layout.

## Delivery

Branch `feat/vditor-editor`, four commits: (1) vendored assets and provenance;
(2) editor script, templates, tests; (3) styles; (4) removal of EasyMDE and
DOMPurify, docs and final verification.
