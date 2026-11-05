# Public Pages Consistency And Navigation Typography

## Goal

Bring the remaining public-facing pages up to the editorial look already used
by the home, archive, links, search, login, register and 404 pages (PR #9),
and give the navigation a serif brand and menu type that matches the site's
Chinese body font. Routes, forms, permissions and data models do not change.

## Background

The pages already redesigned share three traits:

- they override `{% block page_hero %}` to drop the legacy `hero--page` banner;
- their container carries `public-page` (a 640px reading column);
- their heading has a `public-label` eyebrow above the `h1`.

The remaining front-end templates have none of these. They render the legacy
banner and then repeat the title in `page-heading`, in the old 1080px column.
Their markup already uses the shared classes (`form-shell`, `page-heading`,
`data-list`, `empty-state`), so the work is template wiring plus a small amount
of CSS.

## Scope

In scope:

| Group | Templates |
|---|---|
| Forms | `edit_profile`, `send_message`, `user/reset_password`, `user/reset_password_request`, `post/edit_post`, `edit_link`, `post/edit_category`, `about/edit_about`, `movie/movie_edit`, `todo/todo_edit` |
| Lists | `messages`, `movie/movie`, `todo/todo`, `post/posts_by_category` |
| Profile | `user/user` |
| Error | `error/500` |
| Popover | `user/user_popup` |
| Navigation | the `site_navigation` block in `base.html` |

Out of scope: article detail and comments, the admin area, `bootstrap_wtf.html`
macro structure, dark-mode tokens, the unread-message badge, and the
uncommitted `.mo` translation files.

## Page Template Rules

- Add `{% block page_hero %}{% endblock %}`.
- Containers become `content-section public-page`, or `form-shell public-page`
  for forms (the pattern in `user/login.html`).
- Each `page-heading` gets a `public-label` line (Messages, Movies, Todo,
  Profile, Edit, ...) wrapped in `_()`, followed by the `h1`.
- Hard-coded English titles in `edit_post`, `edit_link` and `edit_category` are
  wrapped in `_()`.
- No change to variables, routes or form fields.

## Page-Specific Treatment

- **Lists** (`messages`, `movie`, `todo`, `posts_by_category`): borderless rows
  with 12px padding, as in `public-page .data-list__item`. The IMDb button
  becomes a quiet underlined secondary link, matching the friend-link actions.
  Completed todos use `--text-secondary` with a strikethrough. The hard-coded
  `#ccc` in `.movie-item` is removed.
- **Messages**: 40px avatars (matching friend-link avatars); sender and time on
  one line.
- **Profile**: heading is the username with a `Profile` eyebrow instead of
  "User: name". Avatar is about 96px, beside the bio; below 768px it stacks
  above. Actions become secondary text links. Posts reuse `editorial-post`.
- **Pagination** on `messages`, `todo` and `user`: replace the Bootstrap
  pagination with the two-text-link style of `.search-pagination`. The
  disabled state stays clearly distinct from an active link.
- **500 page**: same structure as 404 (`public-error`, eyebrow `500`).
- **User popover**: inline styles replaced by `.user-popup` and
  `.user-popup__avatar`. The QR container string in `post.html` is a Popover
  attribute and is left alone.
- Old rules superseded by the above (`.post-item`, `.post-header`, ...) are
  deleted only after confirming no template references them.

## Navigation

### Typography

`fonts/article-fonts.css` (Source Serif 4 and Noto Serif SC `@font-face`
rules) is currently linked only from `post/post.html`. It moves to
`base.html` so every page can use it.

- **Brand** "Aisaka's Blog": `'Source Serif 4', 'Noto Serif SC', 'Songti SC',
  Georgia, serif`, 20-22px, weight 600. The `-.04em` letter-spacing written for
  the sans stack is replaced with roughly 0.
- **Menu links**: the same serif stack, 15px, weight 500, for both English and
  Chinese labels.
- **Controls** (search trigger and its keyboard hint, theme selector, unread
  badge) stay on the system sans stack.
- Noto Serif SC is split into unicode-range subsets, so only the few files
  covering the menu's characters are fetched. `source-serif-4-normal-latin.woff2`
  (about 117 KB) is preloaded in `base.html` to avoid a brand-name font flash.
  `font-display: swap` and the Georgia fallback remain.

### Desktop layout

- At viewport width >= 1200px the menu links sit inline in the bar: brand on the
  left, links in the middle, search and theme controls on the right. The
  hamburger is hidden.
- Below 1200px the existing hamburger and dropdown panel are unchanged.
- The HTML is unchanged: the `hidden` attribute, `data-nav-toggle` and
  `aria-controls` stay, so existing tests in `test_editorial_redesign.py` and
  `test_ui_shell.py` still hold. The desktop layout overrides `[hidden]` in CSS;
  no new JavaScript.
- Links may wrap onto a second line instead of overflowing the rounded shell.

## CSS Approach

All additions go in the `public-site` block at the end of `style.css`, using
existing variables; no new tokens. Dark mode relies on those variables only.

## Responsive And Accessibility

- Check at 390, 768, 1200 and 1440 widths; existing `width <= 768px` rules stay.
- Interactive elements keep a 44px minimum target on mobile.
- Focus styles come from the global rules; none are overridden.
- Long titles and usernames use `overflow-wrap: anywhere` so nothing breaks out
  of the 640px column.

## Verification

- Extend `tests/test_editorial_redesign.py`: the listed pages render
  `public-page`, do not render `hero--page`, and `500` carries its eyebrow;
  `base.html` links `article-fonts.css`; the brand and menu font stacks are in
  the stylesheet.
- Run the full suite with `DATABASE_URL=sqlite://` and the `node` front-end
  tests.
- Screenshots with playwright in light and dark, at 390 and 1440, plus the
  1200px breakpoint, an open mobile menu, long titles, empty lists and a form
  validation error.

## Follow-up

New `_()` strings need `pybabel extract/update/compile` afterwards; that is
left to the user because the `.mo` files currently have uncommitted changes.
