# Registration, Drafts, and Revisions Design

## Goal

Allow administrators to disable new-account registration, let authors write
articles as private drafts that survive closing the editor, and retain a
bounded timeline of restorable draft versions.

## Registration Setting

A persistent site-settings record stores `registration_open`, defaulting to
true. An administrator-only settings page exposes it as a switch. When it is
off, the registration page tells anonymous visitors that registration is
temporarily unavailable and the registration POST rejects account creation on
the server. This server-side check prevents bypassing the user interface.

## Article Storage

`Post` remains the canonical public article and gains `is_published`. A post
has at most one `PostDraft`, which contains the currently editable title,
body, category, and detected language. It may have many immutable
`PostRevision` records containing the same content fields plus a creation
timestamp.

New articles start unpublished and are created on the first successful draft
save. Their editable content lives in `PostDraft`. Publishing atomically
copies the draft into `Post`, marks it published, and clears the draft.

Editing a published article creates or updates `PostDraft`; it never mutates
the public `Post` until the author chooses to publish the update. Unpublishing
hides the canonical post from public routes while preserving its editable
draft. Revisions are restored into the draft only, so restoring a version is
not a publication action.

## Public Visibility and Permissions

Only published posts appear in the index, user profiles, categories, search,
RSS, and post detail routes. Direct access to an unpublished post responds as
not found. Likes and comments are likewise unavailable for unpublished posts.

Authors may access their own drafts, histories, and mutation endpoints;
administrators may access every author's records. All write endpoints require
the existing login, ownership, and CSRF protections.

## Editor Flow

The article editor auto-saves a draft about one second after input settles and
reports `Saving`, `Saved`, or `Save failed` only after the server response.
Leaving the editor with saved changes attempts a final draft save, then creates
one revision snapshot. The normal auto-save loop updates the one current draft
and does not create timeline noise.

The editor controls are state-aware:

- An unpublished draft offers `Publish`.
- A published article with a draft offers `Publish update` and `Discard draft`.
- A published article without a draft offers `Unpublish`.

The revision timeline lists snapshots newest first with time, title, and a
content summary. Restoring a revision copies it into the current private draft
for further editing or a later explicit publication.

## Revision Retention

The same site-settings record stores `post_revision_limit`, a global integer
with a default of 20 and a valid range of 1 through 100. Each post keeps only
its newest N revisions. Creating a revision removes that post's older excess
records. Reducing the global limit immediately trims all posts to the new
limit.

## Error Handling

The client treats failed or interrupted requests as unsaved and presents a
save-failure state. It does not claim a draft or revision was saved until the
server confirms it. The leave-page request is best effort; the regular
one-second save protects normal editing before that final attempt.

## Verification

Tests cover the persistent registration setting and its server-side rejection,
draft isolation across every public article query, published-content stability
while an update draft exists, publish and unpublish transitions, autosave
authorization, revision creation on editor exit, global retention pruning,
and restoring a revision without public exposure. Existing management,
security, UI, search, and post-view coverage remains part of the full suite.
