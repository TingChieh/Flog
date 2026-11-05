# Admin Editorial UI And About Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restyle the admin to match the public editorial design and add an admin "关于" entry.

**Spec:** `docs/superpowers/specs/2026-11-05-admin-editorial-ui-design.md`. Baseline: 552 pytest, 41 node. Branch `feat/admin-editorial-ui`.

## Task 1: About entry

**Files:** `app/admin/pages.py`, `app/templates/admin/base.html`, `tests/test_admin_about.py`

- [ ] **Step 1:** Write `tests/test_admin_about.py` (use `users` fixture and `login`): admin GET `/admin/about` with a `Page(slug='about', kind='content')` redirects (302) to `/admin/pages/<id>/edit`; with no such page it redirects to `/admin/pages/new?title=关于&slug=about&show_in_nav=1` and creates no `Page`; with only a `PageRedirect` for `about` it redirects to that page's edit; member gets 403; anonymous redirects to login; `/admin/` HTML for an admin contains a link to `/admin/about` with text `关于`; `GET /admin/pages/new?title=关于&slug=about&show_in_nav=1` renders inputs with `value="关于"`, `value="about"` and the `show_in_nav` checkbox `checked`; a POST to `new_page` ignores the query parameters. Run; expect FAIL.
- [ ] **Step 2:** In `app/admin/pages.py` add:

```python
@bp.route('/about', methods=['GET'])
@login_required
@admin_required
def about():
    page = db.session.scalar(sa.select(Page).where(Page.slug == 'about'))
    if page is None:
        page = db.session.scalar(sa.select(Page).join(PageRedirect).where(
            PageRedirect.slug == 'about'))
    if page is not None:
        return redirect(url_for('admin.edit_page', page_id=page.id))
    return redirect(url_for('admin.new_page', title='关于', slug='about',
                            show_in_nav=1))
```
(import `PageRedirect` from `app.models`). In `new_page`, when `request.method == 'GET'` build `form = PageForm(data={...})` from `request.args` (`title`, `slug`, `show_in_nav` as `request.args.get('show_in_nav') == '1'`, `nav_order` default 0); keep `PageForm()` for POST.
- [ ] **Step 3:** In the `admin_navigation` macro of `admin/base.html` add `<a class="admin-nav__link" href="{{ url_for('admin.about') }}">关于</a>` after the 页面管理 link.
- [ ] **Step 4:** Run the new tests and the full suite; expect pass. Commit `feat(admin): dedicated About entry`.

## Task 2: Shell, top bar, sidebar

**Files:** `app/templates/admin/base.html`, `app/static/style.css`, `tests/test_admin_editorial_ui.py`

- [ ] **Step 1:** Write `tests/test_admin_editorial_ui.py`: admin page HTML has `<body class="public-site admin-site">`; the current nav link carries `aria-current="page"` (GET `/admin/pages` marks 页面管理, exactly one link); CSS contains the section marker `/* Admin: editorial shell` and rules `.admin-topbar`, `.admin-sidebar`, `.admin-nav__link` with the new values (`border-left: 2px solid transparent`, `background: transparent`, serif font stack). Run; expect FAIL.
- [ ] **Step 2:** `{% block body_class %}public-site admin-site{% endblock %}`. In the `admin_navigation` macro render each link with `{% if request.endpoint == 'admin.xxx' %} aria-current="page"{% endif %}` (for 概览 `admin.dashboard`, 我的文章 `admin.posts` — the duplicate 全部文章 link does not get it —, 新建文章 `admin.new_post`, 页面管理 `admin.pages` plus `admin.new_page`/`admin.edit_page`, 关于 `admin.about`, 分类 `admin.categories`, 评论 `admin.comments`, 用户与角色 `admin.users`, 网站设置 `admin.settings`, 环境配置 `admin.environment_settings`).
- [ ] **Step 3:** Append to the end of `style.css`, under `/* Admin: editorial shell, navigation and page header. */`:

```css
.admin-site .site-main { padding: 0 22px 56px; }
.admin-topbar { position: static; min-height: 70px; background: transparent; border: 0; backdrop-filter: none; }
.admin-topbar__inner { width: 100%; min-height: 70px; padding: 12px 22px; }
.admin-topbar__brand { font-family: 'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif; font-size: 22px; font-weight: 600; letter-spacing: 0; }
.admin-topbar__actions a { color: var(--text-secondary); text-decoration: none; }
.admin-topbar__actions a:hover, .admin-topbar__actions a:focus { color: var(--text-primary); text-decoration: underline; }
.admin-workspace { grid-template-columns: 200px minmax(0, 1fr); gap: 48px; min-height: 0; border: 0; }
.admin-sidebar { padding: 0; background: transparent; border: 0; }
.admin-nav__group { margin: 0 0 8px; color: var(--text-secondary); font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
.admin-nav__group--spaced { margin-top: 28px; }
.admin-nav__link { min-height: 34px; padding: 4px 0 4px 12px; color: var(--text-secondary); background: transparent; border-left: 2px solid transparent; border-radius: 0; font-family: 'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif; font-size: 15px; }
.admin-nav__link:hover, .admin-nav__link:focus { color: var(--text-primary); background: transparent; }
.admin-nav__link[aria-current="page"] { color: var(--text-primary); border-left-color: var(--text-primary); }
.admin-workspace__content { padding: 0; }
.admin-workspace__header { margin-bottom: 40px; padding-bottom: 0; border: 0; }
.admin-workspace__eyebrow { margin: 0 0 10px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
.admin-workspace__header h1 { font-family: var(--system-font); font-size: 36px; font-weight: 700; letter-spacing: -.04em; }
```
Check the mobile drawer rules (search `admin-drawer` in the `max-width: 768px` block) and adapt colours/borders so the drawer still reads correctly with the new tokens (no hard-coded greys).
- [ ] **Step 4:** Run tests; look at `/admin/` at 1440 and 390 (drawer open) with playwright; fix defects. Commit `feat(admin): editorial shell, top bar and sidebar`.

## Task 3: Buttons, lists, filters, dashboard, settings

**Files:** `app/static/style.css`, `app/templates/admin/{posts,pages,categories,comments}/list.html`, `tests/test_admin_editorial_ui.py`

- [ ] **Step 1:** Extend `tests/test_admin_editorial_ui.py`: delete buttons in the posts, pages, categories and comments lists carry `button--danger` (create one record of each, assert via lxml); `.button--quiet` CSS is transparent and underlined; `.admin-filter--active` is not filled (`background: var(--text-primary)` absent from its rule); `.admin-metric` has `background: transparent`. Run; expect FAIL.
- [ ] **Step 2:** Add `button--danger` next to `button--quiet` on every 删除 button in those four templates (not on 更新/保存/Restore).
- [ ] **Step 3:** Append to `style.css` under `/* Admin: buttons, lists, filters, dashboard, settings. */`:

```css
.admin-site .button--cta { min-height: 40px; border-radius: 6px; }
.admin-site .button--quiet { min-height: 34px; padding: 0 4px; color: var(--text-secondary); background: transparent; border: 0; font-weight: 400; text-decoration: underline; }
.admin-site .button--quiet:hover, .admin-site .button--quiet:focus { color: var(--text-primary); background: transparent; }
.admin-site .button--quiet.button--danger { color: var(--danger); }
.admin-list__actions a { color: var(--text-secondary); text-decoration: underline; }
.admin-list__actions a:hover { color: var(--text-primary); }
.admin-list { border-top: 0; }
.admin-list__row { padding: 16px 0; }
.admin-list__main a { color: var(--text-primary); text-decoration: none; }
.admin-list__main strong { font-family: var(--system-font); font-size: 17px; font-weight: 700; letter-spacing: -.02em; }
.admin-list__main span, .admin-list__meta { font-size: 13px; }
.admin-filters { margin-bottom: 28px; gap: 24px; border-bottom: 1px solid var(--border); }
.admin-filter { min-height: 36px; padding: 0 0 10px; margin-bottom: -1px; color: var(--text-secondary); background: transparent; border: 0; border-bottom: 2px solid transparent; border-radius: 0; }
.admin-filter--active, .admin-filter:hover, .admin-filter:focus { color: var(--text-primary); background: transparent; }
.admin-filter--active { border-bottom-color: var(--text-primary); }
.admin-dashboard { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 40px; }
.admin-metric { padding: 0; background: transparent; border: 0; border-radius: 0; }
.admin-metric__value { font-family: 'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif; font-size: 48px; font-weight: 600; }
.admin-notice { background: transparent; border-left: 2px solid var(--text-secondary); }
.env-settings__group { padding: 22px 0 0; background: transparent; border: 0; border-top: 1px solid var(--border); border-radius: 0; }
```
Remove superseded old rules only when they are exact duplicates; otherwise rely on cascade order (new section is last).
- [ ] **Step 4:** Run the full pytest and node suites; expect pass. Commit `feat(admin): quiet buttons, lists, filters and dashboard`.

## Task 4: Verification

- [ ] **Step 1:** Scratch DB under the scratchpad (`db.create_all()`, admin user, a category, 2 posts, 2 content pages, a post comment), `flask run -p 5055`, playwright via `bash $HOME/.claude/skills/playwright/scripts/playwright_cli.sh` (take full refs such as `f8e28` from snapshots, use a tall viewport for login).
- [ ] **Step 2:** Screenshots light and dark at 1440 and 390 of: `/admin/`, `/admin/posts`, `/admin/pages`, `/admin/categories`, `/admin/comments`, `/admin/users`, `/admin/settings`, `/admin/settings/environment`, `/admin/pages/new`. Check no overflow, readable contrast, drawer works at 390, active nav marking, danger buttons.
- [ ] **Step 3:** Fix defects in separate commits; run both suites; stop the server and close the browser.
