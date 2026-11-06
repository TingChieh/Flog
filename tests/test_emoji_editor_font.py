import re
from pathlib import Path

STATIC = Path(__file__).parents[1] / 'app' / 'static'


def test_editor_css_points_at_a_font_that_exists():
    css = (STATIC / 'emoji-editor.css').read_text()
    url = re.search(r"url\('?([^')]+)'?\)", css).group(1)
    assert (STATIC / url.removeprefix('/static/')).is_file()


def test_the_font_only_covers_emoji_ranges():
    css = (STATIC / 'emoji-editor.css').read_text()
    assert 'unicode-range' in css


def test_the_range_covers_the_variation_selector():
    # Without U+FE0F, Safari hands "\u2764\uFE0F" to the system font as a whole.
    css = (STATIC / 'emoji-editor.css').read_text()
    assert 'U+FE0F' in css


def test_the_font_ships_with_its_open_font_license():
    license_text = (STATIC / 'fonts' / 'emoji-editor-LICENSE.txt').read_text()
    assert 'SIL Open Font License' in license_text


def test_only_the_editor_pages_load_it(client, users):
    from tests.conftest import login
    login(client, 'admin')
    assert 'emoji-editor.css' in client.get('/admin/pages/new').get_data(as_text=True)
    assert 'emoji-editor.css' in client.get('/admin/posts/new').get_data(as_text=True)
    assert 'emoji-editor.css' not in client.get(f'/post/{users["post"]}').get_data(as_text=True)
