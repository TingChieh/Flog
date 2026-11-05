# Article View Count Design

Date: 2026-08-21
Status: Approved for implementation planning

## Goal

Add a lightweight article view count that gives readers and administrators a
useful indication of readership without storing visitor identities or adding a
separate analytics system.

A view is counted at most once per browser, per article, during a rolling
24-hour window. Authenticated users, article authors, and administrators follow
the same rule when they use the public article page.

## Scope

The following request counts as a view:

- A valid `GET /post/<post_id>` request for an existing article when that
  browser has no valid 24-hour marker for the article.

The following requests do not count:

- Comment form `POST` requests.
- Article list, category, search, feed, or RSS requests.
- Administrative editing and preview requests.
- Requests for missing articles.

Bot detection, unique-person analytics, historical event reporting, and
fraud-resistant counting are explicitly outside this feature's scope. A visitor
who clears or blocks cookies can be counted again.

## Selected Approach

Use one short-lived, signed cookie per viewed article. The cookie is scoped to
that article's public URL and expires after 24 hours. This approach avoids
persisting anonymous browser identifiers and does not depend on the application's
process-local `SimpleCache`.

Alternatives considered:

1. A single cookie containing all recently viewed article IDs was rejected
   because its size grows with browsing activity and requires eviction logic.
2. A database-backed anonymous visitor and view table was rejected because it
   adds retention, cleanup, privacy, and concurrency complexity that is not
   justified for the current blog.

## Data Model And Migration

Add this field to `Post`:

- `view_count`: non-null integer, application default `0`, database default
  `0`.

The Alembic migration adds `post.view_count` with a server default of zero.
MySQL therefore backfills all existing rows without changing article content.
The server default remains in place so inserts outside the ORM cannot create a
null counter. Downgrade removes only the new column.

No per-visitor or per-view rows are stored in the database.

## Cookie Design

Each article uses a cookie whose name includes the article ID, for example
`post_viewed_42`. Its signed payload identifies the same article. A timestamped
signature derived from `SECRET_KEY` prevents a client from manufacturing a
valid marker and allows the server to enforce the 24-hour age even if a client
changes the cookie expiry metadata.

Cookie attributes:

- `Max-Age`: 86,400 seconds.
- `Path`: the article's public path, such as `/post/42`.
- `HttpOnly`: enabled.
- `SameSite`: `Lax`.
- `Secure`: follows the application's secure-cookie configuration so production
  HTTPS can require secure transport while local HTTP tests continue to work.

The 24-hour duration is exposed as application configuration with 86,400 as the
production default. This keeps time-window behavior testable without waiting in
real time.

Missing, expired, malformed, or incorrectly signed cookies are treated as no
marker. They never prevent the article page from loading.

## Request Flow

The public article route keeps comment creation separate from view counting:

1. Resolve the article or return 404.
2. For `POST`, validate and save the comment using the existing flow; never
   inspect or write a view cookie.
3. For `GET`, validate the article-specific view cookie.
4. If the marker is valid and younger than 24 hours, render without updating
   the counter.
5. Otherwise, execute an atomic database expression equivalent to
   `UPDATE post SET view_count = view_count + 1 WHERE id = :post_id` and commit.
6. Refresh or synchronize the in-memory article so the response displays the
   newly committed count.
7. Render the response and attach the signed 24-hour cookie only when the
   counter update committed successfully.

The increment must be an SQL expression, not a Python read-modify-write, so two
concurrent first visits cannot overwrite each other's increments.

Cookie validation and counter mutation belong in a small dedicated helper or
service module. The route remains responsible for choosing GET versus POST and
attaching the cookie to the final response.

## Error Handling

Counting is secondary to serving the article. If cookie parsing fails, the
request proceeds as an unmarked visit. If the counter update or commit fails,
the application rolls back the transaction, records the exception, renders the
article normally, and does not set the view cookie. A later request can retry
the count.

An analytics failure must not turn a readable article into a 500 response. The
helper must leave the SQLAlchemy session usable after rollback so template
rendering and later requests are unaffected.

The comment-writing transaction remains independent. A failed comment submit
must not increment the view count, and a view-count failure must not interfere
with comment validation or persistence.

## Presentation

Display the count in the existing article metadata area:

- On the public article detail page.
- In the shared article list item partial used by public listings.

The value is plain metadata alongside the existing date, category, comment, or
like information. It does not become an interactive control. Zero is displayed
normally so newly migrated articles have a predictable layout.

## Test Strategy

Model and migration coverage:

- New posts default to zero.
- The migration makes existing rows zero and disallows null values.
- The migration downgrade removes only the counter column.

Request and service coverage:

- The first anonymous GET increments and sets a correctly scoped cookie.
- Repeated GETs with the valid cookie do not increment within 24 hours.
- An expired, malformed, or incorrectly signed cookie increments again.
- Viewing two different articles increments each independently.
- Logged-in users, authors, and administrators use the same cookie rule.
- Comment POST requests never increment or refresh the marker.
- Missing articles and non-detail surfaces do not increment.
- The update uses a database-side arithmetic expression.
- A database error is rolled back, logged, serves the article, and does not set
  the cookie.

Template coverage:

- Article detail renders the current count.
- Shared public article listings render the current count.
- Existing public controls and administrative visibility rules remain intact.

The complete existing test suite must pass after the focused tests.

## Operational Notes

Deployment order remains migration first, application code second. Running new
code before the migration would query a missing `post.view_count` column, so the
production release procedure must run `flask db upgrade` before restarting the
application, following the same discipline used for earlier role and content
format migrations.

