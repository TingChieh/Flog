# Remove Private Messages, User Profiles And Post Export

## Goal

Delete private messages, public user profile pages (with the profile edit form
and hover popover) and the "export my posts" background job, together with the
`Task` and `Notification` models that only these features used. The site keeps
articles, categories, custom content pages, search, archive, RSS, article
comments, registration, login and password reset.

This is irreversible for the message data: the `message`, `notification` and
`task` tables are dropped. The owner chose to delete the export feature
together with the profile page rather than move its entry to the admin.

## What Is Removed

**Private messages**: routes `/messages` and `/send_message/<recipient>`; the
`Message` model and the `messages_sent` / `messages_received` relationships;
`User.unread_message_count()`; `MessageForm`; templates `_message.html`,
`messages.html`, `send_message.html`; the `messages` entry in the reserved
slugs stays (the URL should not become a custom page by accident).

**User profiles**: routes `/user/<username>`, `/user/<username>/popup` and
`/edit_profile`; `EditProfileForm`; templates under `app/templates/user/` that
belong to the profile (`user.html`, `user_popup.html`) and `edit_profile.html`
(`login.html`, `register.html` and the password-reset templates stay); the
popover script in `base.html`. On the article page the author name and avatar
become plain text and an image with no link.

**Export job**: route `/export_posts`; `app/tasks.py`; email templates
`email/export_posts.html` and `.txt`; `User.launch_task`,
`get_tasks_in_progress`, `get_task_in_progress` and the `tasks` relationship;
the `Task` model.

**Notifications**: route `/notifications`; the `Notification` model,
`User.add_notification` and the `notifications` relationship; in `base.html`
the task-progress banner and the polling script; `app.task_queue` and the `rq`
requirement (`requirements.in` / `requirements.txt`); the `/test_redis` debug
route.

**Shell context and docs**: `Message`, `Notification` and `Task` leave
`flog.py`'s shell context; the README drops the profile, message, export and
RQ worker instructions.

## What Stays

- `User.last_seen` and the `before_request` update (the admin user list shows
  it). `User.about_me` stays as an unused column; the `user` table is not
  altered.
- Registration, login, password reset and `app/email.py`.
- The Redis connection object `app.redis` and the `REDIS_URL` setting with its
  connectivity check in the admin environment page. They no longer have a
  consumer other than that check; removing them would pull in the environment
  validation code and its tests, so it is left as a possible follow-up.
- The `redis` package (used by the environment check).

## Database Migration

A new Alembic revision on top of the current head `bad2dd157a5f`.

Upgrade: for each of `message`, `notification`, `task`, if the table exists,
log its row count and drop it. Downgrade: recreate the three tables empty with
their current model columns, indexes and foreign keys to `user`. Data is not
restored. The migration uses only SQLAlchemy operations; MySQL is not testable
here and the owner must back up the database before upgrading.

## Testing

- Migration tests modelled on `test_module_removal_*`: upgrade drops the three
  tables and keeps `user` and `post` rows; a missing table is tolerated;
  downgrade recreates three empty tables; there is a single head.
- Behaviour tests: `/messages`, `/user/<name>`, `/user/<name>/popup`,
  `/edit_profile`, `/send_message/x`, `/export_posts`, `/notifications` and
  `/test_redis` are 404 (or 405 for POST-only shapes); the article page shows
  the author name without a link and without an `user_popup` class; the base
  template no longer contains the notification polling script.
- Delete tests that covered the removed features: all of `tests/test_tasks.py`
  and `tests/test_public_profiles.py`, and the profile, message and export
  parts of `test_ui_pages`, `test_public_pages_consistency`,
  `test_roles`, `test_security`, `test_post_interactions` and others as
  the full-suite run reveals. A test is deleted only when it exercises a
  removed feature.
- Full `pytest` with `DATABASE_URL=sqlite://` and `node --test tests/*.test.js`.

## Manual Verification

Seed a scratch SQLite database on the new schema (`db.create_all()`), then run a
second scratch database through `flask db stamp bad2dd157a5f` and
`flask db upgrade` with rows in the three tables to confirm the logged counts.
With playwright, check an article page (author name is not a link), a signed-in
home page (no polling errors in the console) and that the removed URLs return
the 404 page.

## Delivery

On branch `feat/remove-messages-profiles`, four commits after the spec and plan:
1. migration and its tests;
2. routes, templates, forms and the `base.html` scripts (private messages,
   profiles, popover, export and notification routes, the article author link);
3. the `Message`, `Notification` and `Task` models, `app/tasks.py`, the queue
   and the `rq` and `croniter` requirements;
4. CSS, README, translations and final verification.

Commit 2 combines what was planned as separate steps because the routes
reference each other (`redirect(url_for('user'))`, `url_for('notifications')`
in `base.html`), so none of them can be removed alone with a green suite.
Each commit leaves the full test suite green.
