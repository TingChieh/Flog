# Admin Editorial UI And About Entry

## Goal

Make the admin look like the public site (warm editorial shell, serif brand and
navigation, quiet text actions) and add a dedicated "关于" entry to the admin
navigation. The Markdown editor area is out of scope here; it is replaced in a
separate project (Vditor).

## Shell And Tokens

- The admin body becomes `public-site admin-site`, so the editorial tokens
  (`--page-bg`, `--surface`, `--text-*`, `--border`, dark variants), the
  rounded `site-shell`, body padding and footer styling already defined for
  `public-site` apply unchanged. Admin-only rules live in one new section at the
  end of `style.css`.
- `admin-site` overrides: `site-main` padding (no 70px top gap), workspace width
  up to the shell's 1450px.

## Components

- **Top bar**: static, transparent, no bottom border or blur. Brand "Aisaka 管理"
  uses the serif stack (weight 600) like the public brand. "返回网站" is a quiet
  secondary text link; the theme toggle is unchanged.
- **Sidebar**: no grey panel or right border. Group labels reuse the small
  uppercase secondary style; links are serif text in the secondary colour with
  a 2px left bar. The current page has `aria-current="page"`, ink colour and an
  ink bar. The mobile drawer keeps working.
- **Page header**: small uppercase eyebrow, 36px bold title, no divider.
- **Buttons**: primary (`button--cta`) ink fill with a 6px radius; `button--quiet`
  is a secondary text link; destructive actions get `button--danger` (red text).
  Delete buttons in posts, pages, categories and comments use it.
- **Lists**: no top border, thin row dividers, bold sans title, secondary meta,
  text-link actions. **Filters**: text tabs, active tab ink with a 2px underline.
- **Dashboard metrics**: no box; large serif numeral with a secondary caption.
- **Forms**: unchanged controls (already shared with the public forms).
- **Settings and environment pages**: fieldset groups lose their card border and
  radius and get a top divider; density is unchanged.

## About Entry

- New admin route `GET /admin/about` (admin only). If a page with slug `about`
  exists (or a redirect for it), redirect to its edit page. Otherwise redirect to
  the new-page form with the title "关于", slug `about` and "显示在导航中"
  pre-filled through query parameters. Nothing is written on GET; the owner
  saves once.
- The admin navigation shows "关于" in the "网站管理" group after "页面管理".
- `new_page` accepts `title`, `slug` and `show_in_nav` query parameters on GET
  to pre-fill the form; they are ignored on POST.

## Testing

- pytest: `/admin/about` redirects to the edit page when the page exists, to the
  pre-filled new page when it does not, is 403 for a member and a login redirect
  for anonymous visitors; the navigation lists it; `new_page` pre-fills and does
  not create anything on GET; `aria-current` marks the current link; delete
  buttons carry `button--danger`; the admin body class includes `public-site`.
- Existing tests must keep passing (drawer, theme controls, forms).
- playwright screenshots, light and dark, at 1440 and 390: overview, posts,
  pages, categories, comments, users, site settings, environment settings.

## Delivery

Branch `feat/admin-editorial-ui`: (1) About entry; (2) shell, top bar, sidebar;
(3) header, buttons, lists, filters, dashboard, settings; (4) verification and
fixes.
