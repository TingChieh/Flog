# Admin Workspace And Page CMS Design

## Goal

Separate public reading from content management by moving every create, edit,
delete, role, and site-configuration workflow into a role-aware `/admin`
workspace. Add a small page CMS that supports unlimited content pages and one
configurable page for each existing Todo, Movie, Links, and Guestbook module.

The public site remains focused on reading, likes, comments, follows, profiles,
and messages. It contains no create, edit, or delete controls.

## Roles And Access

The system has two persistent roles:

- `user`: can enter `/admin`, view the dashboard, create articles, and list,
  edit, or delete only articles they own;
- `admin`: has all user capabilities plus full article, page, module-data,
  category, comment, guestbook, and user-role management.

Every authorization rule is enforced in server-side queries and route guards.
Menu visibility is only a presentation layer and is never the security
boundary.

Administrators can promote or demote other users. They cannot demote
themselves, and no operation may demote the final administrator. Role changes
run in a transaction and recheck the administrator count before committing.

New registrations always receive the `user` role.

## Role Migration

`User` receives a persistent `role` column constrained to `user` or `admin`.
The migration initially assigns `user` to existing rows, then promotes
existing accounts whose normalized email appears in the current
`ADMIN_EMAILS` configuration.

If no existing account matches `ADMIN_EMAILS`, the migration stops with an
actionable error instead of completing a state in which nobody can administer
the site. After the migration succeeds, database roles become authoritative;
`ADMIN_EMAILS` is no longer consulted for normal authorization.

The migration and its operational instructions must be verified against MySQL
and the isolated SQLite test configuration. Tests must never inherit the
project's MySQL `DATABASE_URL`.

## Admin Architecture

A dedicated Flask Blueprint owns the `/admin` URL prefix. The public route
module no longer renders management forms or performs module-management POST
operations.

The administrator workspace uses a compact Apple-style operational layout:

- a top bar containing `Aisaka 管理`, the current user and role, and a
  `返回网站` link;
- a persistent desktop sidebar;
- a mobile drawer using the same navigation tree;
- a constrained, unframed work area with divided lists and compact forms;
- neutral monochrome surfaces consistent with the public redesign and its
  light/dark theme.

Ordinary users see:

- Overview;
- My articles;
- Create article.

Administrators additionally see:

- All articles;
- Page management;
- Categories;
- Comments and guestbook entries;
- Todo data;
- Movie data;
- Link data;
- Users and roles.

The sidebar adapts to the current role. Direct route access is separately
authorized.

## Admin Routes

The Blueprint provides these route groups:

- `/admin`: role-aware overview;
- `/admin/posts`: own articles for users, with an admin all-articles filter;
- `/admin/posts/new`;
- `/admin/posts/<id>/edit`;
- `/admin/posts/<id>/delete`;
- `/admin/pages`;
- `/admin/pages/new`;
- `/admin/pages/<id>/edit`;
- `/admin/pages/<id>/delete` for deletable content pages;
- `/admin/categories` and category mutation routes;
- `/admin/comments` for guestbook and article-comment moderation;
- `/admin/todos` and Todo mutation routes;
- `/admin/movies` and Movie mutation routes;
- `/admin/links` and Link mutation routes;
- `/admin/users`;
- `/admin/users/<id>/role`.

All mutation routes use POST and CSRF protection. GET routes do not mutate
data.

Unauthenticated access redirects to login and retains a safe return URL.
Authenticated users without the required role receive `403`. Article queries
for ordinary users include an owner predicate before fetching the target, so
identifier guessing cannot expose another user's management view.

## Legacy Management URLs

Existing edit and delete entry points remain temporarily as compatibility
routes. They perform authentication and authorization, then redirect GET
editing requests to the equivalent `/admin` page. Mutation compatibility is
kept only where a safe, CSRF-protected redirect cannot preserve semantics;
public templates stop emitting all legacy mutation URLs.

The compatibility layer is documented and can be removed in a later release
after old bookmarks and integrations have migrated.

## Page Model

The CMS introduces `Page` with:

- `id`;
- `title`;
- unique normalized `slug`;
- `summary`;
- sanitized rich-text `body`;
- `kind`, either `content` or `module`;
- nullable unique `module_key`;
- `is_published`;
- `show_in_nav`;
- `nav_order`;
- `created_at`;
- `updated_at`.

Content pages use `kind=content` and `module_key=NULL`. They may be created in
unlimited numbers.

Module pages use `kind=module` and exactly one of these module keys:

- `todo`;
- `movie`;
- `links`;
- `guestbook`.

The nullable unique `module_key` constraint allows multiple content pages but
prevents a second instance of a module page at the database level. Forms and
services enforce the same rule with readable validation messages.

The existing Todo, Movie, Link, and guestbook Comment tables remain unchanged
because each module is a singleton. Module page configuration controls its
title, slug, summary, publication, and navigation; the existing module tables
continue to hold the module's entries.

## Page Redirects And Slugs

`PageRedirect` stores a unique old slug and its destination page. When a page
slug changes, the previous slug becomes a redirect in the same transaction.

Public pages resolve through `/<slug>`, registered after all fixed application
routes. Slugs are lowercase, URL-safe, unique, and cannot use system-reserved
names including `admin`, `login`, `logout`, `register`, `post`, `user`,
`static`, `files`, `upload`, `rss`, and other current top-level endpoints.

Requests to an old slug redirect to the current canonical page URL. Redirect
chains are flattened to the current page. Deleting a content page deletes its
redirect records.

The initial module pages use the current public paths:

- `/todo`;
- `/movie`;
- `/links`;
- `/comment`.

The current About content migrates to a normal content page at `/about`.
Changing any of these slugs retains the original address as a redirect.

Unpublished pages return `404` on the public site, including direct URL
requests. They remain previewable inside the authorized admin workspace.

## Page Management Workflow

The administrator-only Page Management screen contains filters for all,
content, module, published, and unpublished pages. Each row shows title, slug,
kind, module identity, publication state, navigation state, and actions.

Administrators can create content pages and edit:

- title;
- slug;
- summary;
- rich-text body for content pages;
- published state;
- navigation visibility;
- navigation order.

Module pages can be configured or unpublished but cannot be deleted. Their
module key cannot be changed after creation. Content pages can be deleted after
an explicit confirmation.

The public navigation combines fixed product-level destinations with published
pages where `show_in_nav` is true, ordered by `nav_order` and then title.
Unpublished and navigation-hidden pages never appear in the public menu.

## Module Data Management

Page configuration and module entries are deliberately separate:

- Page Management controls how a module appears publicly;
- Todo Management creates, edits, completes, and deletes Todo entries;
- Movie Management creates, edits, and deletes movies;
- Link Management creates, edits, and deletes links;
- Comments and Guestbook Management moderates article comments and guestbook
  entries.

The public module templates become read-only presentations except for genuine
reader actions. Guestbook submission and article-comment submission remain
public reader actions. Moderation and deletion move to `/admin`.

## Article Management

The article editor and article-management controls exist only under `/admin`.
Ordinary users see only their own rows and cannot access another author's
editor or delete route. Administrators can view and manage all articles.

Public homepage, search, category, profile, and article-detail templates remove
all create, edit, and delete controls. They retain reading, likes, comment
submission, sharing/copy, profiles, follows, and messages.

## User Role Management

The administrator-only Users screen shows username, email, current role,
article count, and account metadata already available in the model. Role change
is an explicit POST action with CSRF protection and confirmation.

The service rejects:

- self-demotion;
- demotion of the final administrator;
- unknown roles;
- changes by non-administrators;
- missing or stale users.

It returns a clear flash message for each rejected operation without partially
updating the account.

## Public Navigation And Reading Separation

The public top navigation contains reader destinations and one role-neutral
`管理` entry for authenticated users. That link always targets `/admin`; the
workspace decides what the user can see.

Public templates contain no management forms or edit/delete buttons. This
includes articles, categories, About/content pages, Todo, movies, links,
guestbook entries, and comments. Server authorization remains enforced even
though controls are absent.

## Validation And Error States

Admin forms use visible labels, field-level errors, CSRF protection, stable
dimensions, and the existing monochrome light/dark tokens.

Validation covers:

- required and length-limited page titles;
- unique, normalized, reserved-word-safe slugs;
- unique module keys;
- required module-page configuration;
- valid publication and navigation states;
- integer navigation ordering;
- valid role values.

Deletion requires explicit confirmation and uses recoverable database
transactions. A failed mutation rolls back and shows an error without changing
the public page.

Empty admin lists use quiet in-flow empty states and an appropriate creation
action. No management section is hidden merely because it is empty.

## Testing

Automated coverage includes:

- role migration and `ADMIN_EMAILS` backfill;
- migration refusal when no configured existing administrator matches;
- registration defaulting to `user`;
- ordinary-user and administrator route-access matrices;
- article ownership filtering and direct-object-reference attempts;
- self-demotion and final-administrator protection;
- successful promotion and demotion of other users;
- Page CRUD;
- slug normalization, uniqueness, reserved words, and redirects;
- redirect flattening and cleanup on page deletion;
- module singleton database and form enforcement;
- module-page non-deletion and unpublishing;
- unpublished pages returning `404`;
- navigation visibility and ordering;
- module data CRUD and moderation permissions;
- compatibility redirects for legacy editor URLs;
- absence of management controls in public rendered HTML;
- CSRF rejection for every mutation group.

Every test run explicitly sets `DATABASE_URL=sqlite://` before importing the
application.

Browser verification covers:

- desktop and mobile admin layouts;
- sidebar and mobile drawer behavior;
- ordinary-user versus administrator menus;
- page list filters and long titles;
- Page and role form validation;
- public navigation generated from published pages;
- light and dark modes;
- public pages with no management controls;
- redirect behavior after changing a slug.

## Delivery Sequence

This CMS is an independent subproject built after the current Apple editorial
frontend changes. Implementation proceeds in this order:

1. role schema, migration, and authorization services;
2. admin Blueprint and shared workspace shell;
3. article-management migration and public-control removal;
4. Page and PageRedirect models plus public resolution;
5. module page seeding and module-data admin screens;
6. user-role management;
7. legacy-route compatibility;
8. complete automated and browser verification.
