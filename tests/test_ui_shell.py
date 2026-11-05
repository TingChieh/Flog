from datetime import datetime, timezone
from pathlib import Path
import re

from app import db
from app.models import Page, Post
from tests.conftest import login


def _css_rule_blocks(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    stack = []
    block_start = 0
    quote = None
    escaped = False

    for index, character in enumerate(css):
        if quote:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == quote:
                quote = None
            continue

        if character in ('"', "'"):
            quote = character
        elif character == '{':
            selector = css[block_start:index].strip()
            stack.append((selector, index + 1, len(stack)))
            block_start = index + 1
        elif character == '}':
            selector, body_start, depth = stack.pop()
            yield selector, css[body_start:index], depth
            block_start = index + 1
        elif character == ';' and not stack:
            block_start = index + 1


def _top_level_rule_bodies(css, selector):
    return [
        body for selectors, body, depth in _css_rule_blocks(css)
        if depth == 0 and selector in {
            item.strip() for item in selectors.split(',')
        }
    ]


def test_public_shell_has_accessible_navigation_footer_and_back_to_top(
        client, application):
    with application.app_context():
        db.session.add(Page(
            title='About', slug='about', kind='content',
            body='<p>About</p>', is_published=True))
        db.session.commit()
    response = client.get('/about')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="site-brand"' in html
    assert 'data-nav-toggle' in html
    assert 'data-site-nav' in html
    assert html.count('data-theme-toggle') == 1
    assert 'static/theme.js' in html
    for mode in ('light', 'dark'):
        assert f'theme-toggle__icon--{mode}' in html
    assert 'theme-toggle__icon--auto' not in html
    assert 'data-theme-selector' not in html
    assert 'data-theme-mode-option' not in html
    assert 'aria-label="当前为白天模式；切换到夜间模式"' in html
    assert 'title="当前为白天模式；切换到夜间模式"' in html
    assert 'data-back-to-top' in html
    assert 'aria-label="Back to top"' in html
    assert str(datetime.now(timezone.utc).year) in html
    assert 'static/site.js' in html
    assert '<font' not in html


def test_authenticated_admin_shell_has_the_theme_toggle(client, users):
    login(client, 'admin')
    response = client.get('/admin')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count('data-theme-toggle') == 1
    assert 'data-theme-selector' not in html
    assert 'data-theme-mode-option' not in html
    assert 'data-theme-mode="light"' in html
    assert 'theme-toggle__icon--auto' not in html
    assert 'aria-label="当前为白天模式；切换到夜间模式"' in html


def test_empty_page_navigation_does_not_restore_hardcoded_modules(client):
    html = client.get('/').get_data(as_text=True)

    for href in ('/movie', '/comment', '/todo', '/links', '/about'):
        assert f'href="{href}"' not in html
    assert 'href="/index"' in html
    assert 'action="/search"' in html


def test_page_navigation_keeps_database_order_without_following(
        client, application):
    with application.app_context():
        db.session.add_all([
            Page(title='Later', slug='later-nav', kind='content',
                 body='Later', is_published=True, show_in_nav=True,
                 nav_order=30),
            Page(title='First', slug='first-nav', kind='content',
                 body='First', is_published=True, show_in_nav=True,
                 nav_order=10),
        ])
        db.session.commit()

    html = client.get('/').get_data(as_text=True)
    assert html.index('href="/first-nav"') < html.index('href="/later-nav"')
    assert 'Following' not in html
    assert 'href="/following"' not in html


def test_homepage_omits_image_hero(client):
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="hero hero--home"' not in html
    assert 'images/hero.jpg' not in html
    assert 'images/aisaka.png' not in html
    assert 'id="latest-posts"' in html


def test_homepage_uses_compact_editorial_post_rows(client, users):
    response = client.get('/')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="editorial-layout"' in html
    assert 'class="editorial-list"' in html
    assert 'class="editorial-post"' in html
    assert 'class="editorial-post__title"' in html
    assert 'class="category-rail"' not in html
    assert 'class="editorial-post__category"' in html
    assert 'Continue reading' not in html
    assert '>Test<' in html


def test_public_article_surfaces_show_persisted_view_count(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.view_count = 7
        db.session.commit()

    homepage = client.get('/').get_data(as_text=True)
    detail = client.get(f'/post/{users["post"]}').get_data(as_text=True)

    assert 'class="post-view-count"' not in homepage
    assert 'class="post-view-count">8 次阅读</span>' in detail


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


def test_article_copy_link_handles_clipboard_success_and_failure(client, users):
    response = client.get(f'/post/{users["post"]}')
    html = response.get_data(as_text=True)

    assert 'navigator.clipboard.writeText(text).then(function()' in html
    assert "alert('Link copied to clipboard!')" in html
    assert "console.error('Could not copy text: ', err)" in html


def test_homepage_editorial_styles_define_responsive_rail_and_utilities():
    css = Path('app/static/style.css').read_text()

    layout = _top_level_rule_bodies(css, '.editorial-layout')
    assert len(layout) == 1
    assert 'display: grid;' in layout[0]
    assert 'grid-template-columns: minmax(0, 1fr) minmax(180px, 230px);' in layout[0]

    for selector in ('.category-rail', '.post-utilities'):
        assert len(_top_level_rule_bodies(css, selector)) == 1

    utilities = _top_level_rule_bodies(css, '.post-utilities')[0]
    assert 'flex-wrap: wrap;' in utilities

    mobile = css.rsplit('@media (max-width: 768px)', 1)[1]
    assert '.editorial-layout {' in mobile
    assert 'grid-template-columns: minmax(0, 1fr);' in mobile
    assert '.category-rail {' in mobile
    assert 'border-top: 1px solid var(--border);' in mobile
    assert '.editorial-post__title {' in mobile
    assert 'font-size: 21px;' in mobile

    desktop = css.rsplit('@media (min-width: 769px)', 1)[1]
    assert '.editorial-post__title {' in desktop
    assert 'font-size: 26px;' in desktop


def test_navigation_open_state_has_a_stylesheet_selector():
    stylesheet = Path(__file__).parents[1] / 'app' / 'static' / 'style.css'

    assert '.site-nav__menu--open' in stylesheet.read_text()


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


def test_stylesheet_has_no_legacy_green_fills():
    css = Path('app/static/style.css').read_text().lower()

    assert 'yellowgreen' not in css
    assert 'rgba(17, 201, 164' not in css


def test_stylesheet_sets_an_accessible_dark_theme_danger_color():
    css = Path('app/static/style.css').read_text()

    dark_theme = css.split('html[data-theme="dark"]', 1)[1].split('}', 1)[0]
    assert '--danger: #ff6961' in dark_theme


def test_theme_toggle_is_a_single_quiet_icon_button():
    css = Path('app/static/style.css').read_text()

    assert 'theme-selector' not in css
    toggle = _top_level_rule_bodies(css, '.theme-toggle')
    assert len(toggle) == 1
    assert 'display: inline-flex;' in toggle[0]
    assert 'background: transparent;' in toggle[0]
    assert 'border: 0;' in toggle[0]
    assert 'color: var(--text-secondary);' in toggle[0]

    icon = _top_level_rule_bodies(css, '.theme-toggle__icon')
    assert len(icon) == 1
    assert 'display: none;' in icon[0]
    assert 'stroke: currentColor;' in icon[0]
    for mode in ('light', 'dark'):
        assert (f'.theme-toggle[data-theme-mode="{mode}"] '
                f'.theme-toggle__icon--{mode}') in css
    assert 'theme-toggle__icon--auto' not in css
    assert _top_level_rule_bodies(css, '.theme-toggle:hover')
    focus = _top_level_rule_bodies(css, '.theme-toggle:focus-visible')
    assert 'outline: 2px solid var(--link-color);' in focus[0]

    label = _top_level_rule_bodies(css, '.theme-toggle__label')
    assert 'display: none;' in label[0]
    assert '.public-site .site-nav__menu .theme-toggle__label' in css

    mobile = css.rsplit('@media (max-width: 768px)', 1)[1]
    assert '.theme-selector' not in mobile
    assert '.site-nav__menu > .icon-button:not(.theme-toggle),' in mobile
    assert '.site-nav__menu > .icon-button {' not in mobile
    assert '.admin-topbar__actions .icon-button:not(.theme-toggle) {' in mobile
    assert '.admin-topbar__actions .icon-button {' not in mobile


def test_admin_form_grid_allows_markdown_editor_to_shrink_on_mobile():
    css = Path('app/static/style.css').read_text()

    blocks = _top_level_rule_bodies(css, '.admin-form')
    assert len(blocks) == 1
    assert 'grid-template-columns: minmax(0, 1fr);' in blocks[0]


def test_mobile_stylesheet_uses_44_pixel_control_targets():
    css = Path('app/static/style.css').read_text()
    mobile = css.rsplit('@media (max-width: 768px)', 1)[1]

    assert '.form-control,' in mobile
    assert '.form-select,' in mobile
    assert '.form-check-label {' in mobile
    assert 'min-height: 44px' in mobile
    assert '.back-to-top {' in mobile
    back_to_top = mobile.split('.back-to-top {', 1)[1]
    assert 'width: 44px;' in back_to_top
    assert 'height: 44px;' in back_to_top


def test_medium_navigation_wraps_before_mobile_breakpoint():
    css = Path('app/static/style.css').read_text()

    assert '@media (min-width: 769px) and (max-width: 1080px)' in css
    medium = css.split(
        '@media (min-width: 769px) and (max-width: 1080px)', 1
    )[1]
    assert '.site-nav__inner {' in medium
    assert 'flex-wrap: wrap;' in medium
    assert '.site-nav__menu {' in medium
    assert 'flex-basis: 100%;' in medium
    assert '.site-nav__links {' in medium


def test_neutral_components_do_not_use_link_color_in_resting_rules():
    css = Path('app/static/style.css').read_text()

    for selector in ('.tile', '.tile:hover', '.btn-outline-primary',
                     '.btn-outline-secondary'):
        blocks = _top_level_rule_bodies(css, selector)
        assert len(blocks) == 1
        assert 'var(--link-color)' not in blocks[0]


def test_shared_navigation_has_one_authoritative_top_level_rule():
    css = Path('app/static/style.css').read_text()

    for selector in (
        '.site-nav', '.site-nav__inner', '.site-nav__menu', '.nav-toggle',
    ):
        assert len(_top_level_rule_bodies(css, selector)) == 1
