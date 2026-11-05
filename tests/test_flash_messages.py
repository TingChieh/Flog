from pathlib import Path
import re

from lxml import html as lxml_html

from tests.conftest import login

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'


def rule_bodies(css, selector):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    return [m.group(2) for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css)
            if selector in [s.strip() for s in m.group(1).split(',')]]


def test_flash_message_uses_the_editorial_markup(client, users):
    login(client, 'admin')
    response = client.post('/admin/pages/new', data={
        'title': 'Notes', 'slug': 'notes', 'nav_order': '0', 'body': 'x',
    }, follow_redirects=True)
    page = lxml_html.fromstring(response.get_data(as_text=True))
    flashes = page.xpath('//main//div[contains(@class, "flash-message")]')
    assert [f.text_content().strip() for f in flashes] == ['页面已创建。']
    assert flashes[0].get('role') == 'status'
    assert not page.xpath('//main//*[contains(@class, "alert")]')


def test_flash_message_css_is_a_quiet_left_rule():
    css = STYLESHEET.read_text()
    body = rule_bodies(css, '.flash-message')[0]
    assert 'background: transparent;' in body
    assert 'border-left: 2px solid var(--text-secondary);' in body
    assert 'border-radius: 0;' in body
    assert 'border: 1px' not in body
    assert rule_bodies(css, '.public-site .flash-message')
    assert 'margin-inline: auto;' in rule_bodies(css, '.public-site .flash-message')[0]
    assert 'margin-inline: 0;' in rule_bodies(css, '.admin-site .flash-message')[0]
    assert not rule_bodies(css, '.alert')
