from pathlib import Path

from lxml import html as lxml_html

from tests.conftest import login

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'
SERIF_STACK = "'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif"


def admin_page(client, path='/admin/'):
    login(client, 'admin')
    response = client.get(path)
    return response, lxml_html.fromstring(response.get_data(as_text=True))


def section(css, marker):
    start = css.index(marker)
    nxt = css.find('/* Admin:', start + len(marker))
    return css[start:] if nxt == -1 else css[start:nxt]


def test_admin_body_uses_the_public_editorial_shell(client, users):
    _, page = admin_page(client)
    assert page.xpath('//body')[0].get('class') == 'public-site admin-site'


def test_current_navigation_link_is_marked(client, users):
    _, page = admin_page(client, '/admin/pages')
    current = page.xpath('//nav[@aria-label="管理导航"]//a[@aria-current="page"]')
    assert [a.text_content().strip() for a in current] == ['页面管理', '页面管理']
    # the nav macro renders twice (sidebar and mobile drawer)


def test_all_pages_of_a_section_keep_the_link_marked(client, users):
    _, page = admin_page(client, '/admin/pages/new')
    current = page.xpath('//nav[@aria-label="管理导航"]//a[@aria-current="page"]')
    assert {a.text_content().strip() for a in current} == {'页面管理'}


def test_shell_css_section_defines_the_editorial_navigation():
    css = STYLESHEET.read_text()
    block = section(css, '/* Admin: editorial shell, navigation and page header. */')
    assert '.admin-topbar {' in block and 'backdrop-filter: none;' in block
    assert f'.admin-topbar__brand {{ font-family: {SERIF_STACK};' in block
    assert 'border-left: 2px solid transparent;' in block
    assert '.admin-nav__link[aria-current="page"]' in block
    assert '.admin-sidebar { padding: 0; background: transparent; border: 0; }' in block
    assert '@media (width <= 768px)' in block


from app import db
from app.models import Category, Page, Post, PostComment


def rule_bodies(css, selector):
    import re
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    out = []
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        selectors = [s.strip() for s in match.group(1).split(',')]
        if selector in selectors:
            out.append(match.group(2))
    return out


def test_delete_buttons_in_admin_lists_are_danger_links(client, application, users):
    with application.app_context():
        db.session.add_all([
            Page(title='P', slug='p', kind='content', body='x', is_published=True),
            PostComment(name='R', email='r@example.com', body='hi',
                        post=db.session.get(Post, users['post'])),
        ])
        db.session.commit()
    login(client, 'admin')
    for path in ('/admin/posts', '/admin/pages', '/admin/categories', '/admin/comments'):
        page = lxml_html.fromstring(client.get(path).get_data(as_text=True))
        buttons = [b for b in page.xpath('//article//button[@type="submit"]')
                   if b.text_content().strip() == '删除']
        assert buttons, path
        for button in buttons:
            assert 'button--danger' in button.get('class'), path


def test_non_destructive_row_buttons_are_not_danger(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/categories').get_data(as_text=True))
    saves = [b for b in page.xpath('//article//button') if b.text_content().strip() == '保存']
    assert saves and all('button--danger' not in b.get('class') for b in saves)


def test_buttons_lists_and_dashboard_css_is_quiet():
    css = STYLESHEET.read_text()
    block = section(css, '/* Admin: buttons, lists, filters, dashboard, settings. */')
    quiet = rule_bodies(block, '.admin-site .button--quiet')[0]
    assert 'background: transparent;' in quiet and 'text-decoration: underline;' in quiet
    assert 'color: var(--danger);' in rule_bodies(
        block, '.admin-site .button--quiet.button--danger')[0]
    active = rule_bodies(block, '.admin-filter--active')
    assert any('border-bottom-color: var(--text-primary);' in body for body in active)
    assert not any('background: var(--text-primary)' in body for body in active)
    metric = rule_bodies(block, '.admin-metric')[0]
    assert 'background: transparent;' in metric and 'border: 0;' in metric


def test_category_rows_lay_out_the_inline_edit_form_horizontally():
    css = STYLESHEET.read_text()
    block = section(css, '/* Admin: buttons, lists, filters, dashboard, settings. */')
    assert 'flex-direction: row;' in rule_bodies(block, '.admin-list__main.admin-inline-edit')[0]
    assert rule_bodies(block, '.admin-list__row:has(> .admin-inline-edit)')


def test_admin_form_submit_button_is_not_stretched():
    css = STYLESHEET.read_text()
    block = section(css, '/* Admin: buttons, lists, filters, dashboard, settings. */')
    assert 'justify-self: start;' in rule_bodies(block, '.admin-form > .button--cta')[0]
