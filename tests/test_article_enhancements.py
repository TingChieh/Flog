from app import db
from app.models import Post


def test_article_enhancement_assets_are_scoped_to_post(client, users):
    article = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    home = client.get('/').get_data(as_text=True)
    for asset in ('vendor/photoswipe/photoswipe.css', 'article-enhancements.js'):
        assert asset in article
        assert asset not in home
    assert 'fonts/article-fonts.css' in article
    assert 'fonts/article-fonts.css' in home
    assert 'reading-progress' in article
    assert 'reading-progress' not in home


def test_image_captions_are_preserved_and_sanitized(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '<figure><img src="/test.png" alt="&lt;img src=x onerror=alert(1)&gt;" onerror="alert(2)"><figcaption>Caption &lt;script&gt;alert(3)&lt;/script&gt;</figcaption></figure>'
        post.body_format = 'html'
        db.session.commit()
    html = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert '<figure>' in html and '<figcaption>' in html
    assert 'alt="&lt;img src=x onerror=alert(1)&gt;"' in html
    assert '<script>alert(3)</script>' not in html
    assert 'onerror="alert(2)"' not in html
