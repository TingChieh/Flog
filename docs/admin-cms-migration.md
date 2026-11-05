# Admin CMS MySQL Migration Runbook

> **Note:** this runbook describes the upgrade to revision `9c8e2f3a4b5d`, which
> seeded the four module pages. Revision `bad2dd157a5f` later removes the module
> pages and the `todo`, `movie`, `link` and `comment` tables permanently; take a
> backup before upgrading past it.

Use a maintenance window. Do not run the live upgrade until the backup exists,
the scratch restore succeeds, and `ADMIN_EMAILS` matches at least one existing
account.

## Preflight

```bash
flask db current
flask db heads
mysql --database=flog -e "SELECT id, username, email FROM user ORDER BY id;"
mysql --database=flog -e "SELECT COUNT(*) FROM user WHERE LOWER(email) IN ('normalized-admin@example.com');"
```

The current revision must be `5c1f31ac842e` or later, there must be exactly one
Alembic head, and the final query must return at least one row. Correct
`ADMIN_EMAILS` before proceeding if it returns zero.

## Backup And Scratch Rehearsal

```bash
stamp=$(date +%Y%m%d-%H%M%S)
mysqldump --single-transaction --routines --triggers flog \
  > "instance/backups/flog-before-admin-cms-${stamp}.sql"
mysql -e "CREATE DATABASE flog_admin_cms_scratch CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql flog_admin_cms_scratch < "instance/backups/flog-before-admin-cms-${stamp}.sql"
DATABASE_URL='mysql+pymysql://USER:PASSWORD@localhost/flog_admin_cms_scratch' \
  ADMIN_EMAILS='existing-admin@example.com' flask db upgrade
```

Inspect the scratch database before touching the live database:

```sql
SELECT version_num FROM alembic_version;
SELECT role, COUNT(*) FROM user GROUP BY role;
SELECT slug, kind, module_key, is_published, show_in_nav, nav_order
FROM page ORDER BY nav_order;
SELECT COUNT(*) FROM page WHERE kind = 'module';
SHOW CREATE TABLE page;
SHOW CREATE TABLE page_redirect;
```

Expected results are revision `9c8e2f3a4b5d`, at least one administrator, five
seeded pages, and exactly one row for each module key: `todo`, `movie`, `links`,
and `guestbook`.

## Live Upgrade

After the scratch checks pass and the site is in maintenance mode:

```bash
flask db upgrade
flask db current
```

Repeat the role and page postflight queries above. Smoke-test administrator
login, `/admin/users`, `/admin/pages`, one public content page, every module
page, an unpublished page returning 404, and an old slug redirect.

## Rollback And Restore

The downgrade removes page metadata and stored roles, so prefer restoring the
backup into a separate database when a live upgrade fails. Keep the failed
database unchanged until the restore has been verified:

```bash
mysql -e "CREATE DATABASE flog_restore_YYYYMMDD_HHMMSS CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql flog_restore_YYYYMMDD_HHMMSS \
  < "instance/backups/flog-before-admin-cms-${stamp}.sql"
DATABASE_URL='mysql+pymysql://USER:PASSWORD@localhost/flog_restore_YYYYMMDD_HHMMSS' \
  flask db current
```

Run the application postflight checks against the restored database, then
switch the deployed `DATABASE_URL` to that verified database and restart the
application. Any later cleanup or in-place repair of the failed database needs
a separate, reviewed database-specific plan.

For a controlled application rollback where data loss is accepted:

```bash
flask db downgrade 5c1f31ac842e
```

Keep the maintenance window active until the application and database revision
are aligned. Never run automated tests against the MySQL URL; tests must use
`DATABASE_URL=sqlite://`.
