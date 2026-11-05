# Admin Environment Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an administrator-only page that safely inspects, validates, connectivity-tests, and atomically updates Flog's allowlisted `.env` settings.

**Architecture:** Keep environment schema and local validation, line-preserving file persistence, and external connectivity checks in three independent modules. A dedicated admin controller merges blank secret inputs with retained values, invokes those services, and renders sanitized structured results without mutating the running Flask configuration.

**Tech Stack:** Python 3.13, Flask 3.1, Flask-WTF/WTForms, python-dotenv, SQLAlchemy 2, redis-py 6, requests 2, Python `smtplib`, Jinja2, CSS, Pytest.

## Global Constraints

- Only `SECRET_KEY`, `ADMIN_EMAILS`, `DATABASE_URL`, `REDIS_URL`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_SSL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `UPLOAD_FOLDER`, `APPID`, `BD_TRANSLATOR_KEY`, `MS_TRANSLATOR_KEY`, and `ELASTICSEARCH_URL` are managed.
- `SECRET_KEY`, `DATABASE_URL`, `MAIL_PASSWORD`, `BD_TRANSLATOR_KEY`, and `MS_TRANSLATOR_KEY` are sensitive and must never be rendered or logged in full.
- A blank sensitive field retains its existing value; clearing it requires that field's explicit clear checkbox.
- Configuration checks and connectivity checks use the current form draft and never write the file.
- Saving updates `.env` atomically, preserves comments and unmanaged lines, rejects stale fingerprints, and never updates `os.environ`, `app.config`, or initialized extensions.
- Every route requires login, administrator authorization, and CSRF protection for POST requests.
- Every network operation has a bounded timeout, returns sanitized output, and releases its resources.
- Tests must override `ENV_FILE_PATH` with a temporary path and must never read or write the repository's real `.env`.
- Tests must not contact real database, Redis, SMTP, translation, or Elasticsearch services.
- No client-side JavaScript is required for the initial version.

---

## File Structure

- Create `app/env_config.py`: allowlisted field metadata, candidate-value merging, local validation, and safe URL/message sanitization.
- Create `app/env_file.py`: line-preserving `.env` parsing, content fingerprints, and atomic writes.
- Create `app/env_checks.py`: isolated connectivity checks with one common result type.
- Create `app/admin/env_settings.py`: admin-only GET/POST orchestration and secret-safe audit logging.
- Create `app/templates/admin/settings/environment.html`: grouped editor and status/result presentation.
- Create `tests/test_env_config.py`: schema, merge, validation, and sanitization unit tests.
- Create `tests/test_env_file.py`: parsing, preservation, fingerprint, permission, and failure-safety tests.
- Create `tests/test_env_checks.py`: dependency checks, timeouts, sanitization, cleanup, and batch isolation tests.
- Create `tests/test_admin_env_settings.py`: access control, form behavior, CSRF, saving, and non-disclosure request tests.
- Modify `config.py`: add the overridable project-root `ENV_FILE_PATH`.
- Modify `app/admin/forms.py`: add the explicit allowlisted environment form fields.
- Modify `app/admin/__init__.py`: import the new route module.
- Modify `app/templates/admin/base.html`: add the administrator navigation link.
- Modify `app/static/style.css`: add responsive environment section and result styles.
- Modify `tests/test_admin_access.py`: include the new GET route in existing access matrices.
- Modify `README.md`: document the admin environment page, restart semantics, and deployment override limitation.

---

### Task 1: Environment Schema, Draft Merge, Validation, And Sanitization

**Files:**
- Create: `app/env_config.py`
- Create: `tests/test_env_config.py`
- Modify: `config.py:6-35`

**Interfaces:**
- Produces: `EnvField(key: str, label: str, group: str, sensitive: bool = False)`.
- Produces: `ENV_FIELDS: tuple[EnvField, ...]`, `MANAGED_KEYS: frozenset[str]`, and `SENSITIVE_KEYS: frozenset[str]`.
- Produces: `ValidationReport(errors: dict[str, list[str]], warnings: dict[str, list[str]])` with `is_valid: bool`.
- Produces: `merge_draft(existing: Mapping[str, str], submitted: Mapping[str, str], clear_keys: AbstractSet[str]) -> dict[str, str]`.
- Produces: `normalize_env(values: Mapping[str, str]) -> dict[str, str]`.
- Produces: `find_active_overrides(file_values: Mapping[str, str], environ: Mapping[str, str]) -> frozenset[str]`.
- Produces: `validate_env(values: Mapping[str, str], project_root: Path) -> ValidationReport`.
- Produces: `sanitize_url(value: str) -> str` and `sanitize_message(message: str, values: Mapping[str, str]) -> str`.
- Produces: `Config.ENV_FILE_PATH`, defaulting to `basedir / '.env'`.

- [ ] **Step 1: Write failing schema and merge tests**

Create tests that name the production behavior directly:

```python
from app.env_config import MANAGED_KEYS, SENSITIVE_KEYS, merge_draft


def test_managed_keys_are_the_documented_allowlist():
    assert MANAGED_KEYS == frozenset({
        'SECRET_KEY', 'ADMIN_EMAILS', 'DATABASE_URL', 'REDIS_URL',
        'MAIL_SERVER', 'MAIL_PORT', 'MAIL_USE_SSL', 'MAIL_USERNAME',
        'MAIL_PASSWORD', 'UPLOAD_FOLDER', 'APPID', 'BD_TRANSLATOR_KEY',
        'MS_TRANSLATOR_KEY', 'ELASTICSEARCH_URL',
    })


def test_merge_draft_retains_blank_secrets_and_ignores_unknown_keys():
    result = merge_draft(
        {'SECRET_KEY': 'existing-secret', 'MAIL_SERVER': 'old.example'},
        {'SECRET_KEY': '', 'MAIL_SERVER': 'new.example', 'EVIL': 'value'},
        clear_keys=set(),
    )
    assert result['SECRET_KEY'] == 'existing-secret'
    assert result['MAIL_SERVER'] == 'new.example'
    assert 'EVIL' not in result


def test_merge_draft_only_clears_allowlisted_sensitive_key_explicitly():
    result = merge_draft(
        {'MAIL_PASSWORD': 'existing-secret'},
        {'MAIL_PASSWORD': ''},
        clear_keys={'MAIL_PASSWORD', 'UNMANAGED'},
    )
    assert result['MAIL_PASSWORD'] == ''
    assert 'UNMANAGED' not in result
```

- [ ] **Step 2: Run the merge tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_config.py -k 'managed_keys or merge_draft'`

Expected: collection fails because `app.env_config` does not exist.

- [ ] **Step 3: Implement the schema and minimal draft merge**

Use immutable metadata and filter all client-controlled mappings through the allowlist:

```python
@dataclass(frozen=True)
class EnvField:
    key: str
    label: str
    group: str
    sensitive: bool = False


def merge_draft(existing, submitted, clear_keys):
    result = {key: existing.get(key, '') for key in MANAGED_KEYS}
    for field in ENV_FIELDS:
        value = (submitted.get(field.key) or '').strip()
        if field.sensitive and not value and field.key not in clear_keys:
            continue
        result[field.key] = value
    return result
```

- [ ] **Step 4: Run the merge tests and verify GREEN**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_config.py -k 'managed_keys or merge_draft'`

Expected: all selected tests pass.

- [ ] **Step 5: Write failing validation and sanitization tests**

Cover a valid minimal SQLite configuration, short/placeholder secrets, malformed emails, URL/port errors, paired mail and Baidu credentials, optional empty services, boolean normalization, upload paths, and removal of URL credentials and literal secrets:

```python
def test_validate_env_accepts_minimal_configuration(tmp_path):
    report = validate_env({
        'SECRET_KEY': 'x' * 32,
        'DATABASE_URL': 'sqlite://',
        'MAIL_PORT': '465',
        'MAIL_USE_SSL': 'true',
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
    }, tmp_path)
    assert report.is_valid
    assert report.errors == {}


def test_validate_env_rejects_placeholder_secret_and_partial_credentials(tmp_path):
    report = validate_env({
        'SECRET_KEY': 'replace-with-a-long-random-value',
        'DATABASE_URL': 'sqlite://',
        'MAIL_PORT': '70000',
        'MAIL_USE_SSL': 'perhaps',
        'MAIL_USERNAME': 'admin@example.com',
        'MAIL_PASSWORD': '',
        'APPID': 'configured-alone',
        'BD_TRANSLATOR_KEY': '',
        'UPLOAD_FOLDER': 'instance/uploads',
    }, tmp_path)
    assert {'SECRET_KEY', 'MAIL_PORT', 'MAIL_USE_SSL', 'MAIL_PASSWORD',
            'BD_TRANSLATOR_KEY'} <= report.errors.keys()


def test_sanitize_url_removes_credentials_query_and_fragment():
    assert sanitize_url(
        'mysql+pymysql://user:password@db.example/flog?token=abc#frag'
    ) == 'mysql+pymysql://db.example/flog'


def test_sanitize_message_replaces_every_nonempty_sensitive_value():
    values = {'MAIL_PASSWORD': 'never-print-this', 'SECRET_KEY': 'also-secret'}
    safe = sanitize_message(
        'login never-print-this failed under also-secret', values)
    assert safe == 'login [REDACTED] failed under [REDACTED]'


def test_normalize_env_canonicalizes_boolean_without_mutating_input():
    original = {'MAIL_USE_SSL': 'YES'}
    assert normalize_env(original)['MAIL_USE_SSL'] == 'true'
    assert original == {'MAIL_USE_SSL': 'YES'}


def test_find_active_overrides_returns_names_without_values():
    assert find_active_overrides(
        {'REDIS_URL': 'redis://file/0', 'SECRET_KEY': 'file-secret'},
        {'REDIS_URL': 'redis://process/0', 'SECRET_KEY': 'file-secret'},
    ) == frozenset({'REDIS_URL'})
```

- [ ] **Step 6: Run the new tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_config.py`

Expected: failures show the validation/report/sanitization interfaces are missing.

- [ ] **Step 7: Implement validation, sanitization, and configured path**

Use `urllib.parse.urlsplit`, `email_validator.validate_email(address, check_deliverability=False)`, and `pathlib.Path`. Accept the installed SQLAlchemy URL schemes `sqlite` and `mysql+pymysql`, Redis schemes `redis`/`rediss`/`unix`, and Elasticsearch schemes `http`/`https`. `normalize_env()` copies the mapping and canonicalizes accepted `MAIL_USE_SSL` spellings to `true` or `false` through a small `normalize_boolean()` helper; it never opens a socket. `find_active_overrides()` compares allowlisted file and process values but returns only key names, never values.

Add this configuration default:

```python
class Config:
    ENV_FILE_PATH = str(basedir / '.env')
```

Build user-facing validation messages from field labels and fixed prose, never by interpolating submitted values.

- [ ] **Step 8: Run validation tests and the existing config tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_config.py tests/test_test_database_isolation.py`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add app/env_config.py config.py tests/test_env_config.py
git commit -m "feat: validate managed environment settings"
```

---

### Task 2: Line-Preserving Environment Document And Atomic Save

**Files:**
- Create: `app/env_file.py`
- Create: `tests/test_env_file.py`

**Interfaces:**
- Consumes: `MANAGED_KEYS` from `app.env_config`.
- Produces: `EnvDocument(path: Path, text: str, values: dict[str, str], fingerprint: str)`.
- Produces: `EnvDocument.load(path: Path) -> EnvDocument`.
- Produces: `EnvDocument.render(values: Mapping[str, str]) -> str`.
- Produces: `EnvDocument.save(values: Mapping[str, str], expected_fingerprint: str) -> EnvDocument`.
- Produces: `EnvFileError`, `DuplicateEnvKeyError`, and `StaleEnvFileError`, all with fixed safe messages.

- [ ] **Step 1: Write failing load and preservation tests**

Use only `tmp_path`; include comments, `export KEY=...`, quoted values, blank lines, and an unmanaged variable:

```python
def test_load_parses_managed_values_without_exposing_unmanaged_values(tmp_path):
    path = tmp_path / '.env'
    path.write_text(
        '# heading\nSECRET_KEY="old value"\nUNMANAGED=leave-me\n\nMAIL_PORT=465\n',
        encoding='utf-8',
    )
    document = EnvDocument.load(path)
    assert document.values == {'SECRET_KEY': 'old value', 'MAIL_PORT': '465'}
    assert len(document.fingerprint) == 64


def test_render_replaces_managed_lines_and_preserves_other_text(tmp_path):
    path = tmp_path / '.env'
    original = '# heading\nSECRET_KEY=old\nUNMANAGED=leave-me\n\n'
    path.write_text(original, encoding='utf-8')
    rendered = EnvDocument.load(path).render({'SECRET_KEY': 'new value'})
    assert '# heading\n' in rendered
    assert 'UNMANAGED=leave-me\n\n' in rendered
    assert "SECRET_KEY='new value'\n" in rendered


def test_render_removes_explicitly_cleared_managed_assignment(tmp_path):
    path = tmp_path / '.env'
    path.write_text(
        '# mail\nMAIL_PASSWORD=old\nUNMANAGED=keep\n', encoding='utf-8')
    rendered = EnvDocument.load(path).render({'MAIL_PASSWORD': ''})
    assert 'MAIL_PASSWORD=' not in rendered
    assert rendered == '# mail\nUNMANAGED=keep\n'
```

- [ ] **Step 2: Run and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_file.py -k 'load or render'`

Expected: collection fails because `app.env_file` does not exist.

- [ ] **Step 3: Implement loading, duplicate detection, and rendering**

Use `dotenv.parser.parse_stream(stream)` so each parsed binding retains its original source string. Hash the exact UTF-8 bytes with SHA-256. A missing file loads as an empty document with the SHA-256 fingerprint of empty bytes. Raise `DuplicateEnvKeyError` if any managed key occurs more than once.

Render by replacing the original source string only for changed managed bindings, using `dotenv.set_key`-compatible single-quote escaping. Remove a managed assignment when its candidate value is empty. Append newly configured nonempty managed keys in `ENV_FIELDS` order. Preserve every comment, blank line, malformed unmanaged line, and unknown assignment exactly.

- [ ] **Step 4: Run parsing tests and verify GREEN**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_file.py -k 'load or render or duplicate'`

Expected: all selected tests pass.

- [ ] **Step 5: Write failing concurrency and atomicity tests**

Inject the replacement function so failure can be proven without changing the original file:

```python
def test_save_rejects_stale_fingerprint(tmp_path):
    path = tmp_path / '.env'
    path.write_text('MAIL_PORT=465\n', encoding='utf-8')
    document = EnvDocument.load(path)
    path.write_text('MAIL_PORT=587\n', encoding='utf-8')
    with pytest.raises(StaleEnvFileError):
        document.save({'MAIL_PORT': '2525'}, document.fingerprint)
    assert path.read_text(encoding='utf-8') == 'MAIL_PORT=587\n'


def test_failed_atomic_replace_leaves_original_file(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('MAIL_PORT=465\n', encoding='utf-8')
    document = EnvDocument.load(path)

    def fail_replace(source, destination):
        raise OSError('simulated replacement failure')

    monkeypatch.setattr('app.env_file.os.replace', fail_replace)
    with pytest.raises(EnvFileError):
        document.save({'MAIL_PORT': '587'}, document.fingerprint)
    assert path.read_text(encoding='utf-8') == 'MAIL_PORT=465\n'
    assert list(tmp_path.glob('.env.*.tmp')) == []
```

Also test owner-only mode `0o600` for a new file, retention of an existing restrictive mode, `flush`/`fsync` before replace, and reparsing the final file after save.

- [ ] **Step 6: Run the save tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_file.py`

Expected: failures identify the missing `save` behavior.

- [ ] **Step 7: Implement safe atomic saving**

Re-read and compare fingerprints immediately before writing. Create the temp file with `tempfile.mkstemp(prefix=f'{path.name}.', suffix='.tmp', dir=path.parent)`, apply mode `0o600` for a new destination or the existing destination's permission bits, write UTF-8 with `newline=''`, flush, `os.fsync`, and call `os.replace`. Clean up the exact temporary path in `finally`. After replacement, load again and compare managed values; raise a safe `EnvFileError` if verification fails.

- [ ] **Step 8: Run all environment-document tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_file.py`

Expected: all tests pass and no temporary file remains.

- [ ] **Step 9: Commit Task 2**

```bash
git add app/env_file.py tests/test_env_file.py
git commit -m "feat: persist environment file atomically"
```

---

### Task 3: Isolated External Connectivity Checks

**Files:**
- Create: `app/env_checks.py`
- Create: `tests/test_env_checks.py`

**Interfaces:**
- Consumes: `validate_env()` and `sanitize_message()` from `app.env_config`.
- Produces: `CheckResult(service: str, status: Literal['success', 'failed', 'not_configured'], message: str, elapsed_ms: int)`.
- Produces: `check_database(values, timeout=3.0) -> CheckResult`.
- Produces: `check_redis(values, timeout=3.0) -> CheckResult`.
- Produces: `check_smtp(values, timeout=5.0) -> CheckResult`.
- Produces: `check_uploads(values, project_root: Path) -> CheckResult`.
- Produces: `check_baidu_translation(values, timeout=5.0) -> CheckResult`.
- Produces: `check_microsoft_translation(values, timeout=5.0) -> CheckResult`.
- Produces: `check_elasticsearch(values, timeout=3.0) -> CheckResult`.
- Produces: `run_checks(values, project_root: Path, services: Collection[str] | None = None) -> dict[str, CheckResult]`.

- [ ] **Step 1: Write failing result, not-configured, and database tests**

Monkeypatch factories at their import location and assert real interactions and cleanup rather than only call counts:

```python
def test_database_check_executes_select_one_and_disposes_engine(monkeypatch):
    engine = FakeEngine(result=1)
    monkeypatch.setattr('app.env_checks.sa.create_engine', lambda *a, **k: engine)
    result = check_database({'DATABASE_URL': 'sqlite://'}, timeout=0.1)
    assert result.status == 'success'
    assert engine.executed_sql == ['SELECT 1']
    assert engine.disposed is True


def test_missing_elasticsearch_is_not_configured():
    result = check_elasticsearch({'ELASTICSEARCH_URL': ''}, timeout=0.1)
    assert result.status == 'not_configured'
```

- [ ] **Step 2: Run the first checker tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_checks.py -k 'database or missing'`

Expected: collection fails because `app.env_checks` does not exist.

- [ ] **Step 3: Implement the common result wrapper and database checker**

Use `time.monotonic_ns()` for elapsed time. Create a temporary engine with `pool_pre_ping=True`, `connect_args` appropriate to the parsed backend, execute `sa.text('SELECT 1')`, and dispose it in `finally`. Convert known timeout/authentication/connection failures into fixed Chinese messages; pass every final message through `sanitize_message`.

- [ ] **Step 4: Run the selected checker tests and verify GREEN**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_checks.py -k 'database or missing'`

Expected: all selected tests pass.

- [ ] **Step 5: Add failing tests for Redis, SMTP, uploads, and HTTP APIs**

Cover these observable behaviors:

```python
def test_redis_check_pings_and_closes_pool(monkeypatch):
    client = FakeRedis(ping_result=True)
    monkeypatch.setattr(
        'app.env_checks.Redis.from_url', lambda *a, **k: client)
    result = check_redis({'REDIS_URL': 'redis://cache.example/0'}, timeout=0.1)
    assert result.status == 'success'
    assert client.ping_called
    assert client.connection_pool.disconnected


def test_smtp_check_authenticates_without_sending(monkeypatch):
    smtp = FakeSMTP()
    monkeypatch.setattr('app.env_checks.smtplib.SMTP_SSL', lambda *a, **k: smtp)
    result = check_smtp({
        'MAIL_SERVER': 'smtp.example', 'MAIL_PORT': '465',
        'MAIL_USE_SSL': 'true', 'MAIL_USERNAME': 'admin@example.com',
        'MAIL_PASSWORD': 'secret',
    }, timeout=0.1)
    assert result.status == 'success'
    assert smtp.logged_in_as == 'admin@example.com'
    assert smtp.send_calls == []
    assert smtp.quit_called


def test_batch_checks_continue_after_one_failure(monkeypatch, tmp_path):
    monkeypatch.setitem(CHECKERS, 'database', lambda *a, **k: failed('database'))
    monkeypatch.setitem(CHECKERS, 'uploads', lambda *a, **k: succeeded('uploads'))
    results = run_checks({}, tmp_path, services={'database', 'uploads'})
    assert results['database'].status == 'failed'
    assert results['uploads'].status == 'success'
```

For uploads, verify a temporary probe is removed. For Baidu, assert the HTTPS request uses the fixed text `health check`, calculated signature, and no credential in the result. For Microsoft, assert headers carry the subscription key and the response is parsed. For Elasticsearch, assert query strings and credentials do not appear in errors. Include timeout and malformed JSON cases.

- [ ] **Step 6: Run all checker tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_checks.py`

Expected: failures correspond to the not-yet-implemented service checkers.

- [ ] **Step 7: Implement remaining checkers and batch isolation**

Use these side-effect boundaries:

- Redis: `Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)` then `ping()` and `connection_pool.disconnect()` in `finally`.
- SMTP: `SMTP_SSL` when true, otherwise `SMTP`, `ehlo()`, optional `starttls()` only when advertised, `login()` only when both credentials exist, and `quit()`/`close()` in `finally`; never call `sendmail`.
- Uploads: resolve relative paths against the project root, create a `NamedTemporaryFile` only inside an existing directory, or inspect the nearest existing parent when the directory is absent.
- Baidu: HTTPS GET to `/api/trans/vip/translate` with fixed text, random salt, and MD5 signature; accept only a response containing `trans_result`.
- Microsoft: HTTPS POST to the Translator v3 endpoint with fixed text and `Ocp-Apim-Subscription-Key`; accept only the documented translation array shape.
- Elasticsearch: `requests.get(url, timeout=timeout)` against a sanitized base URL and accept a successful JSON response.

Store callables in a `CHECKERS` dictionary. `run_checks` catches failures per service so one failure cannot abort the batch.

- [ ] **Step 8: Run checker and sanitizer tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_env_checks.py tests/test_env_config.py`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 3**

```bash
git add app/env_checks.py tests/test_env_checks.py
git commit -m "feat: check environment service connectivity"
```

---

### Task 4: Administrator Form And Controller

**Files:**
- Create: `app/admin/env_settings.py`
- Create: `tests/test_admin_env_settings.py`
- Modify: `app/admin/forms.py:1-141`
- Modify: `app/admin/__init__.py:6`
- Modify: `tests/conftest.py:16-24`
- Modify: `tests/test_admin_access.py:106-134`

**Interfaces:**
- Consumes: `EnvDocument`, `merge_draft`, `validate_env`, `run_checks`, and `Config.ENV_FILE_PATH`.
- Produces: `EnvironmentSettingsForm` with one explicit field per managed key, five explicit clear checkboxes, and hidden `fingerprint`.
- Produces: `GET|POST /admin/settings/environment`, endpoint `admin.environment_settings`.
- Produces: POST actions `validate`, `check:database`, `check:redis`, `check:smtp`, `check:uploads`, `check:baidu_translation`, `check:microsoft_translation`, `check:elasticsearch`, `check:all`, and `save`.

- [ ] **Step 1: Write failing access and secret-rendering tests**

In the fixture, set `ENV_FILE_PATH` to `tmp_path / '.env'` before each request and write only test secrets:

```python
@pytest.fixture
def env_path(application, tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text(
        'SECRET_KEY=test-file-secret-that-is-long-enough\n'
        'DATABASE_URL=sqlite://\n'
        'MAIL_PORT=465\n'
        'MAIL_USE_SSL=true\n'
        f'UPLOAD_FOLDER={tmp_path / "uploads"}\n',
        encoding='utf-8',
    )
    monkeypatch.setitem(application.config, 'ENV_FILE_PATH', str(path))
    return path


def valid_form_data(env_path, action):
    return {
        'fingerprint': EnvDocument.load(env_path).fingerprint,
        'action': action,
        'MAIL_PORT': '465',
        'MAIL_USE_SSL': 'true',
        'UPLOAD_FOLDER': str(env_path.parent / 'uploads'),
    }


def test_only_administrator_can_open_environment_settings(
        client, users, env_path):
    assert client.get('/admin/settings/environment').status_code == 302
    login(client, 'author')
    assert client.get('/admin/settings/environment').status_code == 403
    client.post('/logout')
    login(client, 'admin')
    assert client.get('/admin/settings/environment').status_code == 200


def test_environment_page_never_renders_sensitive_values(
        client, application, users, env_path):
    env_path.write_text(
        'SECRET_KEY=super-secret-value\n'
        'DATABASE_URL=mysql+pymysql://user:password@db/flog\n'
        'MAIL_PASSWORD=mail-secret\n'
        'MAIL_PORT=465\nMAIL_USE_SSL=true\n', encoding='utf-8')
    login(client, 'admin')
    html = client.get('/admin/settings/environment').get_data(as_text=True)
    for secret in ('super-secret-value', 'password@db', 'mail-secret'):
        assert secret not in html
    assert '已配置' in html
```

- [ ] **Step 2: Run and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py -k 'open or never_renders'`

Expected: administrator request returns 404 because the route is missing.

- [ ] **Step 3: Add the explicit Flask-WTF form and read-only GET controller**

Use `PasswordField(render_kw={'autocomplete': 'new-password'})` for sensitive values so submitted values are not redisplayed. Use `StringField` for other text values, a `SelectField` with fixed `true`/`false` choices for `MAIL_USE_SSL`, `BooleanField` for each `clear_<lowercase_key>`, `HiddenField('fingerprint')`, and `SubmitField` only if it maps to a single fixed action. Validate maximum lengths at the WTForms boundary before domain validation.

Register `env_settings` in `app/admin/__init__.py`. Define the
`environment_settings()` view at `/settings/environment` for `GET` and `POST`,
with `@login_required` followed by `@admin_required`, matching existing admin
modules. Its first operation resolves
`Path(current_app.config['ENV_FILE_PATH'])`; it never accepts a path from the
request.

On GET, load the configured path, put only non-sensitive values and the fingerprint into the form, and pass `configured_sensitive_keys` plus `find_active_overrides(document.values, os.environ)` separately to the template. Never use the repository path directly.

- [ ] **Step 4: Run access and non-disclosure tests and verify GREEN**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py -k 'open or never_renders'`

Expected: all selected tests pass.

- [ ] **Step 5: Write failing POST behavior tests**

Add one focused test per behavior:

- `validate` returns field errors and leaves file bytes unchanged.
- `check:redis` receives a draft Redis URL but leaves file bytes unchanged.
- blank secret input retains the stored value during a non-secret update.
- checked `clear_mail_password` removes only `MAIL_PASSWORD`.
- submitted `EVIL` cannot create or alter an unmanaged assignment.
- stale fingerprint returns 409 and preserves the externally changed bytes.
- valid save redirects, preserves comments/unmanaged lines, and flashes the restart requirement.
- unreadable/duplicate-key documents return safe messages.
- audit logs include the administrator and changed key names but no old or new values.
- connectivity audit logs include service/status/duration but no URL or credential.
- `os.environ`, `application.config`, `application.extensions`, and the active database and Redis objects remain unchanged after validate, check, and save actions.

Use a capture fake for connectivity rather than contacting a service:

```python
def test_connection_check_uses_draft_without_saving(
        client, application, users, env_path, monkeypatch):
    seen = {}
    original = env_path.read_bytes()

    def fake_checks(values, project_root, services=None):
        seen.update(values)
        return {'redis': CheckResult('redis', 'success', '连接成功。', 1)}

    monkeypatch.setattr('app.admin.env_settings.run_checks', fake_checks)
    login(client, 'admin')
    fingerprint = EnvDocument.load(env_path).fingerprint
    response = client.post('/admin/settings/environment', data={
        'fingerprint': fingerprint,
        'action': 'check:redis',
        'REDIS_URL': 'redis://draft.example/0',
    })
    assert response.status_code == 200
    assert seen['REDIS_URL'] == 'redis://draft.example/0'
    assert env_path.read_bytes() == original
```

- [ ] **Step 6: Run POST tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py`

Expected: failures correspond to missing action routing, merging, saving, and logging.

- [ ] **Step 7: Implement action orchestration and safe audit logging**

Define fixed action-to-service mappings; reject unknown action values with 400. Always load the server-side document, construct submitted values from explicit form attributes, construct `clear_keys` from the five fixed checkboxes, then call `normalize_env(merge_draft(document.values, submitted, clear_keys))`.

For `validate`, return the local report only. For checks, refuse only the requested services whose prerequisite fields have validation errors and run the others; log only each fixed service name, status, duration, and administrator ID. For `save`, require a valid WTForms submission, valid local report, and matching fingerprint; on success log `environment settings changed keys=%s admin_id=%s`, redirect, and flash `环境配置已保存；请重启应用以使新配置生效。`

Before rendering any POST response, clear every password field's `.data`. Use 409 for stale saves, 400 for invalid action values, and 200 for ordinary validation or connectivity failures.

- [ ] **Step 8: Extend existing access and CSRF matrices**

Add `/admin/settings/environment` to all three GET matrices in `tests/test_admin_access.py`. Add a POST assertion with `WTF_CSRF_ENABLED=True` to prove `/admin/settings/environment` rejects a missing token with 400. Ensure the application fixture's `ENV_FILE_PATH` points to a temporary file for every test, even tests that do not visit the new route.

- [ ] **Step 9: Run admin request and security tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py tests/test_admin_access.py tests/test_security.py`

Expected: all tests pass.

- [ ] **Step 10: Commit Task 4**

```bash
git add app/admin/env_settings.py app/admin/forms.py app/admin/__init__.py tests/conftest.py tests/test_admin_env_settings.py tests/test_admin_access.py
git commit -m "feat: add admin environment settings controller"
```

---

### Task 5: Environment Settings Page And Responsive Presentation

**Files:**
- Create: `app/templates/admin/settings/environment.html`
- Modify: `app/templates/admin/base.html:19-22`
- Modify: `app/static/style.css:2483-2585`
- Modify: `tests/test_admin_env_settings.py`

**Interfaces:**
- Consumes template context: `form`, `fields_by_group`, `configured_sensitive_keys`, `overridden_keys`, `validation_report`, `check_results`, and `document_error`.
- Produces accessible field groups, local statuses, fixed action buttons, connectivity result cards, and restart guidance.

- [ ] **Step 1: Write failing template structure tests**

Assert semantic and security-critical output, not snapshots:

```python
def test_environment_page_renders_groups_actions_and_navigation(
        client, users, env_path):
    login(client, 'admin')
    html = client.get('/admin/settings/environment').get_data(as_text=True)
    assert '环境配置' in html
    assert '数据库' in html
    assert 'Redis 与后台任务' in html
    assert 'name="action" value="validate"' in html
    assert 'name="action" value="check:all"' in html
    assert 'name="action" value="save"' in html
    assert '修改后需要重启应用' in html
    assert 'autocomplete="new-password"' in html
    assert '当前进程值不同' in html


def test_environment_result_uses_text_not_secret_bearing_exception(
        client, users, env_path, monkeypatch):
    monkeypatch.setattr(
        'app.admin.env_settings.run_checks',
        lambda *a, **k: {'database': CheckResult(
            'database', 'failed', '数据库连接失败。', 12)},
    )
    response = client.post(
        '/admin/settings/environment',
        data=valid_form_data(env_path, 'check:database'),
    )
    html = response.get_data(as_text=True)
    assert '数据库连接失败。' in html
    assert '12 ms' in html
```

- [ ] **Step 2: Run template tests and verify RED**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py -k 'renders_groups or result_uses'`

Expected: template-not-found or missing-markup failures.

- [ ] **Step 3: Build the server-rendered page and navigation link**

Extend `admin/base.html` with:

```jinja2
<a class="admin-nav__link" href="{{ url_for('admin.environment_settings') }}">环境配置</a>
```

In the page template, render fields from server-owned metadata, but access only form fields already defined by the fixed form class. For sensitive fields render `已配置`/`未配置`, the password input, and its explicit clear checkbox. Do not use submitted values in help text or HTML attributes. Use one form and buttons such as:

```jinja2
<button class="button" type="submit" name="action" value="validate">检查配置</button>
<button class="button" type="submit" name="action" value="check:all">一键检测全部</button>
<button class="button button--cta" type="submit" name="action" value="save">保存配置</button>
```

Disable mutation/check buttons when `document_error` makes the page read-only. Render result status using both text and a class; do not communicate success/failure by color alone.

- [ ] **Step 4: Add scoped responsive styles**

Add `.env-settings`, `.env-settings__group`, `.env-field-grid`, `.env-status`, `.env-check-results`, and `.env-check-result--{success,failed,not-configured}`. Use existing color variables, borders, radii, and button styles. At `max-width: 768px`, collapse field and result grids to one column and keep every action at least 44px high.

- [ ] **Step 5: Run page and broader UI tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_admin_env_settings.py tests/test_ui_pages.py tests/test_admin_access.py`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add app/templates/admin/settings/environment.html app/templates/admin/base.html app/static/style.css tests/test_admin_env_settings.py
git commit -m "feat: add environment settings admin page"
```

---

### Task 6: Documentation, Regression Audit, And Full Verification

**Files:**
- Modify: `README.md:77-115`

**Interfaces:**
- Consumes all prior task interfaces.
- Produces deployer documentation and final verification evidence.

- [ ] **Step 1: Update operational documentation**

Add an `环境配置管理` subsection explaining:

- administrators use `/admin/settings/environment`;
- sensitive values are never displayed and blank secret fields retain their values;
- connection checks do not send email or mutate service data;
- saving writes `.env` but requires an application restart;
- container/orchestrator environment variables can override `.env` and cannot be changed by this page;
- the web process requires permission to write `.env` if editing is desired.

- [ ] **Step 2: Run a secret-disclosure regression search**

Run:

```bash
rg -n "super-secret-value|mail-secret|never-print-this|password@db" app README.md
```

Expected: no matches. These literal test secrets may exist only under `tests/`.

- [ ] **Step 3: Run focused feature tests**

Run:

```bash
DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q \
  tests/test_env_config.py \
  tests/test_env_file.py \
  tests/test_env_checks.py \
  tests/test_admin_env_settings.py
```

Expected: all focused tests pass with zero warnings caused by the new feature.

- [ ] **Step 4: Run the complete Python suite**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`

Expected: all Python tests pass.

- [ ] **Step 5: Run the complete JavaScript suite**

Run: `node --test tests/*.test.js`

Expected: all JavaScript tests pass.

- [ ] **Step 6: Check formatting and review the final diff**

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.

Run: `git status --short && git diff --stat && git diff -- app/env_config.py app/env_file.py app/env_checks.py app/admin/env_settings.py app/admin/forms.py app/templates/admin/settings/environment.html app/templates/admin/base.html app/static/style.css config.py README.md`

Confirm line by line that every design requirement is represented, no real `.env` value appears, and no unrelated file changed.

- [ ] **Step 7: Commit Task 6**

```bash
git add README.md
git commit -m "docs: explain admin environment management"
```

- [ ] **Step 8: Record final evidence**

Capture the exact passing counts from Python and JavaScript test output, the final commit list from `git log --oneline`, and any service checks that remain intentionally mocked in automated tests. Do not claim completion unless all fresh verification commands above exit successfully.
