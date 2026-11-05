# Search Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound anonymous post searches and preserve literal search semantics.

**Architecture:** The route validates and normalizes the query before building
one paginated SQLAlchemy statement. The template receives only the current
page and navigation URLs. Query length is application configuration so the
limit is explicit and testable.

**Tech Stack:** Flask, Flask-SQLAlchemy, pytest.

## Global Constraints

- Search remains body-only.
- Search uses the existing `POSTS_PER_PAGE` setting.
- No new runtime dependency is added.

---

### Task 1: Define and test bounded literal search

**Files:**
- Modify: `config.py`
- Modify: `app/routes.py`
- Modify: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: `Config.POSTS_PER_PAGE` and Flask request query parameters.
- Produces: `GET /search?q=<query>&page=<number>` with at most one page of
  posts, literal matching, and a 400 response for overlong queries.

- [x] **Step 1: Write failing tests**

```python
def test_empty_search_does_not_return_all_posts(client, users):
    response = client.get('/search?q=')
    assert 'class="editorial-post"' not in response.get_data(as_text=True)


def test_search_treats_like_metacharacters_as_literals(client, application, users):
    # Create one body containing % and one body without it.
    response = client.get('/search?q=%')
    assert response.get_data(as_text=True).count('class="editorial-post"') == 1
```

- [x] **Step 2: Run the focused test module and confirm the empty-query and
  wildcard assertions fail against the current route**

Run: `.venv/bin/pytest tests/test_ui_pages.py -q`

Expected: failure because the current route returns all posts for an empty
query and treats `%` as a SQL wildcard.

- [x] **Step 3: Add the minimal configuration and route implementation**

```python
query = request.args.get('q', '').strip()
if len(query) > app.config['SEARCH_QUERY_MAX_LENGTH']:
    abort(400)
posts = []
if query:
    page = request.args.get('page', 1, type=int)
    statement = sa.select(Post).where(
        Post.body.contains(query, autoescape=True)
    ).order_by(Post.timestamp.desc())
    results = db.paginate(statement, page=page,
                          per_page=app.config['POSTS_PER_PAGE'],
                          error_out=False)
    posts = results.items
```

- [x] **Step 4: Re-run the focused test module and confirm it passes**

Run: `.venv/bin/pytest tests/test_ui_pages.py -q`

Expected: PASS.

### Task 2: Render and test query-preserving pagination

**Files:**
- Modify: `app/routes.py`
- Modify: `app/templates/post/search_results.html`
- Modify: `tests/test_ui_pages.py`

**Interfaces:**
- Consumes: pagination URLs from the search route.
- Produces: next/previous links that retain `q` and `page`.

- [x] **Step 1: Write a failing pagination test**

```python
def test_search_paginates_and_preserves_query(client, application, users):
    # Create POSTS_PER_PAGE + 1 matching posts.
    first_page = client.get('/search?q=match')
    assert 'q=match&amp;page=2' in first_page.get_data(as_text=True)
```

- [x] **Step 2: Run the focused test and confirm it fails because the search
  template has no navigation links**

Run: `.venv/bin/pytest tests/test_ui_pages.py::test_search_paginates_and_preserves_query -q`

Expected: failure because current search results are unpaginated.

- [x] **Step 3: Pass `next_url` and `prev_url` from the route, then render
  the repository's existing pagination markup in the search template**

```python
next_url = url_for('search', q=query, page=results.next_num) \\
    if results.has_next else None
prev_url = url_for('search', q=query, page=results.prev_num) \\
    if results.has_prev else None
```

- [x] **Step 4: Run all search-relevant tests**

Run: `.venv/bin/pytest tests/test_ui_pages.py tests/test_post_views.py -q`

Expected: PASS.
