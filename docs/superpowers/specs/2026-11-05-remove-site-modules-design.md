# Remove The Built-in Site Modules

## Goal

Remove the four built-in module pages (Links, Guestbook, Todo, Movie) and their
data. The CMS already lets the owner create custom content pages, so the site
becomes: articles, categories, custom content pages, private messages, search,
archive and RSS. Article comments (`PostComment`) are unaffected.

This is irreversible for the module data: friend links, guestbook comments,
todo items and movies are dropped from the database. The owner chose this
explicitly over the lighter alternatives (allow deleting module pages in the
admin; delete the page records by hand).

## What Is Removed

**Public routes** in `app/routes.py`: `/movie`, `/todo`, `/links`, `/comment`
and their legacy mutation routes (`movie/edit`, `movie/delete`, `todo/update`,
`todo/delete`, `todo/edit`, `edit_link`, `delete_link`, guestbook delete), the
`_module_page` helper, and the `module_key` dispatch dictionary and guestbook
POST branch in `public_page`. After this change `public_page` serves content
pages only and returns 404 for any page whose `kind` is not `content`. The old
module URLs therefore 404 and their slugs are free for custom pages.

**Models and forms**: `Link`, `Movie`, `Todo`, `Comment` (guestbook), plus
`CommentForm`, `TodoForm`, `TodoEditForm`, `LinkForm` in `app/forms.py` and
`TodoAdminForm`, `MovieAdminForm`, `LinkAdminForm` in `app/admin/forms.py`.
`PostComment` and `PostCommentForm` stay.

**Templates**: `links.html`, `edit_link.html`, `movie/*`, `todo/*`,
`comment/comment.html`, `admin/modules/{links,movies,todos}.html`.

**Admin**:
- the todos, movies, links and guestbook routes in `app/admin/modules.py`;
- the "模块数据" group in `admin/base.html`;
- `admin/comments/list.html` shows article comments only and the nav label
  "评论与留言" becomes "评论";
- page management drops the "模块页" filter, the `module_key` hidden field and
  its validation, and the module notice block in `pages/form.html`.

**Page logic** (`app/pages.py`): `PAGE_MODULE`, `MODULE_KEYS` and the module
branches of `_validate_page_identity` are removed. A page can only be a content
page.

**Styles, docs, translations**: CSS for friend links, movie, todo and guestbook;
the README feature mentions; translation entries become obsolete and are
cleaned with `flask translate update`.

## What Stays

- `Page` columns `kind` and `module_key` and their CHECK constraints are left
  untouched. Changing constraints is risky across MySQL and SQLite and buys
  nothing now that no module rows exist. They can be dropped in a later change.
- `_pager.html`, `search-pagination`, About (a content page the owner deletes
  from the admin), articles, categories, private messages, search, archive,
  sitemap and RSS.

## Database Migration

A new Alembic revision on top of the current head `b5e1a7c9d234`.

Upgrade:
1. Delete `page_redirect` rows that point at module pages, explicitly, because
   SQLite does not enforce `ON DELETE CASCADE` unless foreign keys are enabled.
2. Delete `page` rows where `kind = 'module'`.
3. Drop tables `todo`, `movie`, `link`, `comment`, each only if it exists.
4. Log the number of rows removed from each table and from `page`.

Downgrade: recreate the four tables empty with their original columns and
constraints. Data and the deleted module pages are not restored. This mirrors
the existing followers-removal migration.

Cross-database: use SQLAlchemy operations only, no dialect-specific SQL. MySQL
is not testable here; the owner must back up the database before running
`flask db upgrade`.

## Testing

- **Migration tests** (`tests/test_migrations.py`), modelled on the
  `test_follow_removal_*` tests: upgrade to the previous revision, insert
  module pages with redirects, content pages, posts and rows in all four tables,
  upgrade, then assert module pages, redirects and the four tables are gone
  while content pages and posts are intact; assert the upgrade tolerates a
  missing table; assert downgrade recreates the four empty tables; assert there
  is a single head.
- **Behaviour tests**: `/movie`, `/todo`, `/links`, `/comment` return 404; a
  custom content page with one of those slugs can be created and served;
  creating a page with `kind='module'` is rejected; the admin nav has no
  "模块数据" group; the admin comments page lists only article comments.
- Remove tests that exercised the removed features (`test_admin_modules`,
  module parts of `test_legacy_admin_routes`, `test_pages`, `test_ui_pages`,
  `test_public_pages_consistency`, `test_admin_access`, and friends).
- Full `pytest` with `DATABASE_URL=sqlite://` and `node --test tests/*.test.js`.

## Manual Verification

Build a scratch SQLite database containing the four module pages and rows in
each table, run `flask db upgrade` against it, and check the logged counts and
the result. Then use playwright to confirm the public navigation no longer
shows the modules and the admin navigation and comments page look right.

## Delivery

Work happens on `feat/remove-modules`, one commit per task:
1. migration and its tests;
2. admin removal;
3. public routes, models and forms;
4. `pages.py` simplification;
5. CSS, README, translations and final verification.

Each commit leaves the full test suite green.
