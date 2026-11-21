# AGENTS.md

Flog is a personal blog with a small CMS. The public site puts content and typography first, with a quiet editorial layout that leaves room for reading. Prefer familiar patterns, disclose secondary controls as needed, and keep essential actions easy to find. Avoid the look of a SaaS dashboard, marketing site, component demo, or generic generated template. Keep work within the requested feature. Site-wide redesigns, feature tours, extra settings or animation, unrelated refactors, and article rewrites need their own request.

## Interface copy comes last

**Do not narrate the interface.** Content is the interface, and every UI element must earn its place. Show the content under its functional label. Use `归档` with years, months, and posts, `搜索文章` with the input and results, and `目录` with section links.

- Skip explanatory heading subtitles, list intros, long search instructions, tutorials for familiar controls, and copy that repeats development requirements. Omit filler welcome or marketing copy, intro cards, hint banners, and decorative icons or paragraphs attached to each module. Keep the home page focused on the blog unless a landing page is requested.
- Before adding copy, check whether removing it would impair understanding or operation, whether it conveys information unavailable elsewhere, and whether it helps the reader act or read. Omit copy that merely describes an obvious element.
- Preserve author-written introductions and articles. Keep editorial copy with clear content value, necessary empty states and recovery guidance, explanations of complex settings and their consequences, and necessary privacy, security, accessibility, or data-processing notices.

## Reading and UI conventions

- Start with the current templates and `app/static/style.css`. Reuse shared navigation, buttons, search, tags, pagination patterns, and CSS variables. Keep new patterns compatible with existing color, type, radius, shadow, and motion choices. Scope CSS to the affected component. Avoid arbitrary pixel fixes, `!important`, and global overrides for local problems.
- Preserve the article's body type, size, line height, letter and paragraph spacing, `--reading-width`, heading hierarchy, and link affordances. Check blockquotes, lists, tables, inline code, code blocks, images, and captions. Keep sidebars and navigation secondary. Avoid ornate headings, prominent shadows or gradients, tighter spacing for density, and large heroes without a clear request. Keep the article layout simple as features are added.
- Prefer semantic HTML and CSS, with small, page-scoped JavaScript where needed. Avoid large dependencies for basic interactions and unnecessary third-party resources. Keep scrolling smooth, respect `prefers-reduced-motion`, and reserve space for media to avoid layout shift. Preserve useful features and accessibility when optimizing.
- Use current templates and CSS as the reference for implementation. For design context, see the [public editorial redesign](docs/superpowers/specs/2026-08-20-apple-editorial-redesign-design.md), [public page consistency](docs/superpowers/specs/2026-11-05-public-pages-consistency-design.md), and [admin editorial UI](docs/superpowers/specs/2026-11-05-admin-editorial-ui-design.md).

Apply these constraints to reading and discovery features within the requested scope.

- **TOC.** Show concise heading links with accurate active-section highlighting. Keep it usable on mobile and clear of the article. Preserve normal scrolling and anchor navigation.
- **Reading progress.** Keep it unobtrusive and clear of content and controls. Skip explanatory cards and distracting motion.
- **Search.** Keep the entry easy to find. Lead with titles, matches, and context. Use concise empty states and omit promotional recommendations.
- **Code blocks.** Preserve readable formatting and horizontal scrolling for long lines. Keep copy controls unobtrusive and syntax highlighting legible and lightweight.
- **Images and lightbox.** Keep useful proportions, alt text, and captions. Avoid destructive cropping and elaborate animation. Ensure the close control is obvious and the lightbox works by keyboard and on mobile.

## Architecture and code style

Flog uses Python 3.14, Flask 3, SQLAlchemy 2, Jinja2, and vanilla JavaScript and CSS. The public site and `/admin` share one app. See [README.md](README.md) for setup, configuration, and deployment.

- `app/__init__.py` initializes the app, extensions, and context processors. Register new route modules, `after_request` hooks, and CLI commands through its imports. Public routes live in `app/routes.py` and `app/podcast_routes.py`. Keep the legacy redirects covered by `tests/test_legacy_admin_routes.py`. The `/admin` blueprint lives in `app/admin/`.
- Keep views focused on HTTP handling and put business logic in existing plain modules such as `app/content.py`, `app/search.py`, and `app/images.py`. Prepare data before rendering and batch or eager-load where needed to avoid N+1 queries. Keep Jinja focused on presentation. Reuse existing helpers and keep shared styles in CSS and client behavior in the relevant `app/static/` scripts.
- In `app/templates/`, reuse `base.html`, `admin/base.html`, and `email/base.html` for their respective shells. Check `bootstrap_wtf.html` for form macros, `_theme_controls.html` for theme controls, and `post/_article.html` and `post/_post.html` for article and list markup before adding similar UI.
- Prefer clear names, inputs, outputs, and helpful type annotations. Avoid duplicated logic, thin wrappers, speculative abstractions, and defensive checks without a concrete failure mode. Keep the native stack without frontend frameworks or build systems. Add dependencies only when an existing approach cannot meet a demonstrated need.
- Comment on non-obvious algorithms, business decisions, security and compatibility constraints, migrations, or deliberate performance tradeoffs. Document public interfaces where useful. Omit line-by-line narration, decorative separators, vague TODOs, dead code, and agent process notes.

## Engineering invariants

Regression coverage lives in `tests/test_engineering_invariants.py`, `tests/test_seo_and_core_regression.py`, and `tests/test_public_repo_hygiene.py`.

- **HTML and data.** Never use Jinja `|safe` or execute ORM queries (`db.session`, `sa.select`, `.query`) in templates. Route user HTML and Markdown through the existing sanitizers. `Markup(...)` is restricted to `app/security.py`, `app/content.py`, `app/comment_markdown.py`, and `app/search.py`.
- **Redirects and roles.** Validate local redirects with `app.security.is_local_path`. Roles are limited to `user` and `admin`. Use `User.is_admin` and `admin_required` for authorization.
- **Public visibility and SEO.** `app/seo.py` owns `public_base_url()`, `public_url()`, canonical URLs, Open Graph type, and `noindex, nofollow` across HTML, errors, `/feed.xml`, `/sitemap.xml`, and `/robots.txt`. Keep drafts and unpublished pages out of public routes, feeds, search, and the sitemap.
- **Database.** Support local SQLite and production MySQL/MariaDB. Keep `LIKE` matching in search, including when the optional SQLite FTS5 trigram index is available. Store datetimes in UTC and display them in `DISPLAY_TIMEZONE`. Every schema change requires a reviewed Alembic migration.
- **Configuration and localization.** Read environment settings through `config.py` and document additions there, in `.env.example`, and in `README.md`. Keep environment configuration out of admin. The UI is Chinese-only. Use English message IDs in code and templates, update `app/translations/zh/LC_MESSAGES/messages.po`, and commit the compiled `.mo` with it.
- **Static assets.** Use `url_for('static', ...)` for static links so `static_cache.py` can fingerprint site CSS and JS. Do not hand-edit pinned or generated files in `app/static/vendor/` or `app/static/fonts/`. Regenerate article fonts with `scripts/generate_article_fonts.py` (requires network).
- **Repository hygiene.** Keep secrets, personal analytics IDs, server addresses, local home or temporary paths, `.env`, `instance/`, `logs/`, databases, and uploads out of commits. Never run destructive commands against `instance/`.

## Workflow and verification

1. Investigate the relevant entry points, templates, styles, existing implementations, and tests. Choose the smallest change that meets the request. For UI, check the proposed effect on reading, reuse, and visible copy before editing.
2. Implement within that scope. If a bug or failure repeats, diagnose and fix its root cause, then add a regression test or static check. Keep the failing checks effective and leave global lint and type checks enabled.
3. For code changes, run `make check` and targeted pytest. Run `make test-browser` when templates, CSS, JS, search, or article interactions change. Run the affected suites before delivery and `make verify` for cross-cutting changes. For docs, run `git diff --check` and the applicable checks in `tests/test_public_repo_hygiene.py`.
4. For UI changes, exercise affected pages and interactions at mobile and desktop widths in light and dark modes. Check long articles and titles, long links and code, wide tables, and large images for wrapping or overflow. Check keyboard navigation, visible focus, screen-reader names and states, text contrast, and browser console errors. Run visual regression against an existing baseline where available.
5. Inspect the final diff. For UI, confirm there is no filler copy or decoration, reading width and typography are intact, components match existing patterns, and mobile reading remains usable. Remove redundant comments and accidental edits. Report what changed, which checks actually ran and their results, and any known issues or unverified items.

Use the Python 3.14 project virtualenv. `./scripts/bootstrap.sh --no-run` installs dependencies, compiles translations, and applies local migrations. Runtime dependencies are declared in `requirements.in` and locked in `requirements.txt`. Development dependencies are in `requirements-dev.txt`.

```bash
make check                                          # Ruff, JS syntax, mypy, and Node.js tests
.venv/bin/python -m pytest tests -q -k 'keyword'     # Replace keyword with a relevant selector
make test-browser                                   # Playwright Chromium E2E
make test                                           # Node.js and non-browser Python tests
make verify                                         # Full gate including browser tests
.venv/bin/flask db upgrade                          # Apply Alembic migrations
.venv/bin/flask translate compile                   # Rebuild messages.mo
```

## Git and deployment

- Use conventional commit prefixes such as `feat(scope):`, `fix:`, `perf:`, `refactor:`, `test:`, and `docs:`. Push explicitly to `origin`, the public Flog repository. Production tracks `origin/main`.
- Never modify production servers by hand. Deploy only with explicit authorization and after `git push origin main`. Run `./scripts/deploy.sh --dry-run`, then `./scripts/deploy.sh`. Server configuration comes from `~/.config/flog/deploy.env`.
