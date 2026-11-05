# Vditor Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace EasyMDE with a self-hosted Vditor (instant rendering) for articles and content pages.

**Spec:** `docs/superpowers/specs/2026-11-05-vditor-editor-design.md`. Baseline: 571 pytest, 44 node. Branch `feat/vditor-editor`.

## Task 1: Vendor Vditor 4.0.1

- [ ] In an empty scratch directory run `npm pack vditor@4.0.1`, compare the tarball's sha512 with `npm view vditor@4.0.1 dist.integrity`, extract it into its own empty directory and never run anything from it.
- [ ] Copy only: `dist/index.min.js`, `dist/index.css`, `dist/js/lute/lute.min.js`, `dist/js/i18n/zh_CN.js`, `dist/js/icons/ant.js`, `dist/css/content-theme/light.css`, `dist/css/content-theme/dark.css`, `LICENSE` into `app/static/vendor/vditor/4.0.1/` (same relative paths). Write `app/static/vendor/vditor/4.0.1/README.md` (version, file list, integrity, date, "do not edit").
- [ ] `tests/test_vditor_assets.py`: every listed file exists and is non-empty, `LICENSE` contains "MIT", `README.md` names version 4.0.1, the directory holds no other `.js` files (guards against vendoring the 22 MB of optional renderers), and the total size is under 5 MB. Commit `chore: vendor Vditor 4.0.1`.

## Task 2: Script, templates, tests

- [ ] Read `tests/markdown_editor.test.js` lines 1-503 (harness) and rewrite it around a mock `Vditor` constructor recording `(host, options)`, with `getValue`, `insertValue`, `setTheme`, an `after()` trigger and an `input()` trigger; keep the draft/leave/BFCache cases from line 747 on, driving changes through the adapter's `onChange`.
- [ ] New tests (write first, see them fail): init options (`mode: 'ir'`, `cdn`, `lang: 'zh_CN'`, `cache.enable === false`, toolbar list from the spec, markdown flags, `preview.hljs.enable === false`); the textarea is hidden and kept; `input` and `submit` sync the textarea; adapter `value()` before and after `after()`; `upload.handler` uploads in order, inserts one batch at the end via `insertValue`, ignores non-image files, reports a safe error and inserts nothing when any file fails, sends `X-CSRFToken`, field `post`; no upload option when the form has no upload url or CSRF token; `MutationObserver`-driven `setTheme('dark', 'dark')` / `setTheme('classic', 'light')`; the WYSIWYG mode button is removed from the mode menu after `after()`; initialisation is idempotent; nothing runs without `Vditor` defined.
- [ ] Rewrite `app/static/markdown-editor.js`: create the host `div` after the textarea, hide the textarea, `new Vditor(host, {...})`, adapter on `field.markdownEditor`, `upload.handler`, theme observer, WYSIWYG-entry removal, `initializeArticleDraftEditor` using `editor.value()` and `editor.onChange(...)` instead of `codemirror`; keep the draft/leave/publication code unchanged otherwise. Remove the EasyMDE stylesheet-ready logic.
- [ ] Templates `admin/posts/form.html` and `admin/pages/form.html`: `page_styles` links `vendor/vditor/4.0.1/dist/index.css`; `page_scripts` loads `vendor/vditor/4.0.1/dist/index.min.js` then `markdown-editor.js` (no DOMPurify, no `data-easymde-stylesheet`); set `data-vditor-cdn="{{ url_for('static', filename='vendor/vditor/4.0.1') }}"` on the textarea so the script does not hard-code the path.
- [ ] Update `tests/test_ui_pages.py` asset assertions (editor pages: Vditor css/js, `markdown-editor.js`, `data-markdown-editor`, `data-image-upload-url="/upload"`, no easymde, dompurify, `maxcdn`, `cdn.jsdelivr`, `unpkg`; public pages and legacy HTML editors: none of it). Run both suites. Commit `feat(admin): Vditor instant-rendering editor`.

## Task 3: Styles and browser verification

- [ ] Replace the EasyMDE rules in `style.css` (`.admin-form .EasyMDEContainer`, `.CodeMirror`, `.editor-toolbar*`, `.editor-preview`, dark overrides, `.markdown-editor--dragging`, `.markdown-upload-status`) with a "Vditor" section: map Vditor's classes/variables (`.vditor`, `.vditor-toolbar`, `.vditor-reset`, `.vditor-ir`, `.vditor-sv`, `.vditor-preview`, `.vditor-hint`, `.vditor-tip`, `.vditor-counter`, `.vditor-menu`) onto `--surface`, `--surface-muted`, `--border`, `--text-primary`, `--text-secondary`, `--link-color`, 6px radii, the serif body font in the editing area; toolbar scrolls horizontally under 768px; hide the WYSIWYG mode button with CSS as a fallback. Add a CSS test for the section marker and for the removal of the EasyMDE selectors.
- [ ] Browser verification with the scratch DB and playwright (see spec): list `performance.getEntriesByType('resource')` and assert all are same-origin; type headings, lists, a table and a fenced code block in instant rendering; paste and drop an image through the existing `/upload`; switch to split preview; toggle light/dark; autosave, reload and compare the saved Markdown; 390px viewport. Fix defects in separate commits. Commit `feat(admin): Vditor editor styles`.

## Task 4: Cleanup and docs

- [ ] `git rm -r app/static/vendor/easymde app/static/vendor/dompurify`; `grep -rn "easymde\|EasyMDE\|dompurify\|DOMPurify" app tests README.md` must show nothing except historical docs under `docs/superpowers/`.
- [ ] README: describe the editor (Vditor instant rendering, self-hosted, which Markdown the server supports); `docs/` historical specs stay untouched.
- [ ] Full `pytest` and `node --test tests/*.test.js`; commit `chore: remove EasyMDE and DOMPurify`.
