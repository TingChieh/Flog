import re
from pathlib import Path

STATIC = Path(__file__).parents[1] / 'app' / 'static'


def bundled_keys():
    text = (STATIC / 'emoji-keys.js').read_text()
    return re.search(r'"([^"]*)"', text).group(1).split()


def test_every_bundled_key_has_an_image():
    keys = bundled_keys()
    assert len(keys) > 500
    missing = [key for key in keys if not (STATIC / 'emoji' / 'noto' / f'{key}.png').is_file()]
    assert missing == []


def test_every_image_is_listed_in_the_keys():
    files = {p.stem for p in (STATIC / 'emoji' / 'noto').glob('*.png')}
    assert files == set(bundled_keys())


def test_the_license_ships_with_the_images():
    assert 'Apache License' in (STATIC / 'emoji' / 'noto' / 'LICENSE').read_text()
    assert 'Noto Emoji' in (STATIC / 'emoji' / 'noto' / 'NOTICE').read_text()


def test_public_pages_load_the_emoji_script(client, users):
    body = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert 'emoji-keys.js' in body and 'emoji.js' in body
    assert 'data-base="/static/emoji/noto/"' in body
    assert body.index('emoji-keys.js') < body.index('/emoji.js')


def test_editors_load_the_picker_before_the_markdown_editor(client, users):
    from tests.conftest import login
    login(client, 'admin')
    for path in ('/admin/pages/new', '/admin/posts/new'):
        body = client.get(path).get_data(as_text=True)
        assert 'emoji-data.js' in body and 'emoji-picker.js' in body
        assert body.index('emoji-picker.js') < body.index('markdown-editor.js')
