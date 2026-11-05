# Public Profiles And Module Visibility Design

Date: 2026-08-23
Status: Approved for implementation planning

## Goal

Simplify the blog's public experience by removing the follow system, making
user profile pages readable without authentication, and making every built-in
module's publication and navigation visibility controllable from the existing
Page CMS.

The four built-in modules are:

- Todo (`todo`)
- Movie (`movie`)
- Links (`links`)
- Guestbook (`guestbook`)

## Scope

This change removes the follow feature completely, including persisted follow
relationships. It does not remove user accounts, author pages, private
messages, profile editing, post export, or article ownership.

This change reuses the existing Page model and admin page editor for module
visibility. It does not add an environment-variable feature flag or a second
module-settings table.

## Follow Feature Removal

Remove all application surfaces that create, consume, or present follow
relationships:

- The `followers` SQLAlchemy association table.
- `User.following` and `User.followers` relationships.
- `User.follow()`, `User.unfollow()`, `User.is_following()`,
  `User.followers_count()`, `User.following_count()`, and
  `User.following_posts()`.
- The authenticated `/following` feed.
- The `POST /follow/<username>` and `POST /unfollow/<username>` mutations.
- The Following entry in the primary navigation.
- Follower/following counts and follow/unfollow forms on full profile pages
  and profile popups.
- Follow-specific tests, imports, and dead form construction.

After removal, requests to old follow URLs must not mutate data. Because no
matching route remains, they resolve through normal Flask routing and return a
non-success response, normally 404.

The `following` slug is removed from the Page CMS reserved-slug set because the
application no longer owns that public route. A future content page may use
that slug.

## Follow Data Migration

Add a new Alembic revision after `c2f6e8a91d04` that drops the `followers`
table. Upgrade permanently removes all existing follow relationships.

Downgrade recreates an empty `followers` table with:

- `follower_id` and `followed_id` integer columns.
- A composite primary key across both columns.
- Foreign keys to `user.id` matching the former schema.

Downgrade cannot restore deleted follow rows. This limitation must be stated in
the migration documentation and deployment handoff.

The migration must not change users, posts, roles, content, view counts, Page
CMS records, or module data. A missing expected `followers` table is a schema
error and should stop the migration instead of being silently ignored.

## Public User Profiles

Remove `login_required` from `GET /user/<username>`. Anonymous visitors can
view the same public profile information as authenticated visitors:

- Avatar
- Username
- About text
- Last-seen time
- Paginated authored articles

Missing usernames continue to return 404. Pagination behavior and article
ordering remain unchanged.

Profile actions follow authentication and ownership boundaries:

- An authenticated user viewing their own profile sees Edit Profile and Export
  Posts under the existing conditions.
- An authenticated user viewing another profile sees Send Private Message.
- An anonymous visitor sees no edit, export, or private-message action.
- Follow counts and follow/unfollow controls never appear for any visitor.

Profile popups remain public and show avatar, username, about text, and
last-seen time. They no longer construct a follow form or invoke follow-related
methods. A popup must render safely for an anonymous visitor.

The underlying profile-edit, export, and message-send routes remain protected
by their existing authentication and authorization rules.

## Module Visibility Model

The existing Page CMS is the single source of truth for all four built-in
modules. Each module retains its seeded `Page(kind='module')` record and uses
the existing controls:

- `is_published`: controls whether the module is publicly accessible.
- `show_in_nav`: controls whether the module appears in primary navigation.
- `nav_order`: controls its position among other visible pages.

The resulting behavior matrix is:

| Published | In navigation | Public access | Navigation entry |
|---|---|---|---|
| Yes | Yes | Allowed | Shown |
| Yes | No | Allowed | Hidden |
| No | Yes or No | 404 | Hidden |

`show_in_nav` never overrides `is_published`. An unpublished page is excluded
from navigation even if its stored navigation flag is true.

The existing admin page edit form remains the control surface. Module identity
and underlying module data continue to be managed separately: Page CMS owns
title, slug, summary, publication, navigation visibility, and order; each
module's existing admin screen owns its Todo/Movie/Link/Guestbook records.

## Public Module Routing

Both canonical CMS slugs and legacy module addresses obey `is_published`:

- Todo: CMS slug and `/todo`
- Movie: CMS slug and `/movie`
- Links: CMS slug and `/links`
- Guestbook: CMS slug and `/comment`, for both GET and POST

When a module Page record is unpublished, all of its public addresses return
404. When its configured slug differs from the legacy slug, the published
legacy address keeps the existing permanent redirect to the configured slug.

If a module Page record is unexpectedly missing, the module fails closed with
404. It must not fall back to serving an unconfigured public module.

Administrative module routes remain available to authorized administrators
regardless of public publication state so content can be prepared before
publication.

## Navigation

Primary navigation renders Home plus the result of
`visible_navigation_pages()`, which already requires both `is_published` and
`show_in_nav` and applies `nav_order`.

Remove both follow-related navigation and the hard-coded fallback block that
currently inserts Movie, Guestbook, Todo, Links, and About whenever no Page is
visible. If all Page entries are hidden or unpublished, none of those entries
may reappear automatically.

Authenticated-only Management, Messages, and Profile entries keep their
existing conditions. Search remains available.

## Error Handling And Transactions

Public profile reads and module reads perform no new mutations. Unknown users,
missing module configurations, and unpublished modules return 404.

Admin Page updates continue through `save_page()` and the existing transaction
boundary. Validation failures remain form errors; SQLAlchemy failures roll back
and show the existing retry message. No new visibility state is stored outside
the Page row, preventing disagreement between separate settings systems.

The follow-table migration is deliberately destructive. Production deployment
must create and verify a MySQL backup before upgrade. If table removal fails,
Alembic must not advance its revision marker.

## Testing Strategy

### Migration

- Upgrade drops `followers` while preserving user and post rows.
- Upgrade leaves Page/module records and their flags unchanged.
- Downgrade recreates an empty association table with both foreign keys and the
  composite primary key.
- Migration head remains singular.

### Follow removal

- User model has no follow relationships or helper methods.
- Old following feed and follow/unfollow mutations no longer succeed.
- Navigation, full profile, and popup HTML contain no follow entry, count,
  form, or URL.
- No application query references the removed table.

### Public profiles

- Anonymous profile requests return 200 and render avatar, username, about,
  last-seen time, and authored posts.
- Unknown users return 404.
- Anonymous visitors see no protected actions.
- Owners retain edit/export actions; authenticated non-owners retain the
  private-message action.
- Profile popups render for anonymous visitors without server errors.
- Existing protected action routes still redirect unauthenticated users to
  login.

### Module matrix

For each of Todo, Movie, Links, and Guestbook:

- Published and navigation-visible: canonical page returns 200 and navigation
  includes it.
- Published and navigation-hidden: canonical page returns 200 and navigation
  excludes it.
- Unpublished: canonical and legacy GET addresses return 404 and navigation
  excludes it.
- Renamed published modules retain the legacy-to-canonical 301 redirect.

Guestbook additionally verifies that unpublished POST requests return 404 and
cannot create comments. Authorized administrators can still manage all module
data while the public module is unpublished.

### Navigation and UI

- With all Page entries hidden, primary navigation shows no hard-coded module
  fallback.
- Navigation order remains driven by `nav_order`.
- Desktop and mobile browser checks cover the empty/partial/full module
  navigation states, anonymous profile pages with long usernames, profile
  popups, protected-action visibility, and light/dark modes.
- Browser checks verify no overlap, horizontal overflow, broken navigation
  toggle, failed network request, or console error.

The focused suites and complete existing pytest suite must pass.

## Deployment

Deployment order:

1. Confirm the deployed code/database target and current Alembic revision
   `c2f6e8a91d04`.
2. Record the current number of rows in `followers`.
3. Create a timestamped, checksummed MySQL backup.
4. Run the new Alembic upgrade that drops `followers`.
5. Verify the new revision, absence of `followers`, unchanged user/post counts,
   and unchanged four module Page states.
6. Deploy or restart the application code.
7. Smoke-test an anonymous user profile and all four module publication and
   navigation states.

Production migration requires a separate explicit confirmation after code,
tests, scratch migration rehearsal, and browser verification are complete.

