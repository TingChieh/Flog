"""Public search cases that also exercise MySQL's LIKE implementation."""
import pytest
from app import db
from app.models import Post, User


@pytest.fixture
def like_posts(application):
    with application.app_context():
        author = User(username='like-author', email='like@example.com')
        db.session.add(author)
        db.session.flush()
        db.session.add_all([
            Post(title='中文 English', body='混合 English 中文', author=author, is_published=True),
            Post(title='Hidden 中文', body='混合 English 中文', author=author, is_published=False),
            Post(title='Literal', body=r'''token 100%_done path\name O'Reilly "quote"''', author=author, is_published=True),
            Post(title='Decoy', body='token 100XXdone pathname OXReilly quote', author=author, is_published=True),
            Post(title='<img src=x onerror=alert(1)>', body='needle &lt;script&gt;alert(1)&lt;/script&gt;', author=author, is_published=True),
        ])
        db.session.commit()


@pytest.mark.parametrize('query,expected', [
    ('中文', '中文 English'),
    ('English', '中文 English'),
    ('混合 English 中文', '中文 English'),
    ('100%_done', 'Literal'),
    ('%', 'Literal'),
    ('_', 'Literal'),
    (r'path\name', 'Literal'),
    ("O'Reilly", 'Literal'),
    ('"quote"', 'Literal'),
    ("' OR 1=1 --", None),
])
def test_like_search_treats_queries_as_literal_and_hides_drafts(client, like_posts, query, expected):
    results = client.get('/api/search', query_string={'q': query}).json['results']
    assert [row['title'] for row in results] == ([expected] if expected else [])


def test_like_search_highlights_and_escapes_html(client, like_posts):
    response = client.get('/search', query_string={'q': 'needle'})
    html = response.get_data(as_text=True)
    assert '<mark>needle</mark>' in html
    assert '<img src=x onerror=alert(1)>' not in html
    assert '<script>alert(1)</script>' not in html
    result = client.get('/api/search', query_string={'q': 'needle'}).json['results'][0]
    assert result['snippet'] == '<mark>needle</mark> &lt;script&gt;alert(1)&lt;/script&gt;'
