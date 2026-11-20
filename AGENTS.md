# AGENTS.md

Flog is a personal blog and small CMS: Python 3.14, Flask 3, SQLAlchemy 2, Jinja2, vanilla JS and CSS (no frontend build step). Public site and `/admin` live in one app. `README.md` covers features, setup, environment variables and deployment; this file locks the engineering constraints and verification commands for coding agents.

## Automated checks

Use the project virtualenv (`.venv/bin/python`, Python 3.14). `./scripts/bootstrap.sh --no-run` sets it up via `uv` (`requirements.in` -> `requirements.txt`, `requirements-dev.txt`).

```bash
make lint                                          # Ruff lint + node --check on app/static/*.js
make typecheck                                     # mypy (check_untyped_defs = true)
make test-js                                       # Node.js VM tests (tests/*.test.js)
make check                                         # Fast gate: lint + typecheck + test-js
.venv/bin/python -m pytest tests -q -k <keyword>   # Targeted Python tests during iteration
make test-browser                                  # Playwright real Chromium E2E tests
make test                                          # JS + full non-browser Python suite (~1180 tests)
make verify                                        # Full pre-merge gate: lint + typecheck + test + browser
flask db upgrade                                   # Apply Alembic migrations
flask translate compile                            # Rebuild messages.mo after editing messages.po
```

## Architecture & entrypoints

- `app/__init__.py` initializes global `app`, `db`, `login`, `mail`, `babel`, `csrf`, context processors, and registers modules via import side effects at the bottom of the file. Any new route module, `after_request` hook, or CLI command must be imported there.
- `app/routes.py` holds public routes (plus legacy admin redirect adapters pinned by `tests/test_legacy_admin_routes.py`); `app/podcast_routes.py` holds public podcast routes; `app/admin/` is the `/admin` blueprint (one module per area).
- Business logic lives in plain modules, not views: `content.py` + `markdown_extras.py`, `security.py`, `seo.py`, `post_drafts.py`, `comments.py`, `comment_markdown.py`, `comment_mail.py`, `images.py`, `live_photos.py`, `pages.py`, `search.py`, `search_index.py`, `likes.py`, `post_views.py`, `podcast.py`, `authorization.py`, `throttle.py`, `site_text.py`.
- Templates: `app/templates/base.html` (public shell), `admin/base.html` (admin shell), `email/base.html` (mail shell). Static files: `app/static/`; `static/vendor/` (Bootstrap, Vditor, KaTeX, Mermaid, PhotoSwipe) and `static/fonts/` are generated/pinned and must not be hand-edited.

## Invariants & security boundaries

Many of these are enforced by `tests/test_engineering_invariants.py`, `tests/test_seo_and_core_regression.py`, and `tests/test_public_repo_hygiene.py`:

- **HTML/XSS boundary**: Never use Jinja `|safe` in templates. `Markup(...)` is restricted to `app/security.py`, `app/content.py`, `app/comment_markdown.py`, and `app/search.py`. All user HTML/Markdown must pass through those sanitizers.
- **No template data access**: Templates must never execute ORM queries (`db.session`, `sa.select`, `.query`).
- **Redirects & auth**: Roles are only `user` and `admin` (`User.is_admin`, `admin_required`). Validate all local redirects with `app.security.is_local_path`.
- **SEO & syndication single source of truth**: `app/seo.py` owns `public_base_url()`, `public_url()`, canonical URLs, Open Graph type, and `noindex, nofollow` directives (shared across `base.html`, `errors.py`, `/feed.xml`, `/sitemap.xml`, `/robots.txt`). Drafts and unpublished pages must never appear in public routes, feeds, search, or sitemap.
- **Database portability**: SQLite locally (with optional FTS5 trigram index in `search_index.py`), MySQL/MariaDB in production. Always keep `LIKE` matching in search. Store UTC datetimes, display in `DISPLAY_TIMEZONE`. Every schema change requires a reviewed Alembic migration.
- **Configuration**: Environment variables / `.env` via `config.py` only (no admin env UI). New settings must be added to `config.py`, `.env.example`, and `README.md`.
- **Localization**: Chinese-only UI. English message IDs in code/templates, Chinese translations in `app/translations/zh/LC_MESSAGES/messages.po`; commit both `.po` and compiled `.mo`.
- **Static caching & fonts**: Always link static assets via `url_for('static', ...)` so `static_cache.py` fingerprints site CSS/JS. Regenerate fonts via `scripts/generate_article_fonts.py` (needs network).
- **Repo hygiene**: Never commit secrets, personal analytics IDs, server addresses, or local machine home/temp directory paths (checked by `tests/test_public_repo_hygiene.py`).

## Code style & minimal comments

- Keep the architecture simple: prefer native Flask/Jinja2/SQLAlchemy and plain functions over extra abstraction layers (`Service`/`Manager`/`Repository`/`Factory` wrappers).
- Write self-documenting code (explicit names, clear inputs/outputs, Python type annotations where helpful).
- **Minimal Comments**: Do not write comments that narrate obvious code. Keep or add comments only for security constraints, non-obvious design invariants, external protocol/library quirks, compatibility workarounds, or deliberate performance tradeoffs.

## Agent workflow & feedback loop

1. Understand the request -> locate entrypoints and invariants -> identify affected tests.
2. Implement the minimal necessary change without speculative refactoring.
3. Run `make check` and targeted pytest tests (`-k <keyword>`).
4. Run `make test-browser` whenever templates, CSS, JS, search, or article interactions change.
5. Before finishing or merging, ensure all affected suites (and `make verify` for cross-cutting changes) pass with real command output.
6. **When a failure or bug repeats**: diagnose the root cause first, fix the underlying code/boundary, and add a permanent automated test or static check—never paper over it with prompt notes alone, never weaken or delete failing tests, and never globally disable lint or type checks.

## Forbidden actions

- Do not introduce frontend build systems/frameworks (React/Vue/Vite) or unnecessary architectural layers.
- Do not hand-edit `app/static/vendor/` or `app/static/fonts/article-fonts.css`.
- Do not commit `.env`, `instance/`, `logs/`, databases, or uploads, and never run destructive commands against `instance/`.
- Do not claim tests pass without actually running them.
- Do not modify production servers by hand or deploy without explicit user authorization.

## Git & deployment

- Commit messages use conventional prefixes (`feat(scope):`, `fix:`, `perf:`, `refactor:`, `test:`, `docs:`).
- `origin` is the public GitHub repository (`Flog`); production tracks `origin/main`. Push explicitly to `origin`.
- Deploy only when explicitly requested and only after `git push origin main`: run `./scripts/deploy.sh --dry-run`, then `./scripts/deploy.sh` (server config comes from `~/.config/flog/deploy.env`).
