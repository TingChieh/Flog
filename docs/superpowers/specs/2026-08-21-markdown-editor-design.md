# Markdown Editor Design

## Goal

Replace CKEditor in authenticated content-management forms with a Markdown-first
editor while preserving every existing HTML body byte-for-byte. New articles and
content pages use Markdown; comments and guestbook messages remain plain text.

## Scope

The Markdown editor applies to:

- new and existing article forms;
- new and existing ordinary CMS page forms;
- the About page, which is managed through the ordinary page CMS.

Module pages have no editable body and are unchanged. Article comments,
guestbook messages, profile fields, and private messages remain plain text.

## Compatibility Model

`Post` and `Page` receive a non-null `body_format` column whose supported values
are `html` and `markdown`. The migration uses `html` as both the server default
and the value for all existing rows. It does not rewrite either table's `body`
column.

New articles and ordinary pages are explicitly created with
`body_format='markdown'`. Editing an existing record preserves its current
format. Consequently, a legacy HTML record is shown as editable HTML source and
continues to be saved and rendered as HTML. The form identifies this state as
legacy HTML so that an editor does not mistake it for Markdown. There is no
implicit or automatic HTML-to-Markdown conversion.

The two-format model is intentionally narrow. Unknown or null format values are
treated as HTML for defensive backward compatibility, while form and model code
only writes the two supported values.

## Editing Experience

EasyMDE replaces CKEditor on the scoped forms. It provides a Markdown toolbar,
keyboard editing, preview, side-by-side preview, and fullscreen editing. Editor
assets load only on templates containing an opted-in editor textarea rather than
on every public page.

Markdown records receive the complete EasyMDE experience. Legacy HTML records
use the same stable source textarea without Markdown preview or Markdown toolbar,
because interpreting the source as Markdown could produce a misleading preview.
The form displays a concise legacy-format notice above the field.

The editor follows the current light and dark themes. On narrow screens its
toolbar wraps without horizontal page overflow, the editing surface retains a
stable minimum height, and fullscreen controls remain usable.

## Rendering And Security

A central server-side content renderer accepts a body and its format:

1. HTML input passes through the existing Bleach allowlist.
2. Markdown input is rendered by a maintained Python Markdown implementation.
3. The resulting HTML passes through the same Bleach allowlist.
4. Only the sanitized result is marked safe for Jinja.

Article detail, CMS public pages, admin page preview, and other full-body output
use this renderer. List excerpts continue to strip markup before truncation.
RSS descriptions use the same rendered and sanitized result so Markdown source
is not exposed as an unrendered description.

Browser-side EasyMDE preview is only an authoring aid and is never trusted as
stored or public HTML. Raw HTML written inside Markdown is sanitized by the
server pipeline. The existing allowlist remains the single policy boundary for
links, images, tables, and other supported elements.

## Forms And Persistence

CKEditor-specific form fields become WTForms `TextAreaField` instances. Templates
opt Markdown textareas into EasyMDE through a data attribute. Save handlers store
the source exactly as submitted, aside from existing required-field behavior;
they no longer sanitize Markdown into HTML before persistence.

Language detection continues to use the submitted source. Legacy HTML save paths
continue to sanitize HTML before storing it, matching current behavior. Page
creation and update retain the existing slug, redirect, publication, and
transaction rules.

The obsolete Flask-CKEditor initialization, global CKEditor CDN script, upload
integration that is no longer referenced by the scoped forms, and Python package
dependency are removed once call sites and tests confirm they are unused.

## Migration And Rollout

The Alembic migration proceeds conservatively:

1. Add `body_format` to `post` and `page` with a server default of `html`.
2. Explicitly backfill any null values to `html`.
3. Make the columns non-null where the database requires a staged alteration.
4. Keep the `html` server default so older application processes remain safe
   during a rolling deployment; application creation paths still write
   `markdown` explicitly.

The migration is first exercised against a disposable MySQL database copied from
the current schema. Production migration requires a current backup and checks
that existing body values are unchanged before and after the upgrade.

## Error Handling

Editor JavaScript is progressive enhancement: if the CDN asset fails, the source
textarea remains fully usable and the server accepts valid submissions. Empty or
invalid form submissions use the existing inline validation errors without
discarding source text. Markdown rendering failures do not expose unsafe source;
the renderer returns sanitized plain content and records the failure through the
application logger.

## Verification

Automated coverage includes:

- migration defaults existing Post and Page rows to HTML without changing body;
- new Post and Page rows are stored as Markdown;
- editing a legacy row preserves its HTML format;
- Markdown headings, links, lists, code blocks, and tables render correctly;
- scripts, event handlers, unsafe URLs, and disallowed raw HTML are removed;
- article detail, page preview, public pages, and RSS use compatible rendering;
- comment and guestbook forms remain plain text and do not initialize EasyMDE;
- editor assets are absent from ordinary public pages.

Browser verification covers desktop and mobile article/page forms, legacy HTML
notice and editing, Markdown preview, long content, validation errors, light and
dark themes, toolbar wrapping, and usable fallback behavior with editor scripts
blocked.

## Non-Goals

- Automatic conversion of existing HTML to Markdown.
- A WYSIWYG editing mode.
- Markdown support for public comments or guestbook messages.
- Persisting a second rendered-HTML cache column.
- Changing the current HTML sanitization allowlist beyond additions required for
  standard Markdown output.
