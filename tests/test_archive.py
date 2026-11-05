from datetime import datetime

from lxml import html

from app import db
from app.models import Post, User


def test_archive_groups_published_posts_in_reverse_chronological_order(client, application):
    with application.app_context():
        author = User(username='archive-author', email='archive@example.com')
        db.session.add_all([
            Post(title=title, body='text', author=author, is_published=published,
                 timestamp=datetime.fromisoformat(date))
            for title, date, published in [
                ('Older', '2023-12-01', True), ('January', '2024-01-03', True),
                ('Newest', '2024-03-15', True), ('Earlier March', '2024-03-01', True),
                ('Hidden draft', '2025-01-01', False),
            ]
        ])
        db.session.commit()
    doc = html.fromstring(client.get('/archive').data)
    assert doc.xpath('//h2[@class="archive-year"]/text()') == ['2024', '2023']
    assert doc.xpath('//h3[@class="archive-month"]/text()') == ['三月', '一月', '十二月']
    assert doc.xpath('//a[@class="archive-entry__title"]/text()') == ['Newest', 'Earlier March', 'January', 'Older']
    assert 'Hidden draft' not in doc.text_content()
    # stored as UTC, shown (and labelled) in China time
    assert doc.xpath('//time[@datetime="2024-03-15T08:00:00+08:00"]')


def test_archive_localization_menu_and_sitemap(client):
    doc = html.fromstring(client.get('/archive').data)
    assert doc.xpath('//h1/text()') == ['归档']
    assert doc.xpath('//nav//a[@href="/archive" and text()="归档"]')
    assert b'http://localhost/archive' in client.get('/sitemap.xml').data
