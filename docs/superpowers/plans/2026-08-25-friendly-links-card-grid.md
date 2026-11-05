# Friendly Links Card Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the public Friendly Links page as an aligned responsive card grid with three desktop columns and one mobile column.

**Architecture:** Keep link data and routing unchanged, replace only the public template's shared row classes with dedicated friend-link card markup, and add scoped CSS using the existing design tokens. Flask rendering tests cover semantics and safe external links; stylesheet tests lock the three-, two-, and one-column states plus vertical card alignment.

**Tech Stack:** Flask, Jinja2, CSS Grid, Flexbox, pytest, Codex in-app Browser

## Global Constraints

- Affect only the public Friendly Links page; do not change link records, avatars, URLs, administration screens, permissions, or editing flows.
- Use three equal-width columns on wide desktop, two at intermediate widths, and one on mobile.
- Use the existing 1080-pixel content width and current responsive structure.
- Preserve the existing page heading, empty state, light theme, and dark theme.
- Keep mobile actions at least 44 pixels high through the existing mobile control rule.
- Use existing design tokens and add no dependencies.
- Keep final incomplete rows left-aligned without stretching cards across missing columns.

---

## File Map

- `app/templates/links.html`: owns semantic rendering of the public link grid and each card's header, description, and action.
- `app/static/style.css`: owns link-grid columns, card appearance, text wrapping, and bottom action alignment.
- `tests/test_ui_pages.py`: verifies rendered card markup, accessibility, and safe external-link attributes.
- `tests/test_ui_shell.py`: verifies the stylesheet contract for layout, alignment, and responsive column counts.

### Task 1: Dedicated Friend-Link Card Markup

**Files:**
- Modify: `tests/test_ui_pages.py`
- Modify: `app/templates/links.html:10-23`

**Interfaces:**
- Consumes: the existing `links` iterable of `Link` model instances with `name`, `text`, `url`, and `avatar(size)`.
- Produces: `.friend-links-grid`, `.friend-link-card`, `.friend-link-card__header`, `.friend-link-card__avatar`, `.friend-link-card__title`, `.friend-link-card__description`, and `.friend-link-card__actions` hooks for Task 2.

- [ ] **Step 1: Write the failing rendering test**

Add `Link` to the model import in `tests/test_ui_pages.py`:

```python
from app.models import Category, Link, Page, Post, Todo
```

Add this test after `test_public_pages_render_in_the_shared_design`:

```python
def test_friend_links_use_dedicated_card_markup(client, application):
    with application.app_context():
        add_published_module_for_path('/links')
        db.session.add_all([
            Link(name='Short', email='short@example.com', text='Brief',
                 url='https://short.example.com'),
            Link(name='Long link name', email='long@example.com',
                 text='A longer description that needs room to wrap.',
                 url='https://long.example.com'),
        ])
        db.session.commit()

    response = client.get('/links')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="friend-links-grid"' in html
    assert html.count('class="friend-link-card"') == 2
    assert 'class="friend-link-card__header"' in html
    assert 'class="friend-link-card__description"' in html
    assert 'class="friend-link-card__actions"' in html
    assert 'alt=""' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert 'data-list__item functional-row' not in html
```

- [ ] **Step 2: Run the rendering test and confirm the expected failure**

Run:

```bash
pytest tests/test_ui_pages.py::test_friend_links_use_dedicated_card_markup -v
```

Expected: FAIL because `class="friend-links-grid"` is absent from the current row-based template.

- [ ] **Step 3: Replace the public link-list markup**

Replace the existing `<ul class="data-list">...</ul>` block in `app/templates/links.html` with:

```html
  <ul class="friend-links-grid">
    {% for link in links %}
    <li class="friend-link-card">
      <div class="friend-link-card__header">
        <img class="friend-link-card__avatar" src="{{ link.avatar(40) }}" alt="" width="40" height="40">
        <h2 class="friend-link-card__title">{{ link.name }}</h2>
      </div>
      <p class="friend-link-card__description">{{ link.text }}</p>
      <div class="friend-link-card__actions">
        <a href="{{ link.url }}" class="button btn-sm" target="_blank" rel="noopener noreferrer">Visit Website</a>
      </div>
    </li>
    {% endfor %}
  </ul>
```

Leave the `{% if not links %}` empty-state block unchanged.

- [ ] **Step 4: Run the rendering and public-management tests**

Run:

```bash
pytest tests/test_ui_pages.py::test_friend_links_use_dedicated_card_markup tests/test_admin_modules.py::test_public_module_pages_have_no_management_actions -v
```

Expected: PASS for the new rendering test and all parameterized public-module cases.

- [ ] **Step 5: Commit the semantic markup**

```bash
git add app/templates/links.html tests/test_ui_pages.py
git commit -m "feat: restore friend link card markup"
```

### Task 2: Responsive Grid And Internal Alignment

**Files:**
- Modify: `tests/test_ui_shell.py`
- Modify: `app/static/style.css:1551-1610`
- Modify: `app/static/style.css:2474-2739`
- Modify: `app/static/style.css:2741-2775`

**Interfaces:**
- Consumes: the friend-link class hooks produced by Task 1 and existing CSS tokens `--surface`, `--border`, `--radius`, and `--text-secondary`.
- Produces: a three-column base grid, two-column intermediate grid, one-column mobile grid, equal-height cards per row, wrapped text, and bottom-aligned action areas.

- [ ] **Step 1: Write the failing stylesheet contract test**

Add this test near the other stylesheet assertions in `tests/test_ui_shell.py`:

```python
def test_friend_link_cards_define_responsive_aligned_grid():
    css = Path('app/static/style.css').read_text()

    grid = _top_level_rule_bodies(css, '.friend-links-grid')
    card = _top_level_rule_bodies(css, '.friend-link-card')
    actions = _top_level_rule_bodies(css, '.friend-link-card__actions')
    assert len(grid) == len(card) == len(actions) == 1
    assert 'display: grid;' in grid[0]
    assert 'grid-template-columns: repeat(3, minmax(0, 1fr));' in grid[0]
    assert 'display: flex;' in card[0]
    assert 'flex-direction: column;' in card[0]
    assert 'min-width: 0;' in card[0]
    assert 'margin-top: auto;' in actions[0]

    mobile = css.rsplit('@media (max-width: 768px)', 1)[1].split(
        '@media (min-width: 769px) and (max-width: 1080px)', 1)[0]
    medium = css.split(
        '@media (min-width: 769px) and (max-width: 1080px)', 1)[1].split(
            '@media (min-width: 769px)', 1)[0]
    assert '.friend-links-grid {' in mobile
    assert 'grid-template-columns: minmax(0, 1fr);' in mobile
    assert '.friend-links-grid {' in medium
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in medium
```

- [ ] **Step 2: Run the stylesheet test and confirm the expected failure**

Run:

```bash
pytest tests/test_ui_shell.py::test_friend_link_cards_define_responsive_aligned_grid -v
```

Expected: FAIL because no `.friend-links-grid` top-level rule exists.

- [ ] **Step 3: Add the base card-grid styles**

Add these dedicated rules after the existing `.functional-row__actions` rules in `app/static/style.css`:

```css
.friend-links-grid {
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: stretch;
    gap: 24px;
    list-style: none;
}

.friend-link-card {
    min-width: 0;
    padding: 22px;
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}

.friend-link-card__header {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 12px;
}

.friend-link-card__avatar {
    flex: 0 0 auto;
    border-radius: 50%;
}

.friend-link-card__title {
    min-width: 0;
    margin: 0;
    font-size: 18px;
    line-height: 1.3;
    overflow-wrap: anywhere;
}

.friend-link-card__description {
    margin: 18px 0 24px;
    color: var(--text-secondary);
    overflow-wrap: anywhere;
}

.friend-link-card__actions {
    margin-top: auto;
    display: flex;
    align-items: center;
}
```

- [ ] **Step 4: Add the mobile and intermediate column rules**

Inside the final `@media (max-width: 768px)` block, add:

```css
    .friend-links-grid {
        grid-template-columns: minmax(0, 1fr);
        gap: 16px;
    }

    .friend-link-card {
        padding: 18px;
    }
```

Inside `@media (min-width: 769px) and (max-width: 1080px)`, add:

```css
    .friend-links-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
```

- [ ] **Step 5: Run the stylesheet and shell tests**

Run:

```bash
pytest tests/test_ui_shell.py::test_friend_link_cards_define_responsive_aligned_grid tests/test_ui_shell.py -v
```

Expected: PASS for the new contract and the complete shell test module.

- [ ] **Step 6: Commit the responsive alignment styles**

```bash
git add app/static/style.css tests/test_ui_shell.py
git commit -m "style: align responsive friend link cards"
```

### Task 3: Regression And Responsive Browser Verification

**Files:**
- Verify: `app/templates/links.html`
- Verify: `app/static/style.css`
- Verify: `tests/test_ui_pages.py`
- Verify: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: the complete card grid from Tasks 1 and 2.
- Produces: verification evidence that the change is regression-free and visually correct at desktop and mobile widths.

- [ ] **Step 1: Run focused UI coverage**

```bash
pytest tests/test_ui_pages.py tests/test_ui_shell.py tests/test_admin_modules.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run the complete automated test suite**

```bash
pytest -v
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 3: Check patch integrity**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional implementation changes are present before their commits, and the temporary `.superpowers/brainstorm/` preview directory remains uncommitted.

- [ ] **Step 4: Start the application for visual verification**

```bash
flask run --port 5001
```

Expected: the Flask development server remains available at `http://127.0.0.1:5001` for user and browser inspection. If port 5001 is occupied, use the next free port and report it.

- [ ] **Step 5: Verify the desktop layout at 1280 by 800**

Open the published Friendly Links route in the in-app Browser and verify:

```text
- computed grid-template-columns contains three tracks
- cards in the same row have equal heights
- Visit Website buttons in the same row have equal bottom coordinates
- avatar and title are vertically centered in every header
- long descriptions wrap without horizontal overflow
- the final incomplete row begins at the left grid edge
```

Expected: all checks pass with no overlap, clipping, console error, or horizontal page overflow.

- [ ] **Step 6: Verify the mobile layout at 390 by 844**

Set the Browser viewport to 390 by 844, reload the page, and verify:

```text
- computed grid-template-columns contains one track
- every card fills the available content width
- Visit Website controls are at least 44 pixels high
- names and descriptions wrap inside the card
- no element overlaps or creates horizontal overflow
```

Expected: all checks pass. Reset the temporary viewport override afterward and leave the development server URL available to the user.

- [ ] **Step 7: Commit only if visual verification required a correction**

If Steps 5 or 6 required a code correction, rerun Steps 1-3 and commit the focused fix:

```bash
git add app/templates/links.html app/static/style.css tests/test_ui_pages.py tests/test_ui_shell.py
git commit -m "fix: polish friend link card alignment"
```

If no correction was required, do not create an empty commit.
