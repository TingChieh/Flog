# Admin Environment Configuration Design

Date: 2026-09-14
Status: Approved for specification review

## Goal

Add an administrator-only system page that can inspect the application's
managed `.env` configuration, validate its values, test dependent services,
and safely update the file. Saving changes does not hot-reload the running
Flask process; the page clearly tells the administrator to restart the
application before the new configuration becomes active.

The feature is an operational aid for this single Flog deployment, not a
general-purpose environment editor or secret-management system.

## Selected Approach

Add a dedicated `.env` configuration page under the existing admin blueprint,
backed by a small environment-document service and a separate validation and
connectivity-check service. Only an explicit allowlist of Flog settings is
editable. Local validation and external connectivity checks remain separate so
an administrator can distinguish malformed configuration from an unavailable
dependency.

Alternatives considered:

1. Extending the existing database-backed website settings form was rejected
   because deployment configuration and runtime content settings have different
   persistence, security, and restart semantics.
2. A free-form text editor for the complete `.env` file was rejected because it
   would expose secrets, permit accidental edits to unrelated variables, and
   make field-level validation impractical.
3. Hot-reloading Flask extensions after saving was rejected because database,
   Redis, mail, signing-key, and queue objects are initialized at process start.
   Partially replacing them would leave the process in an inconsistent state.

## Managed Configuration

The page manages only these documented variables:

- Core: `SECRET_KEY`, `ADMIN_EMAILS`.
- Database: `DATABASE_URL`.
- Redis and tasks: `REDIS_URL`.
- Mail: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_SSL`, `MAIL_USERNAME`,
  `MAIL_PASSWORD`.
- Uploads: `UPLOAD_FOLDER`.
- Translation: `APPID`, `BD_TRANSLATOR_KEY`, `MS_TRANSLATOR_KEY`.
- Search: `ELASTICSEARCH_URL`.

Unknown variables, comments, and blank lines already present in `.env` are
retained byte-for-byte but are neither displayed nor editable. Existing
managed assignment lines may be re-quoted when their value changes. The code never accepts a
client-supplied variable name, which prevents the page from becoming an
arbitrary file or process configuration editor.

The `.env` path is application configuration with the project-root `.env` as
the production default. Tests override it with a temporary path. The resolved
path must refer to that configured file; request data cannot select another
file.

## Access And Security

Every page and mutation requires login plus the existing `admin_required`
authorization decorator. Every POST uses Flask-WTF CSRF protection.

`SECRET_KEY`, `DATABASE_URL`, `MAIL_PASSWORD`, `BD_TRANSLATOR_KEY`, and
`MS_TRANSLATOR_KEY` are sensitive. Their complete values are never rendered
into HTML, flash messages, logs, or connectivity results. The page shows only
whether each is configured and a short fixed mask. A blank sensitive input
means "keep the existing value." Replacing one requires entering the complete
new value. Clearing one requires a separate explicit checkbox, and local
validation may then report that a required or dependency-specific value is
missing.

Non-sensitive managed values are rendered in editable fields. Error responses
must also avoid reflecting submitted secrets. URLs are sanitized before they
are shown in results or logs so embedded usernames, passwords, query strings,
and fragments cannot leak.

Application logs record the administrator identity, the names of changed
variables, and the outcome and duration of checks. They never record old or new
values, exception representations that may contain credentials, or request
form bodies.

## Page And Interaction Design

Add `环境配置` to the existing administrator-only `系统` navigation group.
The page uses the current admin layout and groups fields into core, database,
Redis, mail, uploads, translation, and search sections.

Each field displays a local status such as configured, optional and empty,
invalid, or overridden. The page includes these actions:

- `检查配置`: validates the current form draft without contacting external
  systems or writing the file.
- A service-level `检测连接` action for database, Redis, SMTP, uploads,
  translation, and Elasticsearch.
- `一键检测全部`: runs every applicable service check against the current
  form draft.
- `保存配置`: validates and atomically writes the managed changes.

Connectivity actions use the current draft, merged with retained sensitive
values whose input is blank. This lets an administrator test a proposed value
before saving it. The returned page contains a per-service result with status,
safe explanatory text, and elapsed time. Services without enough configuration
are marked `未配置`, not failed.

After a successful save, the page redirects using POST/Redirect/GET and flashes
that the `.env` file was updated and the application must be restarted. The
running Flask configuration and initialized extensions remain untouched.

## Local Validation

Validation produces field errors and a page-level summary. It covers:

- `SECRET_KEY`: required, not the example placeholder, and long enough for
  session and token signing.
- `ADMIN_EMAILS`: a comma-separated list of syntactically valid addresses;
  empty remains allowed but is reported as a warning.
- `DATABASE_URL`, `REDIS_URL`, and `ELASTICSEARCH_URL`: supported URL shape,
  required scheme where applicable, and valid port syntax. URLs are parsed
  without opening a connection.
- `MAIL_PORT`: integer from 1 through 65535.
- `MAIL_USE_SSL`: normalized boolean value.
- Mail credentials: username and password must either both be present or both
  absent when authentication is configured.
- Baidu translation: `APPID` and `BD_TRANSLATOR_KEY` must be supplied together.
- `UPLOAD_FOLDER`: non-empty path; relative paths are resolved using the same
  project-root rule as application configuration and reported clearly.

Optional services do not make the whole configuration invalid merely because
they are absent. Instead, the page reports them as not configured. Validation
errors prevent both saving and external checks that depend on the invalid
fields.

## Connectivity Checks

All checks are explicit administrator POST actions, have short bounded
timeouts, release connections after use, and do not mutate application data.
One failing check does not stop the remaining checks in `一键检测全部`.

- Database: create an isolated temporary SQLAlchemy engine from the draft URL,
  execute `SELECT 1`, and dispose the engine. It never reuses or replaces the
  application's active database engine.
- Redis: create a temporary client from the draft URL, issue `PING`, and close
  its connection pool. It does not enqueue or remove jobs.
- SMTP: establish the configured SSL or plain connection, upgrade with
  `STARTTLS` when the non-SSL server advertises it, and authenticate when
  credentials are present. It never sends a message.
- Uploads: verify that the resolved directory exists or that its nearest
  existing parent permits creation, and verify write access without leaving a
  persistent test file.
- Baidu and Microsoft translation: when the corresponding credentials are
  configured, make the smallest supported translation request with a fixed
  harmless test string and treat authentication and API errors as failures.
- Elasticsearch: make a lightweight health/info request and accept only a
  valid server response.

Results classify timeout, authentication rejection, name resolution or
connection failure, invalid response, and success. User-facing messages are
short and sanitized. Detailed exceptions may be logged only after credential
and URL sanitization.

## File Read And Write Semantics

The environment-document service reads `.env` without modifying
`os.environ`. It parses managed assignments while retaining comments, blank
lines, ordering, quoting, and unknown lines. Duplicate managed assignments are
treated as a validation error rather than guessing which one to edit.

Saving follows this sequence:

1. Re-read the file and compare its content fingerprint with the fingerprint
   issued when the form was loaded or last checked.
2. Reject the save with a refresh instruction when the fingerprint changed,
   preventing an external edit from being overwritten.
3. Merge submitted managed values with retained sensitive values.
4. Run complete local validation.
5. Render updated managed assignments while preserving unrelated content.
6. Write a temporary file in the same directory, flush and synchronize it,
   preserve restrictive file permissions, then use an atomic replace.
7. Re-read the saved document and verify that the intended managed values can
   be parsed.

If `.env` does not exist, the service creates it with owner-only permissions
and only the managed values submitted by the administrator. It does not create
a second backup containing secrets. Any failure before atomic replacement
leaves the prior file intact; temporary files are cleaned up.

## Error Handling

An unreadable `.env`, duplicate keys, malformed lines, validation errors, stale
fingerprints, filesystem permission errors, and failed connectivity checks
render actionable messages without exposing values. A missing `.env` is a valid
empty starting state and may be created on the first successful save.

A read failure makes the form read-only except for refresh. A save failure does
not change the running configuration and must leave the previous `.env`
content intact. Connectivity failures never save values and never make the
admin page itself return a server error. Unexpected exceptions are logged in a
sanitized form and shown as a generic failure.

## Components

The implementation keeps these responsibilities separate:

- An environment schema defines the allowlist, labels, groups, sensitivity,
  defaults, dependency rules, and validation rules.
- An environment-document service parses, fingerprints, merges, and atomically
  writes `.env` without touching process environment variables.
- A validation service returns structured field errors and warnings.
- A connectivity service exposes one checker per external dependency and
  returns a common sanitized result type.
- An admin form and route coordinate authorization, CSRF, requested action,
  logging, redirect behavior, and template rendering.

The document and connectivity services receive paths, values, and client or
engine factories explicitly so their behavior can be tested without accessing
the real project `.env` or production services.

## Test Strategy

Environment document tests cover parsing, unknown-line and comment
preservation, quoting, missing files, duplicate managed keys, permission
preservation, atomic replacement failure, post-write verification, and stale
fingerprint rejection.

Validation tests cover every field rule, paired credentials, optional service
groups, placeholders, URL credential sanitization, and secret-safe errors.

Connectivity tests use local fakes or injected factories and cover success,
timeout, authentication failure, invalid response, resource cleanup, and
continuing other checks after one failure. No test contacts a real database,
Redis, SMTP, translation, or Elasticsearch service.

Admin request tests cover:

- Anonymous users are redirected and non-admin members receive 403.
- Administrators can view the page and navigation link.
- Rendered HTML never contains configured sensitive values.
- Blank secret fields retain values; explicit clear and replacement behave as
  designed.
- Unmanaged variable names cannot be submitted for modification.
- CSRF protects validation, detection, and saving actions.
- Invalid drafts and stale fingerprints do not alter the file.
- Detection uses draft values without saving them.
- Successful saving uses POST/Redirect/GET and shows the restart requirement.
- Logs contain variable names and outcomes but no secret values.

The focused test files and the complete existing Python test suite must pass.
Existing JavaScript tests must also remain green; no new client-side JavaScript
is required for the initial version.

## Operational Notes

The web process must have read and write permission for `.env`; otherwise the
page remains useful for diagnosis but saving reports a permission error. In
container deployments, an injected process environment may override values in
`.env`. The page reports when the currently active process value differs from
the file, but it cannot update an orchestrator, secret store, or container
environment.

Saving `SECRET_KEY` invalidates existing sessions and signed tokens after the
restart. Saving database or Redis settings can make the restarted application
unavailable if the dependency later becomes unreachable, even when an earlier
check succeeded. The UI therefore presents connectivity results as a
point-in-time check rather than a deployment guarantee.
