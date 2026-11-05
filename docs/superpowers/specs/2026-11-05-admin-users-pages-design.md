# Admin: user management, page management, dashboard

## Goal

Fill the gaps in the admin area: users can only be listed and have their role
changed, the page list is thin, the dashboard shows one number, and the "about"
page is still a special case written around a legacy table. After this change
"about" is an ordinary page and the admin has real user management.

## 1. User management (`/admin/users`, admin only)

**List.** Search box (`q`, matches username or email, case-insensitive
substring) and role filter (`role=all|user|admin`). Each row: username, email,
role, article count, last seen, links "编辑" and "删除". The inline role select
and "更新" button are removed; role is changed on the edit page. Invalid
`role` value → 400.

**New user** (`/admin/users/new`). Fields: username (required, unique, ≤64),
email (required, valid, unique, ≤120), password (required, same rule as
registration: non-empty), role (user/admin, default user). Works even when
public registration is closed.

**Edit user** (`/admin/users/<id>/edit`). Fields: username, email, role,
optional new password (blank keeps the current hash). Uniqueness ignores the
user being edited. The role change keeps going through `change_user_role`, so
"last administrator cannot be demoted" and "cannot remove your own admin role"
still apply and are shown as a flash message / field error. The admin editing
themselves sees the role select disabled.

**Delete user** (`/admin/users/<id>/delete`). GET shows a confirmation page
with the article count and a select of receivers (all other users, default the
acting admin). POST (CSRF) transfers the user's articles to the receiver, deletes
the user (likes cascade via the existing FK), commits, flashes. A user with no
articles skips the receiver. Refused with a flash + 400: deleting yourself,
deleting the last administrator, a receiver equal to the deleted user or not
existing. Logic lives in `app/authorization.py` next to `change_user_role`
(`delete_user(actor, target, receiver)`), raising the existing
`RoleChangeError`-style error type for guard failures.

Not included: disabling users (needs a schema change).

## 2. Page management (`/admin/pages`)

**"About" becomes an ordinary page.** The page row with slug `about` already
exists in `page`; what remains is dedicated code around it. Removed:

- `About` model, `AboutForm`, the `about` table (new Alembic migration drops it;
  downgrade recreates an empty table with the original columns). Old databases
  that never ran `9c8e2f3a4b5d` lose any unmigrated legacy text; normal
  deployments are unaffected.
- Routes `/about` and `/about/edit` in `app/routes.py` (the generic
  `/<slug>` route and `PageRedirect` already serve and redirect the page) and
  the unused templates `templates/about/about.html`, `edit_about.html`.
- The slug special-cases in `templates/page/content.html` (`about-page` class
  and the "About" label).
- Admin route `admin.about`, `_prefill_from_query` and its nav entry "关于".
- Any now-unused catalog entries stay in the `.po` files (harmless); not
  regenerated.

The `.about-page` editorial rules in `style.css` are generalised to every
content page (`.public-page .page-body …`): large summary, spaced headings,
quote rule, list spacing. No page gets a special label; formatting beyond that
is written in the page's Markdown.

**List improvements.**

- `q` searches title and slug (case-insensitive substring).
- The "内容页" filter is removed (all pages are content pages); filters are
  全部 / 已发布 / 未发布. Unknown filter → 400 (unchanged).
- Each row shows the last updated time.
- Inline toggles "发布/取消发布" and "导航显示/隐藏": POST to
  `/admin/pages/<id>/publish` and `/admin/pages/<id>/nav` with CSRF, flash and
  redirect back to the list preserving `q` and `filter`.

Not included: bulk actions, drag-and-drop ordering, scheduled publishing.

## 3. Dashboard (`/admin/`)

A row of linked metric cards using the existing `admin-metric` styling.
Everyone: 我的文章 (→ my posts). Administrators additionally: 全部文章, 页面
(published / total), 评论, 用户, each linking to its admin page. Keep the
"新建文章" action.

## Security and errors

All new routes use `@login_required` + `@admin_required`; mutations are POST
with CSRF through Flask-WTF forms (`DeleteForm`-style forms for toggles).
Non-admins get 403 (existing behaviour of the decorator). Database errors roll
back and flash the existing style messages. Passwords are only ever hashed
with `set_password`.

## Testing

pytest, written first:

- users: search, role filter, bad filter, create (success, duplicate username,
  duplicate email, allowed while registration is closed), edit (fields,
  duplicates, blank password keeps hash, new password changes hash, role
  rules), delete (article transfer, no-article delete, self, last admin,
  invalid receiver, CSRF, non-admin 403).
- pages: search, filters, updated time shown, publish/nav toggles (CSRF, state,
  query preserved), `/admin/about` and `/about/edit` gone, `/about` served by
  the generic route with no label/special class and redirects after slug change,
  nav no longer has "关于", admin nav matrix updated.
- dashboard: member sees only own-post card; admin sees all cards with links
  and correct counts.
- migration: `about` table dropped on upgrade, recreated on downgrade (same
  `create_all` + `stamp` approach as earlier migration tests).
- existing tests referencing `About`, `AboutForm`, `/about/edit`,
  `test_admin_about.py` are updated or removed.

Then browser verification (light, dark, 1440 / 390) of the user list, forms,
delete confirmation, page list and dashboard.
