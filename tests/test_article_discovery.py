from datetime import datetime, timedelta, timezone

import pytest
from lxml import html

from app import db
from app.models import Category, Post, PostDraft, User


@pytest.fixture()
def add_articles(application):
    author = User(username='writer', email='writer@example.com')
    category = Category(name='Reading')
    other_category = Category(name='Other')
    db.session.add_all([author, category, other_category])
    now = datetime.now(timezone.utc).replace(microsecond=0)
    categories = {'reading': category, 'other': other_category, None: None}

    def add(*rows):
        posts = [Post(title=title, body='<p>Public text</p>', author=author,
                      category=categories[group], timestamp=now + timedelta(days=days),
                      is_published=published)
                 for title, group, days, published in rows]
        db.session.add_all(posts)
        db.session.commit()
        return posts

    return add


def article_page(client, post):
    response = client.get(f'/post/{post.id}')
    assert response.status_code == 200
    return html.fromstring(response.get_data(as_text=True))


def adjacent_links(page):
    return {link.get('rel'): link.get('href') for link in page.xpath(
        '//nav[@class="article-neighbors"]//a')}


def related_links(page):
    return page.xpath('//section[@class="article-related"]//a/@href')


def test_article_navigation_uses_publication_time_then_id(client, add_articles):
    first, newest, tied_older, current, tied_newer, draft, future = add_articles(
        ('First public', 'other', -10, True),
        ('Newest public', 'other', -2, True),
        ('Earlier tie', 'reading', -5, True),
        ('Current', 'reading', -5, True),
        ('Later tie', 'other', -5, True),
        ('Hidden draft', 'reading', -4, False),
        ('Future article', 'reading', 1, True),
    )

    assert adjacent_links(article_page(client, current)) == {
        'prev': f'/post/{tied_older.id}', 'next': f'/post/{tied_newer.id}',
    }
    assert adjacent_links(article_page(client, first)) == {
        'next': f'/post/{tied_older.id}',
    }
    latest_page = article_page(client, newest)
    assert adjacent_links(latest_page) == {'prev': f'/post/{tied_newer.id}'}
    assert not latest_page.xpath(f'//a[@href="/post/{draft.id}" or @href="/post/{future.id}"]')


def test_related_articles_are_capped_and_use_published_category_and_title(client, add_articles):
    current, fourth, third, second, first, _, draft, future = add_articles(
        ('Current', 'reading', -10, True),
        ('Fourth match', 'reading', -9, True),
        ('Third match', 'reading', -8, True),
        ('Second match', 'reading', -6, True),
        ('First match', 'reading', -6, True),
        ('More recent other category', 'other', -2, True),
        ('Hidden draft', 'reading', -1, False),
        ('Future article', 'reading', 1, True),
    )
    db.session.add(PostDraft(post_id=first.id, title='Private revision title', body='Private body'))
    db.session.commit()

    page = article_page(client, current)
    assert related_links(page) == [f'/post/{post.id}' for post in (first, second, third)]
    related = page.xpath('//section[@class="article-related"]')[0]
    assert 'First match' in related.text_content()
    assert 'Private revision title' not in page.text_content()
    assert not related.xpath(f'.//a[@href="/post/{fourth.id}" or @href="/post/{draft.id}" or @href="/post/{future.id}"]')


def test_article_discovery_omits_empty_sections(client, add_articles):
    current, _, _ = add_articles(
        ('Only public article', 'reading', -5, True),
        ('Hidden draft', 'reading', -4, False),
        ('Future article', 'reading', 1, True),
    )
    page = article_page(client, current)
    assert not page.xpath('//*[@class="article-neighbors" or @class="article-related"]')


def test_unmatched_categories_and_uncategorized_articles_hide_related(client, add_articles):
    unique, uncategorized, another = add_articles(
        ('Only in my category', 'reading', -5, True),
        ('No category', None, -4, True),
        ('Also no category', None, -3, True),
    )
    unique_page = article_page(client, unique)
    assert adjacent_links(unique_page) == {'next': f'/post/{uncategorized.id}'}
    uncategorized_page = article_page(client, uncategorized)
    assert adjacent_links(uncategorized_page)['next'] == f'/post/{another.id}'
    for page in (unique_page, uncategorized_page):
        assert not page.xpath('//section[@class="article-related"]')
