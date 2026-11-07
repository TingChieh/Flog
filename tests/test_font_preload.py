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
