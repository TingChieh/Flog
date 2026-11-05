# Apple Editorial Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the complete Flask/Jinja site as a monochrome Apple editorial experience while preserving the homepage lake-and-logo hero and all existing application behavior.

**Architecture:** Consolidate the duplicated base templates into one shared page shell, move global interaction code into one static JavaScript module, and rebuild the existing stylesheet around shared monochrome design tokens. Page templates then opt into a small set of editorial, reading, list, form, and management layouts without changing routes or model contracts.

**Tech Stack:** Flask, Jinja2, Bootstrap 5.3 compatibility, vanilla CSS, vanilla JavaScript, pytest, Flask test client, in-app browser visual verification.

## Global Constraints

- Preserve the current lake image, Aisaka logo, `Hello World!`, `你好世界`, and homepage welcome line.
- Use `SmileySans-Oblique` only for the Aisaka brand and central homepage hero copy.
- Use the native system font stack for navigation, article titles, body text, metadata, forms, and utilities.
- Keep desktop article titles between 24 and 28 pixels and mobile article titles between 20 and 22 pixels.
- Do not show a visible `Continue reading` link.
- Preserve light/dark preference, search, authentication state, comments, likes, QR actions, and all existing routes.
- Keep Bootstrap for compatibility; add no frontend framework and no new runtime dependency.
- Run every Python test command with `DATABASE_URL=sqlite://` so tests cannot touch MySQL.
- Verify at 390 by 844 mobile and 1440 by 900 desktop, in light and dark mode.

---

### Task 1: Shared Page Shell And Interaction Contract

**Files:**
- Create: `app/static/site.js`
- Create: `tests/test_ui_shell.py`
- Modify: `app/__init__.py`
- Modify: `app/templates/base.html`
- Modify: `app/templates/index_base.html`

**Interfaces:**
- Produces: Jinja global `current_year: int`.
- Produces: base blocks `page_hero` and `content`.
- Produces: DOM hooks `[data-nav-toggle]`, `[data-site-nav]`, `[data-theme-toggle]`, and `[data-back-to-top]`.
- Produces: `site.js` behavior that owns navigation expansion, theme switching, back-to-top visibility, and reduced-motion scrolling.
- Consumes: existing `current_user`, `csrf_token`, translations, notifications, Flask-Moment, Bootstrap popovers, and route endpoint names.

- [ ] **Step 1: Write failing shared-shell tests**

```python
# tests/test_ui_shell.py
from datetime import datetime, timezone


def test_public_shell_has_accessible_navigation_footer_and_back_to_top(client):
    response = client.get('/about')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="site-brand"' in html
    assert 'data-nav-toggle' in html
    assert 'data-site-nav' in html
    assert 'data-theme-toggle' in html
    assert 'data-back-to-top' in html
    assert 'aria-label="Back to top"' in html
    assert str(datetime.now(timezone.utc).year) in html
    assert 'static/site.js' in html
    assert '<font' not in html


def test_homepage_preserves_aisaka_hero(client):
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="hero hero--home"' in html
    assert 'images/hero.jpg' not in html  # the asset remains CSS-owned
    assert 'images/aisaka.png' in html
    assert 'Hello World!' in html
    assert '你好世界' in html
    assert '欢迎来到 Aisaka 的空间' in html
```

- [ ] **Step 2: Run the tests and verify the shell contract is missing**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py`

Expected: FAIL because the current templates have no `site-brand`, data hooks,
accessible back-to-top button, shared static script, or dynamic year.

- [ ] **Step 3: Add the dynamic year Jinja global**

```python
# app/__init__.py
from datetime import datetime, timezone


@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now(timezone.utc).year}
```

- [ ] **Step 4: Consolidate the base templates**

Rewrite `base.html` as the single document shell. Keep analytics, Bootstrap,
Moment, popovers, notification polling, flash messages, authenticated links,
search, and CSRF logout. Replace obsolete `font` and `align` markup with:

```html
<nav class="site-nav" aria-label="{{ _('Primary navigation') }}">
  <div class="site-nav__inner">
    <a class="site-brand" href="{{ url_for('index') }}">Aisaka's Blog</a>
    <button class="nav-toggle" type="button" data-nav-toggle
            aria-expanded="false" aria-controls="site-navigation">
      <span class="visually-hidden">{{ _('Toggle navigation') }}</span>
      <span aria-hidden="true"></span><span aria-hidden="true"></span>
    </button>
    <div class="site-nav__menu" id="site-navigation" data-site-nav>
      <!-- Preserve every existing destination and authenticated condition. -->
      <form class="site-search" method="get" action="{{ url_for('search') }}">
        <input type="search" name="q" aria-label="{{ _('Search') }}">
        <button class="icon-button" type="submit" aria-label="{{ _('Search') }}">⌕</button>
      </form>
      <button class="icon-button theme-toggle" type="button" data-theme-toggle
              aria-label="{{ _('Toggle dark mode') }}"></button>
    </div>
  </div>
</nav>
{% block page_hero %}
<header class="hero hero--page"><h1>{{ title }}</h1></header>
{% endblock %}
<main class="site-main" id="main-content">
  <!-- tasks, flash messages, then block content -->
</main>
<button class="back-to-top" type="button" data-back-to-top
        aria-label="Back to top" hidden>↑</button>
<footer class="site-footer">
  <div class="site-footer__inner">
    <p>Aisaka's Blog · 思考、记录，以及日常生活。</p>
    <div class="site-footer__meta">
      <span>Copyright &copy; {{ current_year }} Aisaka</span>
      <!-- Preserve Powered by Flog and Login/Logout. -->
    </div>
  </div>
</footer>
<script src="{{ url_for('static', filename='site.js') }}"></script>
```

Reduce `index_base.html` to an extension of `base.html` that overrides only
`page_hero`:

```html
{% extends "base.html" %}
{% block page_hero %}
<header class="hero hero--home">
  <div class="hero__inner brand-display">
    <img src="{{ url_for('static', filename='images/aisaka.png') }}"
         width="160" height="160" alt="Aisaka">
    <h1>Hello World!</h1>
    <h2>你好世界</h2>
    <p>欢迎来到 Aisaka 的空间</p>
  </div>
</header>
{% endblock %}
```

- [ ] **Step 5: Implement the interaction module**

```javascript
// app/static/site.js
document.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement;
  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-site-nav]');
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const backToTop = document.querySelector('[data-back-to-top]');
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

  navToggle?.addEventListener('click', () => {
    const open = nav.classList.toggle('site-nav__menu--open');
    navToggle.setAttribute('aria-expanded', String(open));
  });

  themeToggle?.addEventListener('click', () => {
    const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = theme;
    root.dataset.bsTheme = theme;
    localStorage.setItem('theme', theme);
  });

  const syncBackToTop = () => {
    if (!backToTop) return;
    backToTop.hidden = scrollY <= innerHeight;
  };
  addEventListener('scroll', syncBackToTop, {passive: true});
  syncBackToTop();

  backToTop?.addEventListener('click', () => {
    scrollTo({top: 0, behavior: reduceMotion.matches ? 'auto' : 'smooth'});
  });
});
```

- [ ] **Step 6: Run shell and existing tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py`

Expected: PASS.

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`

Expected: all tests PASS with no MySQL connection attempt.

- [ ] **Step 7: Commit the shared shell**

```bash
git add app/__init__.py app/static/site.js app/templates/base.html \
  app/templates/index_base.html tests/test_ui_shell.py
git commit -m "refactor: unify the site shell"
```

### Task 2: Monochrome Design System And Responsive Components

**Files:**
- Modify: `app/static/style.css`
- Modify: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: shared shell classes and data hooks from Task 1.
- Produces: CSS custom properties for color, typography, spacing, borders,
  controls, content widths, light/dark themes, and motion.
- Produces: component styles used by all later page-template tasks.

- [ ] **Step 1: Add failing stylesheet contract tests**

```python
from pathlib import Path


def test_stylesheet_uses_monochrome_editorial_tokens():
    css = Path('app/static/style.css').read_text()

    for token in (
        '--page-bg: #ffffff', '--surface-muted: #f5f5f7',
        '--text-primary: #1d1d1f', '--link-color: #0066cc',
        '--content-width: 1080px', '--reading-width: 760px',
    ):
        assert token in css
    assert '--brand-green' not in css
    assert '--medium-green' not in css
    assert '@media (prefers-reduced-motion: reduce)' in css
    assert '.back-to-top' in css
    assert '.site-footer' in css
```

- [ ] **Step 2: Run the token test and verify it fails**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py::test_stylesheet_uses_monochrome_editorial_tokens`

Expected: FAIL because the current green token system is still present.

- [ ] **Step 3: Replace global tokens and typography**

Start `style.css` with these exact foundations, then migrate existing selectors
to consume them:

```css
:root {
  --page-bg: #ffffff;
  --surface: #ffffff;
  --surface-muted: #f5f5f7;
  --text-primary: #1d1d1f;
  --text-secondary: #6e6e73;
  --border: #d2d2d7;
  --link-color: #0066cc;
  --danger: #b42318;
  --content-width: 1080px;
  --reading-width: 760px;
  --control-height: 42px;
  --radius: 8px;
  --system-font: -apple-system, BlinkMacSystemFont, "SF Pro Text",
    "Helvetica Neue", "PingFang SC", Arial, sans-serif;
}

html[data-theme="dark"] {
  color-scheme: dark;
  --page-bg: #000000;
  --surface: #1d1d1f;
  --surface-muted: #161617;
  --text-primary: #f5f5f7;
  --text-secondary: #a1a1a6;
  --border: #424245;
  --link-color: #2997ff;
}

@font-face {
  font-family: "SmileySans-Oblique";
  src: url("fonts/SmileySans-Oblique.ttf") format("truetype");
  font-display: swap;
}

body {
  margin: 0;
  background: var(--page-bg);
  color: var(--text-primary);
  font-family: var(--system-font);
  font-size: 16px;
  line-height: 1.6;
  letter-spacing: 0;
  text-align: left;
}

.site-brand,
.brand-display {
  font-family: "SmileySans-Oblique", var(--system-font);
}
```

- [ ] **Step 4: Implement shared component rules**

Define these selectors in the same file with no green fills or decorative
gradients: `.site-nav`, `.site-nav__inner`, `.site-nav__menu`, `.nav-toggle`,
`.icon-button`, `.site-search`, `.hero--home`, `.hero--page`, `.site-main`,
`.page-heading`, `.editorial-list`, `.editorial-post`, `.button`, Bootstrap
`.btn` variants, `.form-control`, `.form-select`, `.form-check-input`,
`.alert`, `.pagination`, `.list-group`, `.empty-state`, `.site-footer`, and
`.back-to-top`.

Required values:

```css
.site-nav { min-height: 48px; background: color-mix(in srgb, var(--page-bg) 88%, transparent); border-bottom: 1px solid var(--border); backdrop-filter: saturate(180%) blur(18px); }
.site-nav__inner { width: min(var(--content-width), calc(100% - 32px)); min-height: 48px; margin: auto; }
.hero--home { min-height: clamp(365px, 48vw, 530px); background: linear-gradient(rgba(0,0,0,.25), rgba(0,0,0,.25)), url("images/hero.jpg") center/cover; }
.site-main { width: min(var(--content-width), calc(100% - 32px)); margin: 0 auto; padding: 42px 0 72px; }
.back-to-top { position: fixed; right: max(16px, env(safe-area-inset-right)); bottom: max(16px, env(safe-area-inset-bottom)); width: 40px; height: 40px; border-radius: 50%; }
.back-to-top[hidden] { display: none; }
.site-footer { background: var(--surface-muted); color: var(--text-secondary); }
.site-footer__inner { width: min(var(--content-width), calc(100% - 32px)); margin: auto; padding: 22px 0 26px; border-top: 1px solid var(--border); }
```

At `max-width: 768px`, make the menu a stable full-width column, use 44-pixel
minimum interactive targets, stack footer metadata, and set editorial titles to
21 pixels. At `min-width: 769px`, set editorial titles to 26 pixels.

- [ ] **Step 5: Add reduced-motion and no-backdrop fallbacks**

```css
@supports not (backdrop-filter: blur(1px)) {
  .site-nav { background: var(--page-bg); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
    animation-duration: .01ms !important;
  }
}
```

- [ ] **Step 6: Run stylesheet and full tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py`

Expected: PASS.

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 7: Commit the design system**

```bash
git add app/static/style.css tests/test_ui_shell.py
git commit -m "style: add the monochrome editorial system"
```

### Task 3: Homepage And Reusable Editorial Post Rows

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/templates/post/_post.html`
- Modify: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: `.editorial-layout`, `.editorial-list`, `.editorial-post`,
  `.post-utilities`, `.category-rail`, and shared button classes from Task 2.
- Preserves: `posts`, `categories`, `prev_url`, `next_url`, permissions, CSRF,
  copy link, QR code, edit, and delete behavior.

- [ ] **Step 1: Add failing homepage structure tests**

```python
def test_homepage_uses_compact_editorial_post_rows(client, users):
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="editorial-layout"' in html
    assert 'class="editorial-list"' in html
    assert 'class="editorial-post"' in html
    assert 'class="editorial-post__title"' in html
    assert 'class="category-rail"' in html
    assert 'Continue reading' not in html
    assert '>Test<' in html
```

- [ ] **Step 2: Run the homepage test and verify it fails**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py::test_homepage_uses_compact_editorial_post_rows`

Expected: FAIL because the current homepage uses legacy post cards.

- [ ] **Step 3: Replace homepage presentation markup**

Use this hierarchy in `index.html`:

```html
<div class="editorial-layout">
  <section aria-labelledby="latest-posts">
    <header class="section-heading">
      <p>{{ _('Latest posts') }}</p>
      <h2 id="latest-posts">{{ title }}</h2>
    </header>
    <div class="editorial-list">
      {% for post in posts %}{% include 'post/_post.html' %}{% endfor %}
    </div>
    <!-- Preserve pagination URLs with shared pagination classes. -->
  </section>
  <aside class="category-rail" aria-labelledby="post-categories">
    <h2 id="post-categories">{{ _('Categories') }}</h2>
    <!-- Preserve category names, counts, and links. -->
  </aside>
</div>
```

Rewrite `_post.html` as one divided article row. The title link is the main
navigation target. Keep author/avatar metadata and utilities outside the title
link so nested controls remain valid HTML:

```html
<article class="editorial-post">
  <div class="editorial-post__meta">
    <a class="user_popup" href="{{ url_for('user', username=post.author.username) }}">
      <img src="{{ post.author.avatar(40) }}" width="40" height="40" alt="">
      <span>{{ post.author.username }}</span>
    </a>
    <time>{{ moment(post.timestamp).fromNow() }}</time>
  </div>
  <a class="editorial-post__link" href="{{ url_for('post', post_id=post.id) }}">
    <h3 class="editorial-post__title">{{ post.title or _('Untitled') }}</h3>
    <p>{{ post.body|striptags|truncate(180) }}</p>
  </a>
  <div class="post-utilities">
    <!-- Preserve copy, QR, edit, delete, CSRF, and permission conditions. -->
  </div>
</article>
```

- [ ] **Step 4: Run homepage and security tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py tests/test_security.py`

Expected: PASS.

- [ ] **Step 5: Commit homepage markup**

```bash
git add app/templates/index.html app/templates/post/_post.html tests/test_ui_shell.py
git commit -m "style: rebuild the homepage article list"
```

### Task 4: Article Reading, Likes, Actions, And Comments

**Files:**
- Modify: `app/templates/post/post.html`
- Modify: `app/static/style.css`
- Modify: `tests/test_ui_shell.py`
- Test: `tests/test_post_interactions.py`

**Interfaces:**
- Consumes: shared reading, button, form, divider, and responsive tokens.
- Preserves: `post`, `form`, `comments`, `current_user`, sanitization,
  like-toggle route, copy, edit/delete permission conditions, and CSRF.

- [ ] **Step 1: Add failing article-page design assertions**

```python
def test_article_page_uses_reading_layout_and_divided_comments(client, users):
    response = client.get(f'/post/{users["post"]}')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="reading-layout"' in html
    assert 'class="article-header"' in html
    assert 'class="article-body"' in html
    assert 'class="article-actions"' in html
    assert 'class="comments-section"' in html
    assert 'class="comment-form"' in html
    assert 'class="comment-list"' in html
```

- [ ] **Step 2: Run the article test and verify it fails**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py::test_article_page_uses_reading_layout_and_divided_comments`

Expected: FAIL on the new reading-layout class contract.

- [ ] **Step 3: Refine article markup without changing form actions**

Use one `reading-layout` wrapper, a compact author/time `article-header`, the
existing sanitized content inside `article-body`, and `article-actions` for
like/copy/admin controls. Keep comment fields visibly labelled. Keep comments
as siblings separated by borders; do not place comment cards inside a section
card.

```html
<article class="reading-layout">
  <header class="article-header">...</header>
  <div class="article-body">{{ post.body|safe_html }}</div>
  <div class="article-actions">...</div>
</article>
<section class="comments-section" id="comments" aria-labelledby="comments-title">
  <header class="comments-section__heading">
    <h2 id="comments-title">{{ _('Comments') }}</h2>
    <span>{{ comments|length }}</span>
  </header>
  <form method="post" class="comment-form" novalidate>...</form>
  <div class="comment-list">...</div>
</section>
```

- [ ] **Step 4: Add exact reading and comment component CSS**

```css
.reading-layout,
.comments-section { width: min(var(--reading-width), 100%); margin-inline: auto; }
.article-header { display: flex; align-items: center; gap: 12px; margin-bottom: 34px; color: var(--text-secondary); }
.article-body { font-size: 17px; line-height: 1.75; overflow-wrap: anywhere; }
.article-body h1 { font-size: clamp(30px, 5vw, 44px); }
.article-body h2 { font-size: clamp(25px, 4vw, 34px); }
.article-actions { display: flex; flex-wrap: wrap; gap: 10px; padding: 30px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.comments-section { padding-top: 52px; }
.comment-form { padding: 24px 0 36px; border-bottom: 1px solid var(--border); }
.post-comment { display: grid; grid-template-columns: 48px 1fr; gap: 14px; padding: 24px 0; border-bottom: 1px solid var(--border); }
```

- [ ] **Step 5: Run article interaction and security tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_shell.py tests/test_post_interactions.py tests/test_security.py`

Expected: PASS; comment privacy, sanitization, likes, delete cascades, and
permissions remain unchanged.

- [ ] **Step 6: Commit article and comment presentation**

```bash
git add app/templates/post/post.html app/static/style.css tests/test_ui_shell.py
git commit -m "style: refine article reading and comments"
```

### Task 5: Supporting Pages And Management Surfaces

**Files:**
- Modify: `app/templates/about/about.html`
- Modify: `app/templates/about/edit_about.html`
- Modify: `app/templates/comment/comment.html`
- Modify: `app/templates/links.html`
- Modify: `app/templates/edit_link.html`
- Modify: `app/templates/movie/movie.html`
- Modify: `app/templates/movie/movie_edit.html`
- Modify: `app/templates/todo/todo.html`
- Modify: `app/templates/todo/todo_edit.html`
- Modify: `app/templates/post/categories.html`
- Modify: `app/templates/post/edit_category.html`
- Modify: `app/templates/post/edit_post.html`
- Modify: `app/templates/post/posts_by_category.html`
- Modify: `app/templates/post/search_results.html`
- Modify: `app/templates/user/login.html`
- Modify: `app/templates/user/register.html`
- Modify: `app/templates/user/reset_password.html`
- Modify: `app/templates/user/reset_password_request.html`
- Modify: `app/templates/user/user.html`
- Modify: `app/templates/edit_profile.html`
- Modify: `app/templates/send_message.html`
- Modify: `app/templates/messages.html`
- Modify: `app/templates/_message.html`
- Modify: `app/templates/bootstrap_wtf.html`
- Modify: `app/static/style.css`
- Create: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: `.page-heading`, `.content-section`, `.data-list`, `.form-shell`,
  shared controls, pagination, alert, and empty-state classes.
- Preserves: every current form action, field name, validation rendering,
  route URL, permission condition, CSRF token, and pagination URL.

- [ ] **Step 1: Add failing public-page smoke and legacy-markup tests**

```python
import pytest


@pytest.mark.parametrize('path', [
    '/about', '/comment', '/links', '/movie', '/todo', '/categories', '/login',
])
def test_public_pages_render_in_the_shared_design(client, path):
    response = client.get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="site-nav"' in html
    assert 'class="site-footer"' in html
    assert '<font' not in html
    assert 'style="display:inline' not in html


def test_search_results_use_editorial_rows(client, users):
    response = client.get('/search?q=Test')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="editorial-list"' in html
    assert 'class="editorial-post"' in html
```

- [ ] **Step 2: Run public-page tests and verify failures**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_pages.py`

Expected: FAIL on legacy inline presentation and missing shared layout classes.

- [ ] **Step 3: Normalize content and form shells**

For every listed page, use one unframed `.content-section` or a constrained
`.form-shell`; do not nest Bootstrap cards. Use `.page-heading` for the page
title and optional secondary copy. Convert repeated item collections to
`.data-list` with divided `.data-list__item` rows. Preserve all business markup
inside those rows.

Use this form structure through `bootstrap_wtf.html` and page-specific forms:

```html
<section class="form-shell" aria-labelledby="page-title">
  <header class="page-heading"><h1 id="page-title">{{ title }}</h1></header>
  <form method="post" novalidate>
    {{ form.hidden_tag() }}
    <div class="form-field">
      {{ field.label(class='form-label') }}
      {{ field(class='form-control' + (' is-invalid' if field.errors else '')) }}
      {% for error in field.errors %}
      <div class="invalid-feedback">{{ error }}</div>
      {% endfor %}
    </div>
  </form>
</section>
```

Search results must reuse `post/_post.html` so homepage and search presentation
cannot drift. Profile and management pages may use a two-column responsive grid
but must remain full-width page layouts, not nested cards.

- [ ] **Step 4: Add compact functional-surface CSS**

```css
.content-section { width: min(var(--content-width), 100%); margin-inline: auto; }
.form-shell { width: min(620px, 100%); margin-inline: auto; }
.page-heading { margin-bottom: 30px; }
.page-heading h1 { margin: 0; font-size: clamp(30px, 5vw, 44px); line-height: 1.12; }
.data-list { margin: 0; padding: 0; list-style: none; border-top: 1px solid var(--border); }
.data-list__item { padding: 18px 0; border-bottom: 1px solid var(--border); }
.form-field { margin-bottom: 20px; }
.form-label { display: block; margin-bottom: 7px; font-size: 14px; font-weight: 600; }
.form-control, .form-select { min-height: var(--control-height); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--text-primary); }
.form-control:focus, .form-select:focus { border-color: var(--link-color); box-shadow: 0 0 0 3px color-mix(in srgb, var(--link-color) 22%, transparent); }
.invalid-feedback { display: block; margin-top: 6px; color: var(--danger); }
```

- [ ] **Step 5: Run page smoke, security, and full tests**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q tests/test_ui_pages.py tests/test_security.py`

Expected: PASS.

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit supporting pages**

```bash
git add app/templates app/static/style.css tests/test_ui_pages.py
git commit -m "style: unify supporting pages and forms"
```

### Task 6: Browser Verification And Before/After Assets

**Files:**
- Create: `instance/backups/ui-after-apple-2026-08-20/home-desktop.png`
- Create: `instance/backups/ui-after-apple-2026-08-20/post-desktop.png`
- Create: `instance/backups/ui-after-apple-2026-08-20/home-mobile.png`
- Create: `instance/backups/ui-after-apple-2026-08-20/post-mobile.png`
- Modify: `docs/superpowers/plans/2026-08-20-apple-editorial-redesign.md` (checkbox status only)

**Interfaces:**
- Consumes: completed Flask UI, saved before screenshots, and local MySQL data
  for read-only visual rendering.
- Produces: fixed-viewport after screenshots and an evidence-backed completion
  report.

- [x] **Step 1: Run the complete automated verification**

Run: `DATABASE_URL=sqlite:// .venv/bin/python -m pytest -q`

Expected: all tests PASS and output shows no warnings about a MySQL connection.

Run: `git diff --check`

Expected: no whitespace errors.

- [x] **Step 2: Start the local application for visual verification**

Run: `set -a; source .env; .venv/bin/flask run --host 127.0.0.1 --port 5001`

Expected: Flask serves the restored `flog` database at
`http://127.0.0.1:5001/`. Do not submit forms or run tests in this environment.

- [x] **Step 3: Verify desktop light and dark states at 1440 by 900**

Using the in-app browser:

- open `/` and `/post/29`;
- verify the homepage hero still shows the lake, Aisaka logo, 得意黑 welcome
  copy, and no layout overlap;
- verify article titles are 24 to 28 pixels and there is no visible
  `Continue reading` link;
- scroll beyond one viewport, confirm the circular up-arrow appears, activate
  it, and confirm the page returns to the top;
- scroll to the bottom and confirm Footer content and login state remain usable;
- switch light/dark mode and confirm neutral monochrome surfaces in both;
- inspect browser console logs for errors and missing assets.

- [x] **Step 4: Verify responsive and interaction states at 390 by 844**

Using the same browser session:

- verify `/` and `/post/29` at 390 by 844;
- open and close mobile navigation and confirm it does not overlap the hero or
  cause horizontal scrolling;
- confirm article titles remain 20 to 22 pixels and long Chinese/English titles
  wrap without clipping;
- confirm form fields, like button, comment form, footer, and back-to-top button
  remain reachable with stable dimensions;
- set reduced motion through page emulation if supported and confirm the page
  remains functional without animation.

- [x] **Step 5: Save after screenshots and compare against the baseline**

Save viewport screenshots for homepage and `/post/29` at 1440 by 900 and 390
by 844 under `instance/backups/ui-after-apple-2026-08-20/`. Compare them with
the corresponding PNGs under `instance/backups/ui-before-apple-2026-08-20/`.
Reject the result if the central homepage hero is substantially changed, any
text overlaps, the Footer is missing, the back-to-top control blocks content,
or the UI remains green-dominant.

- [x] **Step 6: Commit the final verified implementation**

Do not stage generated screenshots unless the repository explicitly tracks
`instance/backups`. Stage only implementation, tests, and plan checkbox edits:

```bash
git add app tests docs/superpowers/plans/2026-08-20-apple-editorial-redesign.md
git commit -m "feat: complete the Apple editorial redesign"
```
