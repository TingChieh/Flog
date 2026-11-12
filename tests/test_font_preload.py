import re

from app import db, font_preload
from app.models import Post


def test_only_the_pieces_a_page_needs_are_named():
    files = font_preload.needed_files('<p>你好，世界</p><script>var 龘 = 1</script>')

    assert files
    assert len(files) <= font_preload.MAX_PRELOADED
    assert font_preload.needed_files('<p>plain ASCII and café</p>') == []


def test_a_chinese_page_preloads_its_font_pieces(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '你好，世界。今天天气很好。'
        post.body_format = 'markdown'
        db.session.commit()

    body = client.get(f"/post/{users['post']}").get_data(as_text=True)
    head, rest = body.split('</head>', 1)
    links = re.findall(r'<link rel="preload" as="font"[^>]*href="([^"]*noto-serif-sc-\d+\.woff2)"', head)

    assert links
    assert [link.rsplit('/', 1)[1] for link in links] == font_preload.needed_files(rest)


def test_a_page_carries_its_own_font_faces_and_loads_the_full_sheet_later(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '你好，世界。'
        post.body_format = 'markdown'
        db.session.commit()

    head = client.get(f"/post/{users['post']}").get_data(as_text=True).split('</head>', 1)[0]
    style = re.search(r'<style>(@font-face.*?)</style>', head).group(1)
    assert "font-family: 'Source Serif 4'" in style
    # Only the characters on the page, mapped to the piece that holds them.
    assert 'U+4f60' in style and 'U+4e16' in style
    assert style.count("font-family:'Noto Serif SC'") == len(re.findall(r'noto-serif-sc-\d+\.woff2', style))
    sheet = re.search(r'<link rel="stylesheet" href="([^"]*article-fonts\.css[^"]*)"([^>]*)>', head)
    assert 'media="print"' in sheet.group(2) and "onload=\"this.media='all'\"" in sheet.group(2)
    assert f'<noscript><link rel="stylesheet" href="{sheet.group(1)}"></noscript>' in head


def test_pages_this_hook_skips_keep_the_blocking_font_sheet(client):
    head = client.get('/no-such-page').get_data(as_text=True).split('</head>', 1)[0]
    assert re.search(r'<link rel="stylesheet" href="[^"]*article-fonts\.css[^"]*">', head)
    assert '<style>@font-face' not in head


def test_unicode_ranges_merge_neighbouring_characters():
    assert font_preload._unicode_range([0x4e00, 0x4e01, 0x4e02, 0x4e10]) == 'U+4e00-4e02,U+4e10'
