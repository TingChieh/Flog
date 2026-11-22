# Article Tags and Series Design

## Current state

[`app/models.py`](../../../app/models.py) and the Alembic history define a single optional category per article and no tag or series tables. Published articles, `PostDraft`, and `PostRevision` store category independently. The article editor saves drafts through [`app/post_drafts.py`](../../../app/post_drafts.py) and copies the draft fields to `Post` on publication. The admin manages categories, and public discovery uses article IDs, the archive, categories, and search. There are no tag or series routes, templates, or admin controls.

Markdown and legacy HTML are stored in `Post.body`. The Markdown renderer has no front-matter extension. [`app/cli.py`](../../../app/cli.py) has a podcast import command. The repository has no active article importer or exporter. The old `/archives/<legacy_id>/` redirect and database backups provide URL and data continuity.

## Minimal schema

| Table | Columns and constraints |
| --- | --- |
| `tag` | Integer `id` primary key, `slug` (`VARCHAR(80)`, unique, required), display `name` (`VARCHAR(120)`, required). |
| `post_tag` | Composite primary key `(post_id, tag_id)`, foreign keys to `post` and `tag` with `ON DELETE CASCADE`, and index `(tag_id, post_id)` for a tag's article list. |
| `series` | Integer `id` primary key, unique required `slug` (`VARCHAR(80)`), required display `title` (`VARCHAR(120)`). |
| `series_post` | `post_id` primary key, required `series_id` and integer `position`, `CHECK (position > 0)`, unique `(series_id, position)`, and cascading foreign keys to `post` and `series`. The unique constraint also indexes series reads in position order. |

An article can have many tags and belong to one series. Gaps in positions are valid, including gaps left by unpublished or deleted articles. Use stable lowercase ASCII slugs with digits and interior hyphens. Validate the same normalized slug in admin and import code so MySQL/MariaDB collation and SQLite uniqueness behave consistently. Display names and titles can be Chinese and can change while the slug stays fixed. Removing a tag or series removes its memberships and preserves the articles.

## Migration and rollback

1. Add a reviewed Alembic revision creating `tag` and `series` before `post_tag` and `series_post`. Give constraints and indexes explicit names. Leave existing article, category, draft, and revision rows intact. Start with empty taxonomy tables and assign memberships explicitly.
2. Rehearse upgrade, constraints, and downgrade against disposable copies of the current schema on SQLite (with foreign keys enabled) and MariaDB. Verify duplicate memberships, duplicate series positions, invalid references, cascades, and survival of legacy post IDs and bodies. Check MySQL/MariaDB DDL failure recovery because individual DDL statements can commit independently.
3. For rollback after taxonomy writes begin, run the Alembic downgrade while still on the build that contains the taxonomy revision, before resetting the application checkout:
   - Stop writers (for example, `systemctl stop <service>` or enter a maintenance window) and export taxonomy tables and memberships, or confirm a verified database backup is in place.
   - From the current (new) build whose `migrations/versions/` still contains the taxonomy revision, downgrade the database to the pre-taxonomy revision (`<db_before>`):
     ```bash
     flask db downgrade <db_before>
     ```
     The Alembic downgrade drops both association tables (`post_tag`, `series_post`) before their parents (`tag`, `series`). Do not `git reset` to the older build first: the older build lacks the taxonomy revision file, so Alembic cannot locate the database's current revision and `downgrade` fails.
   - Roll the application back to the pre-taxonomy build (`<old_commit>`), confirm `flask db current` matches `<db_before>`, and restart the service:
     ```bash
     git reset --hard <old_commit>
     flask db current
     systemctl restart <service>
     ```
   A downgrade removes taxonomy data, so keep the export or verified backup for recovery.

## Public and admin behavior

- Add paginated `/tag/<slug>` and `/series/<slug>` routes. Use the article discovery visibility rule (`is_published` and publication time at or before the current UTC time) for both membership queries and any tag or series counts. Return 404 for unknown slugs and for collections with no public articles. Order tag lists by `(timestamp DESC, id DESC)` and series lists by `position ASC`. Keep article IDs and canonicals. Leave taxonomy URLs out of feeds and the sitemap during the first public stage.
- Render tags and an optional series link beside the article's existing discovery controls. Fetch them before rendering, select titles and IDs for series navigation, and keep query counts independent of list length. An unpublished member cannot contribute a title, link, count, or sequence label. Keep displayed neighbor labels relative to the visible entries.
- Start with a separate taxonomy editor restricted to admins. Save metadata explicitly and transactionally. Changes to a public article's taxonomy take effect when the admin saves. Draft-only articles remain hidden, and autosave, publication of body changes, and revision restoration leave taxonomy memberships alone. When reordering, validate the full submitted membership set and replace its positions in one serialized transaction to avoid transient uniqueness collisions during a swap. Lock the affected series rows in ID order on MariaDB and serialize the write transaction on SQLite.

## Markdown and data exchange

Preserve Markdown, legacy HTML, and literal front matter as stored for existing articles. For future interchange, use a versioned structured metadata manifest with nullable series membership, explicit position, and tag slugs. Export slugs with display names and preserve the source body separately. During dry runs, validate article identity, slugs, and conflicts before any write. Upsert by stable identifiers, treat absent taxonomy fields as unchanged for legacy inputs, and use explicit empty values to clear membership. A future importer may map opt-in front matter into the manifest fields. Keep that parser on the import path so rendering, excerpts, and old posts retain their current behavior.

## Rollout and risks

1. Rehearse the additive schema and rollback with a disposable database and representative data. Verify the live application can continue using its existing tables during a schema-only rollout.
2. Enable admin-only editing after testing authorization, duplicate slugs, concurrent reorders, cascades, and round-trip interchange for the metadata format. Audit taxonomy before enabling public reads.
3. Release filtered public views after tests cover draft and future membership, empty collections, stable pagination, redirects, query budgets, and mobile rendering. Series order is editorial and stays independent of republishing dates. Review the lookup plans at real data volumes before adding any indexes beyond those in the schema.

Round 2 delivers this design without schema or taxonomy UI changes. A throwaway Alembic Operations prototype on a disposable SQLite database at the current migration head verified the proposed tables, constraints, cascades, public series order, and preservation of pre-existing article rows during downgrade. Run the corresponding rehearsal on MariaDB when implementing the versioned migration.
