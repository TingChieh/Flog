# Public Pages Consistency And Navigation Typography Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the remaining public pages up to the editorial look of the home/archive/links/login pages, and give the nav a serif brand and menu that matches the site's Chinese body font, with inline links on desktop.

**Architecture:** Template wiring (`page_hero` override, `public-page` container, `public-label` eyebrow) plus a small CSS block appended to the `public-site` section of `style.css`. One shared pager macro replaces three copies of Bootstrap pagination. Navigation fonts come from the existing self-hosted `fonts/article-fonts.css`, now linked from `base.html`.

**Tech Stack:** Flask/Jinja2, Flask-Babel (`_()`), plain CSS, pytest with lxml, node test runner.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-05-public-pages-consistency-design.md`.
- Routes, forms, variables, permissions and models do not change.
- Run tests with `.venv/bin/python -m pytest -q` from the repo root. Baseline before this plan: **609 passed**.
- All new CSS is appended inside/after the `public-site` section at the end of `app/static/style.css`; use existing variables only, no new tokens.
- Desktop inline menu breakpoint: viewport width >= 1200px. Below that the hamburger and dropdown are unchanged.
- Brand/menu font stack: `'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif`. Controls (search trigger, theme selector, unread badge) stay on `var(--system-font)`.
- New user-visible strings are wrapped in `_()`. Do not touch or regenerate `app/translations/**/*.mo` (they have unrelated uncommitted changes); never `git add` them.
- Each commit stages only the files named in its task. Never use `git add -A`.
- Existing `hidden`, `data-nav-toggle`, `aria-controls="site-navigation"` markup stays so current tests hold.

## File Structure

- Modify `app/templates/base.html`: link `fonts/article-fonts.css`, preload the Latin font.
- Modify `app/templates/post/post.html`: drop its own `article-fonts.css` link (now in base).
- Create `app/templates/_pager.html`: `pager(prev_url, next_url, newer_label, older_label, aria_label)` macro.
- Modify (templates, page wiring): `edit_profile.html`, `send_message.html`, `user/reset_password.html`, `user/reset_password_request.html`, `post/edit_post.html`, `edit_link.html`, `post/edit_category.html`, `about/edit_about.html`, `movie/movie_edit.html`, `todo/todo_edit.html`, `messages.html`, `movie/movie.html`, `todo/todo.html`, `post/posts_by_category.html`, `user/user.html`, `user/user_popup.html`, `_message.html`, `error/500.html`.
- Modify `app/static/style.css`: append new rules; delete superseded old rules (Task 5).
- Modify tests: `tests/test_article_enhancements.py`, `tests/test_ui_pages.py`, `tests/test_editorial_redesign.py`; create `tests/test_public_pages_consistency.py`.

---

### Task 1: Navigation typography and desktop inline menu

**Files:**
- Modify: `app/templates/base.html` (head, near line 29-30)
- Modify: `app/templates/post/post.html:8`
- Modify: `app/static/style.css` (append at end of file)
- Modify: `tests/test_article_enhancements.py:5-12`
- Create: `tests/test_public_pages_consistency.py`

**Interfaces:**
- Produces: `fonts/article-fonts.css` is linked on every page; `tests/test_public_pages_consistency.py` with helper `PUBLIC_STYLESHEET` and `get_page(client, path)` that later tasks extend.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_public_pages_consistency.py`:

```python
from pathlib import Path

from lxml import html as lxml_html

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'
SERIF_STACK = "'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif"


def get_page(client, path, **kwargs):
    response = client.get(path, **kwargs)
    return response, lxml_html.fromstring(response.get_data(as_text=True))


def test_every_page_loads_the_article_fonts_once(client, users):
    home = client.get('/').get_data(as_text=True)
    article = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert home.count('fonts/article-fonts.css') == 1
    assert article.count('fonts/article-fonts.css') == 1


def test_latin_brand_font_is_preloaded(client):
    page = lxml_html.fromstring(client.get('/').get_data(as_text=True))
    preload = page.xpath('//link[@rel="preload"][@as="font"]')
    assert preload
    assert preload[0].get('href').endswith('fonts/source-serif-4-normal-latin.woff2')
    assert preload[0].get('crossorigin') is not None


def test_brand_and_menu_links_use_the_serif_stack():
    css = STYLESHEET.read_text()
    assert f'.public-site .site-brand {{ font-family: {SERIF_STACK};' in css
    assert f'.public-site .site-nav__links a {{ font-family: {SERIF_STACK};' in css


def test_desktop_breakpoint_shows_links_inline():
    css = STYLESHEET.read_text()
    assert '@media (width >= 1200px)' in css
    block = css[css.index('@media (width >= 1200px)'):]
    assert '.public-site .nav-toggle { display: none; }' in block
    assert '.public-site .site-nav__menu[hidden]' in block
```

Edit `tests/test_article_enhancements.py`: the fonts CSS is no longer article-only. Replace lines 8-11 with:

```python
    for asset in ('vendor/photoswipe/photoswipe.css', 'article-enhancements.js'):
        assert asset in article
        assert asset not in home
    assert 'fonts/article-fonts.css' in article
    assert 'fonts/article-fonts.css' in home
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py tests/test_article_enhancements.py -v`
Expected: FAIL (home has no `article-fonts.css`, no preload, CSS rules missing).

- [ ] **Step 3: Implement templates**

In `app/templates/base.html`, replace line 29-30:

```html
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    {% block page_styles %}{% endblock %}
```

with:

```html
    <link rel="preload" as="font" type="font/woff2" crossorigin href="{{ url_for('static', filename='fonts/source-serif-4-normal-latin.woff2') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='fonts/article-fonts.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    {% block page_styles %}{% endblock %}
```

In `app/templates/post/post.html`, delete line 8 (`<link rel="stylesheet" href="{{ url_for('static', filename='fonts/article-fonts.css') }}">`), leaving the photoswipe link.

- [ ] **Step 4: Implement CSS**

Append to the end of `app/static/style.css`:

```css

/* Navigation: serif brand and menu that match the Chinese body font. */
.public-site .site-brand { font-family: 'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif; font-size: 22px; font-weight: 600; letter-spacing: 0; }
.public-site .site-nav__links a { font-family: 'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif; font-size: 15px; font-weight: 500; }
.public-site .search-trigger,
.public-site .theme-selector,
.public-site .site-nav__links .badge { font-family: var(--system-font); }

/* Desktop: links sit inline in the bar; below 1200px the hamburger panel is unchanged. */
@media (width >= 1200px) {
    .public-site .nav-toggle { display: none; }
    .public-site .site-nav__menu,
    .public-site .site-nav__menu[hidden] {
        position: static;
        width: auto;
        flex: 1;
        padding: 0;
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        align-items: center;
        justify-content: flex-end;
        gap: 8px 14px;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
    }
    .public-site .site-nav__links { flex-direction: row; flex-wrap: wrap; align-items: center; margin-inline: auto; }
    .public-site .site-nav__menu .theme-selector { align-self: center; }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py tests/test_article_enhancements.py tests/test_article_fonts.py tests/test_ui_shell.py tests/test_editorial_redesign.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/templates/base.html app/templates/post/post.html app/static/style.css tests/test_article_enhancements.py tests/test_public_pages_consistency.py
git commit -m "feat(ui): serif brand and menu, inline desktop navigation"
```

---

### Task 2: Form pages

**Files:**
- Modify: `app/templates/edit_profile.html`, `send_message.html`, `user/reset_password.html`, `user/reset_password_request.html`, `post/edit_post.html`, `edit_link.html`, `post/edit_category.html`, `about/edit_about.html`, `movie/movie_edit.html`, `todo/todo_edit.html`
- Test: `tests/test_public_pages_consistency.py`

**Interfaces:**
- Consumes: `get_page` from Task 1.
- Produces: form-page convention: `{% block page_hero %}{% endblock %}`, `<section class="form-shell public-page" aria-labelledby="page-title">`, heading block `<div class="public-label">{{ _('...') }}</div><h1 id="page-title">`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_public_pages_consistency.py`:

```python
import pytest

from app import db
from app.models import Link, Movie, Todo
from tests.conftest import login


@pytest.fixture()
def member(client, users):
    login(client, 'author')
    return users


def assert_public_form(page, label):
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "form-shell") and contains(@class, "public-page")]')
    assert page.xpath(f'//div[@class="public-label"][normalize-space()="{label}"]')
    assert len(page.xpath('//h1')) == 1


@pytest.mark.parametrize(('path', 'label'), [
    ('/edit_profile', 'Profile'),
    ('/send_message/other', 'Messages'),
    ('/reset_password_request', 'Account'),
])
def test_account_form_pages_use_public_form_shell(client, member, path, label):
    client.get('/logout')
    if path != '/reset_password_request':
        login(client, 'author')
    response, page = get_page(client, path)
    assert response.status_code == 200
    assert_public_form(page, label)


def test_edit_post_category_and_link_forms_use_public_form_shell(client, application, users):
    login(client, 'admin')
    with application.app_context():
        link = Link(name='L', email='l@example.com', text='t', url='https://l.example.com')
        db.session.add(link)
        db.session.commit()
        link_id = link.id
    for path, label in [(f'/edit_post/{users["post"]}', 'Edit'),
                        ('/edit_category/1', 'Edit'),
                        (f'/edit_link/{link_id}', 'Edit')]:
        response, page = get_page(client, path)
        assert response.status_code == 200, path
        assert_public_form(page, label)


def test_movie_and_todo_edit_forms_use_public_form_shell(client, application, users):
    login(client, 'admin')
    with application.app_context():
        movie = Movie(title='M', year='2020')
        todo = Todo(title='T', complete=False)
        db.session.add_all([movie, todo])
        db.session.commit()
        movie_id, todo_id = movie.id, todo.id
    for path in (f'/movie/edit/{movie_id}', f'/todo/edit/{todo_id}'):
        response, page = get_page(client, path)
        assert response.status_code == 200, path
        assert_public_form(page, 'Edit')
```

Before running, confirm the real URLs: `grep -n "@app.route" app/routes.py | grep -E "edit_post|edit_category|edit_link|edit_about|edit_profile"` and the `Movie` model name/fields; adjust the paths in the test to match (some edit routes may be under `/admin` or require a different method). If an edit route is unreachable for the test user, log in as `admin`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py -k "form" -v`
Expected: FAIL (still `hero--page`, no `public-page`, no label).

- [ ] **Step 3: Implement the template changes**

For each file, add `{% block page_hero %}{% endblock %}` after the `{% extends %}`/`{% import %}` lines, change the container to `form-shell public-page`, and add the `public-label` div as the first child of `page-heading`. Concrete results:

`app/templates/edit_profile.html`:
```html
{% extends "base.html" %}
{% import "bootstrap_wtf.html" as wtf %}

{% block page_hero %}{% endblock %}

{% block content %}
  <section class="form-shell public-page" aria-labelledby="page-title">
    <header class="page-heading">
      <div class="public-label">{{ _('Profile') }}</div>
      <h1 id="page-title">{{ _('Edit Profile') }}</h1>
    </header>
    {{ wtf.quick_form(form) }}
  </section>
{% endblock %}
```

`send_message.html`: same shape; label `{{ _('Messages') }}`; keep `<h1 id="page-title">{{ _('Send Message to %(recipient)s', recipient=recipient) }}</h1>`.

`user/reset_password_request.html` and `user/reset_password.html`: same shape; label `{{ _('Account') }}`; keep existing `h1` text.

`post/edit_post.html`:
```html
{% extends 'base.html' %}
{% from 'bootstrap_wtf.html' import quick_form %}

{% block title %}{{ _('Edit Post') }}{% endblock %}
{% block page_hero %}{% endblock %}

{% block content %}
<section class="form-shell public-page" aria-labelledby="page-title">
  <header class="page-heading">
    <div class="public-label">{{ _('Edit') }}</div>
    <h1 id="page-title">{{ _('Edit Post') }}</h1>
  </header>
  {{ quick_form(form, action=url_for('edit_post', post_id=post.id)) }}
</section>
{% endblock %}
```

`edit_link.html`: `{% block title %}{{ _('Edit Link') }}{% endblock %}`, add `page_hero` override, container `form-shell public-page`, heading `<div class="public-label">{{ _('Edit') }}</div><h1 id="page-title">{{ _('Edit Link') }}</h1>`; wrap the Cancel text in `{{ _('Cancel') }}` and the four placeholders in `_()` (`_('Enter the name')`, `_('Enter the email')`, `_('Enter the text')`, `_('Enter the URL')`). Keep all other markup.

`post/edit_category.html`: title/h1 `{{ _('Edit Category') }}`, label `{{ _('Edit') }}`, page_hero override, container class.

`about/edit_about.html`: label `{{ _('Edit') }}`, page_hero override, container class; titles already use `_()`.

`movie/movie_edit.html` and `todo/todo_edit.html`: page_hero override, container class, label `{{ _('Edit') }}`, `h1` text wrapped as `{{ _('Edit item') }}` and `{{ _('Edit Todo') }}` (also the `{% block title %}` in todo_edit).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py tests/test_ui_pages.py tests/test_pages.py tests/test_security.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/edit_profile.html app/templates/send_message.html app/templates/user/reset_password.html app/templates/user/reset_password_request.html app/templates/post/edit_post.html app/templates/edit_link.html app/templates/post/edit_category.html app/templates/about/edit_about.html app/templates/movie/movie_edit.html app/templates/todo/todo_edit.html tests/test_public_pages_consistency.py
git commit -m "feat(ui): editorial shell for edit and account form pages"
```

---

### Task 3: List pages and shared pager

**Files:**
- Create: `app/templates/_pager.html`
- Modify: `app/templates/messages.html`, `movie/movie.html`, `todo/todo.html`, `post/posts_by_category.html`, `_message.html`
- Modify: `app/static/style.css` (append)
- Modify: `tests/test_ui_pages.py` (the profile/messages assertion block, around lines 455-465)
- Test: `tests/test_public_pages_consistency.py`

**Interfaces:**
- Produces: macro `pager(prev_url, next_url, newer_label, older_label, aria_label)` in `_pager.html`, imported with `{% from '_pager.html' import pager %}`. Renders `<nav class="search-pagination" aria-label="...">` with an `<a>` only for each non-empty URL. Task 4 reuses it for the profile page.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_public_pages_consistency.py`:

```python
from app.models import Page


def publish_module(path, key, title):
    db.session.add(Page(title=title, slug=path.removeprefix('/'), kind='module',
                        module_key=key, is_published=True, show_in_nav=True,
                        nav_order=10))


def assert_public_list(page, label):
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "content-section") and contains(@class, "public-page")]')
    assert page.xpath(f'//div[@class="public-label"][normalize-space()="{label}"]')
    assert not page.xpath('//ul[contains(@class, "pagination")]')


def test_messages_page_uses_public_list_and_pager(client, member):
    response, page = get_page(client, '/messages')
    assert response.status_code == 200
    assert_public_list(page, 'Messages')
    assert page.xpath('//div[@class="data-list"]')


def test_movie_page_uses_public_list(client, application):
    with application.app_context():
        publish_module('/movie', 'movie', 'Movie')
        db.session.add(Movie(title='Totoro', year='1988'))
        db.session.commit()
    response, page = get_page(client, '/movie')
    assert response.status_code == 200
    assert_public_list(page, 'Movies')
    link = page.xpath('//a[contains(@class, "imdb")]')[0]
    assert 'btn' not in link.get('class')


def test_todo_pagination_uses_pager_links(client, application, monkeypatch):
    monkeypatch.setitem(application.config, 'POSTS_PER_PAGE', 1)
    with application.app_context():
        publish_module('/todo', 'todo', 'Todo')
        db.session.add_all([Todo(title='First', complete=False),
                            Todo(title='Second', complete=True)])
        db.session.commit()
    response, page = get_page(client, '/todo?page=2')
    assert_public_list(page, 'Todo')
    hrefs = page.xpath('//nav[@class="search-pagination"]/a/@href')
    assert hrefs == ['/todo?page=1']


def test_category_page_uses_public_list(client, users):
    response, page = get_page(client, '/category/1')
    assert response.status_code == 200
    assert_public_list(page, 'Category')
    assert page.xpath('//div[contains(@class, "editorial-list")]')
```

Verify the category URL with `grep -n "posts_by_category" app/routes.py` and adjust. Update `tests/test_ui_pages.py` (the block that asserts `'class="content-section"' in messages`): change the messages assertion to `'class="content-section public-page"' in messages` and keep `'class="data-list"' in messages`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py -k "messages or movie or todo or category" -v`
Expected: FAIL.

- [ ] **Step 3: Create the pager macro**

`app/templates/_pager.html`:

```html
{% macro pager(prev_url, next_url, newer_label, older_label, aria_label) %}
<nav class="search-pagination" aria-label="{{ aria_label }}">
  {% if prev_url %}<a href="{{ prev_url }}" rel="prev"><span aria-hidden="true">&larr;</span> {{ newer_label }}</a>{% endif %}
  {% if next_url %}<a href="{{ next_url }}" rel="next">{{ older_label }} <span aria-hidden="true">&rarr;</span></a>{% endif %}
</nav>
{% endmacro %}
```

- [ ] **Step 4: Rewrite the list templates**

`messages.html`:
```html
{% extends "base.html" %}
{% from '_pager.html' import pager %}

{% block page_hero %}{% endblock %}

{% block content %}
  <section class="content-section public-page" aria-labelledby="page-title">
    <header class="page-heading">
      <div class="public-label">{{ _('Messages') }}</div>
      <h1 id="page-title">{{ _('Messages') }}</h1>
    </header>
    <div class="data-list">
    {% for post in messages %}
      {% include '_message.html' %}
    {% endfor %}
    </div>
    {% if not messages %}<div class="empty-state"><p>{{ _('No messages yet.') }}</p></div>{% endif %}
    {{ pager(prev_url, next_url, _('Newer messages'), _('Older messages'), _('Message navigation')) }}
  </section>
{% endblock %}
```

`todo/todo.html`: keep `{% block title %}`; add the `from '_pager.html' import pager` line and `page_hero` override; container `content-section public-page`; heading with `<div class="public-label">{{ _('Todo') }}</div>`; replace the `<nav>…</nav>` with `{{ pager(prev_url, next_url, _('Newer posts'), _('Older posts'), _('Post navigation')) }}`. Keep the list and `empty-state`. Completed items: replace the class `text-decoration-line-through text-muted` with `todo-title--done` (styled in Step 5), i.e. `<span class="todo-title{% if todo.complete %} todo-title--done{% endif %}">`.

`movie/movie.html`: add `page_hero` override; container `content-section public-page`; `<div class="public-label">{{ _('Movies') }}</div>` before the `h1`; replace `<p>{{ movies|length }} Titles</p>` with `<p>{{ ngettext('%(num)s title', '%(num)s titles', movies|length) }}</p>`; the IMDb anchor becomes `<a class="imdb" href="https://www.imdb.com/find?q={{ movie.title|urlencode }}" target="_blank" rel="noopener noreferrer" title="{{ _('Find this movie on IMDb') }}">IMDb</a>` (no `btn` classes). Keep the totoro `img`.

`post/posts_by_category.html`: `{% block title %}{{ _('Posts in %(name)s', name=category.name) }}{% endblock %}`; `page_hero` override; container `content-section public-page`; heading `<div class="public-label">{{ _('Category') }}</div><h1 id="page-title">{{ _('Posts in %(name)s', name=category.name) }}</h1>`; empty state `{{ _('No posts available in this category.') }}`.

`_message.html`: change `width="70" height="70"` to `width="40" height="40"` and `post.author.avatar(70)` to `post.author.avatar(40)`.

- [ ] **Step 5: Append CSS**

```css

/* Quiet list rows for messages, movies and todos. */
.public-site .public-page .data-list { border-top: 0; }
.public-site .public-page .message-row { padding: 18px 0; }
.public-site .message-row__header img { width: 40px; height: 40px; }
.public-site .message-row__header { align-items: center; gap: 12px; }
.public-site .message-row__header time { display: inline; margin: 0 0 0 8px; }
.public-site .movie-item { border-bottom: 0; }
.public-site .movie-item .imdb { color: var(--text-secondary); font-size: 14px; text-decoration: underline; }
.public-site .todo-title--done { color: var(--text-secondary); text-decoration: line-through; }
.public-site .public-page .search-pagination { margin-top: 32px; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py tests/test_ui_pages.py tests/test_pages.py tests/test_public_profiles.py -q`
Expected: PASS (`test_todo_pagination_preserves_page_urls` still sees `href="/todo?page=1"` and `class="data-list"`).

- [ ] **Step 7: Commit**

```bash
git add app/templates/_pager.html app/templates/messages.html app/templates/movie/movie.html app/templates/todo/todo.html app/templates/post/posts_by_category.html app/templates/_message.html app/static/style.css tests/test_ui_pages.py tests/test_public_pages_consistency.py
git commit -m "feat(ui): editorial list pages with shared text pager"
```

---

### Task 4: Profile page and user popover

**Files:**
- Modify: `app/templates/user/user.html`, `app/templates/user/user_popup.html`
- Modify: `app/static/style.css` (append)
- Modify: `tests/test_ui_pages.py` (profile `content-section` assertion), `tests/test_public_profiles.py` only if a heading assertion breaks
- Test: `tests/test_public_pages_consistency.py`

**Interfaces:**
- Consumes: `pager` macro from Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_public_pages_consistency.py`:

```python
def test_profile_page_uses_public_layout(client, application, users):
    response, page = get_page(client, '/user/author')
    assert response.status_code == 200
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "content-section") and contains(@class, "public-page")]')
    assert page.xpath('//div[@class="public-label"][normalize-space()="Profile"]')
    assert page.xpath('//h1')[0].text_content().strip() == 'author'
    avatar = page.xpath('//img[contains(@class, "profile-avatar")]')[0]
    assert avatar.get('width') == '96'
    assert 's=96' in avatar.get('src')
    assert page.xpath('//div[contains(@class, "editorial-list") and contains(@class, "profile-posts")]')


def test_profile_pagination_uses_pager(client, application, users, monkeypatch):
    monkeypatch.setitem(application.config, 'POSTS_PER_PAGE', 1)
    with application.app_context():
        author = db.session.get(Post, users['post']).author
        category = db.session.get(Post, users['post']).category
        db.session.add(Post(title='Older', body='Body', author=author,
                            category=category, is_published=True))
        db.session.commit()
    _, page = get_page(client, '/user/author?page=1')
    assert page.xpath('//nav[@class="search-pagination"]/a/@href') == ['/user/author?page=2']
    assert not page.xpath('//ul[contains(@class, "pagination")]')


def test_user_popup_has_no_inline_styles(client, users):
    body = client.get('/user/author/popup').get_data(as_text=True)
    assert 'style=' not in body
    assert 'user-popup' in body
```

Add `from app.models import Post` to that file's imports if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py -k "profile or popup" -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `user/user.html`**

```html
{% extends "base.html" %}
{% from '_pager.html' import pager %}

{% block page_hero %}{% endblock %}

{% block content %}
<section class="content-section public-page" aria-labelledby="page-title">
  <div class="profile-layout">
    <img src="{{ user.avatar(96) }}" class="profile-avatar" width="96" height="96" alt="{{ user.username }}">
    <div class="profile-details">
      <header class="page-heading">
        <div class="public-label">{{ _('Profile') }}</div>
        <h1 id="page-title">{{ user.username }}</h1>
      </header>
      {% if user.about_me %}<p>{{ user.about_me }}</p>{% endif %}
      {% if user.last_seen %}<p class="profile-meta">{{ _('Last seen on') }}: {{ moment(user.last_seen).format('LLL') }}</p>{% endif %}
      {% if current_user.is_authenticated %}
      <div class="profile-actions">
        {% if user == current_user %}
        <a href="{{ url_for('edit_profile') }}">{{ _('Edit your profile') }}</a>
        {% if not current_user.get_task_in_progress('export_posts') %}
        <a href="{{ url_for('export_posts') }}">{{ _('Export your posts') }}</a>
        {% endif %}
        {% else %}
        <a href="{{ url_for('send_message', recipient=user.username) }}">{{ _('Send private message') }}</a>
        {% endif %}
      </div>
      {% endif %}
    </div>
  </div>
  <div class="editorial-list profile-posts">
    {% for post in posts %}
    {% include 'post/_post.html' %}
    {% endfor %}
  </div>
  {% if not posts %}<div class="empty-state"><p>{{ _('No posts yet.') }}</p></div>{% endif %}
  {{ pager(prev_url, next_url, _('Newer posts'), _('Older posts'), _('Post navigation')) }}
</section>
{% endblock %}
```

Check that `test_public_profiles.py` assertions (`'author' in html`, `Public biography`, `Last seen on`, `cravatar.cn/avatar/`) still pass; they do not depend on the old "User:" prefix. If any test asserts `User:` or `btn`, update it to the new markup.

- [ ] **Step 4: Rewrite `user/user_popup.html`**

```html
<div class="user-popup">
    <img class="user-popup__avatar" src="{{ user.avatar(64) }}" width="64" height="64" alt="">
    <p><a href="{{ url_for('user', username=user.username) }}">{{ user.username }}</a></p>
    {% if user.about_me %}<p>{{ user.about_me }}</p>{% endif %}
    <div class="clearfix"></div>
    {% if user.last_seen %}
    <p>{{ _('Last seen on') }}: {{ moment(user.last_seen).format('lll') }}</p>
    {% endif %}
</div>
```

- [ ] **Step 5: Append CSS**

```css

/* Profile: compact avatar beside the bio; quiet text actions. */
.public-site .public-page .profile-layout { grid-template-columns: 96px minmax(0, 1fr); gap: 24px; }
.public-site .profile-avatar { width: 96px; height: 96px; }
.public-site .profile-details .page-heading { margin-bottom: 16px; }
.public-site .profile-details p { margin: 0 0 12px; }
.public-site .profile-meta { color: var(--text-secondary); font-size: 14px; }
.public-site .profile-actions { gap: 20px; }
.public-site .profile-actions a { color: var(--text-secondary); text-decoration: underline; min-height: 44px; display: inline-flex; align-items: center; }
.public-site .profile-posts { margin-top: 56px; }
@media (width <= 768px) {
    .public-site .public-page .profile-layout { grid-template-columns: minmax(0, 1fr); gap: 16px; }
    .public-site .profile-avatar { width: 96px; }
}
.user-popup__avatar { margin: 5px; float: left; }
```

- [ ] **Step 6: Update the existing assertion and run tests**

In `tests/test_ui_pages.py`, change the profile assertion `'class="content-section"' in profile` to `'class="content-section public-page"' in profile` (keep `profile-layout` and `editorial-list profile-posts`).

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py tests/test_ui_pages.py tests/test_public_profiles.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/templates/user/user.html app/templates/user/user_popup.html app/static/style.css tests/test_ui_pages.py tests/test_public_pages_consistency.py
git commit -m "feat(ui): editorial profile page and class-based user popover"
```

---

### Task 5: 500 page, legacy CSS cleanup, full verification

**Files:**
- Modify: `app/templates/error/500.html`
- Modify: `app/static/style.css` (remove superseded rules)
- Test: `tests/test_public_pages_consistency.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_public_pages_consistency.py`:

```python
def test_500_page_matches_the_404_structure(application, client, monkeypatch):
    application.config['PROPAGATE_EXCEPTIONS'] = False
    application.config['TESTING'] = False

    @application.route('/__boom')
    def boom():
        raise RuntimeError('boom')

    try:
        response = client.get('/__boom')
    finally:
        application.config['TESTING'] = True
        application.view_functions.pop('boom', None)
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert response.status_code == 500
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "public-error")]')
    assert page.xpath('//p[@class="public-label"][normalize-space()="500"]')
```

If registering a route after the first request raises in this Flask version, instead call the handler directly: `with application.test_request_context(): from app.errors import internal_error; body, status = internal_error(Exception())` and parse `body`. Use whichever works; keep the assertions.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_public_pages_consistency.py -k 500 -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `error/500.html`**

```html
{% extends "base.html" %}

{% block page_hero %}{% endblock %}

{% block content %}
    <section class="content-section public-page public-error">
      <header class="page-heading"><p class="public-label">500</p><h1>{{ _('An unexpected error has occurred') }}</h1></header>
      <p>{{ _('The administrator has been notified. Sorry for the inconvenience!') }}</p>
      <p><a href="{{ url_for('index') }}">{{ _('Back') }}</a></p>
    </section>
{% endblock %}
```

- [ ] **Step 4: Remove superseded CSS**

For each selector below, first run `grep -rn "<name>" app/templates app/static/*.js` (names without the dot). Only delete a rule if there is no match outside `style.css`: `.post-item`, `.post-header` (and `.post-header img`), `.post-body`, `.post-footer` (and `.post-footer .btn, .post-footer .inline-form`), `.movie-form .form-group`. In `.movie-item`, remove the hardcoded `border-bottom: 1px solid #ccc;` line. Record in the commit message which selectors were removed. If a selector is still referenced, leave it.

- [ ] **Step 5: Full automated verification**

Run:
```bash
.venv/bin/python -m pytest -q
node --test tests/
```
Expected: pytest all pass (>= 609 plus the new tests); node tests pass.

- [ ] **Step 6: Visual verification (playwright skill)**

Start the app (`.venv/bin/flask run` or the project's documented run command, with a local sqlite DB and a seeded admin user). With the playwright skill, screenshot light and dark at 390, 768, 1200 and 1440 widths: home, `/messages`, `/movie`, `/todo`, `/user/<name>`, `/edit_profile`, `/login`, a forced 500, plus the open mobile menu at 390 and the inline menu at 1200 and 1440. Check: no legacy banner, no horizontal scroll, brand is the serif at all widths, menu links serif and inline at >= 1200px, hamburger hidden at >= 1200px and working below, no console errors or missing assets (`fonts/article-fonts.css`, preloaded woff2 return 200). Fix any defect found before committing, in a separate commit per defect.

- [ ] **Step 7: Commit**

```bash
git add app/templates/error/500.html app/static/style.css tests/test_public_pages_consistency.py
git commit -m "feat(ui): editorial 500 page and remove superseded legacy CSS"
```

- [ ] **Step 8: Hand-off note**

Tell the user: new `_()` strings need `pybabel extract` / `update` / `compile` (not done, `.mo` files have unrelated uncommitted changes), and list any CSS selectors left in place because they are still referenced.

---

## Self-Review

- **Spec coverage:** page rules and eyebrow labels (Tasks 2-4); lists, messages 40px avatar, IMDb link, todo done style, `#ccc` removal (Task 3, 5); profile layout and actions (Task 4); pagination replaced with text links (Tasks 3, 4); 500 page (Task 5); popover inline styles (Task 4); fonts moved to base with preload and serif stacks (Task 1); desktop inline menu at 1200px with HTML untouched (Task 1); `_()` wrapping of hard-coded titles (Tasks 2, 3); old-rule cleanup gated on grep (Task 5); verification with tests and screenshots (Task 5). Out-of-scope items (admin, article, `.mo`, unread badge) are untouched.
- **Known deviations to watch:** `test_article_enhancements.py` must change because its premise (fonts CSS is article-only) is intentionally reversed; `test_ui_pages.py` exact-class assertions change from `content-section` to `content-section public-page` for profile and messages.
- **Names:** `pager(prev_url, next_url, newer_label, older_label, aria_label)`, `.search-pagination`, `.todo-title--done`, `.user-popup`, `.user-popup__avatar`, `get_page` are used identically across tasks.
