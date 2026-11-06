import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from lxml import html

from app import db
from app.models import Post
from app.post_drafts import DraftValues, publish_draft, save_draft, unpublish_post
from app.timezones import later_update
from tests.conftest import login

LONG_AGO = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def publish_new(users, title='T', body='body'):
    author = db.session.get(db.session.get(Post, users['post']).author.__class__, users['author'])
    post = save_draft(author, None, DraftValues(title, body, 1))
    db.session.flush()
    publish_draft(author, post.id)
    db.session.commit()
    return author, post


def test_first_publish_sets_the_publish_time_not_the_draft_creation_time(application, users):
    author = db.session.get(db.session.get(Post, users['post']).author.__class__, users['author'])
    post = save_draft(author, None, DraftValues('T', 'body', 1))
    db.session.flush()
    post.timestamp = LONG_AGO
    db.session.commit()

    publish_draft(author, post.id)
    db.session.commit()

    assert (datetime.now(timezone.utc) - aware(post.timestamp)).total_seconds() < 60
    assert post.updated_at is None


def test_publishing_an_update_keeps_the_publish_time_and_sets_the_update_time(application, users):
    author, post = publish_new(users)
    post.timestamp = LONG_AGO
    db.session.commit()

    save_draft(author, post, DraftValues('T', 'changed', 1))
    publish_draft(author, post.id)
    db.session.commit()

    assert aware(post.timestamp) == LONG_AGO
    assert (datetime.now(timezone.utc) - aware(post.updated_at)).total_seconds() < 60


def test_publishing_an_unchanged_draft_is_not_an_update(application, users):
    author, post = publish_new(users)
    save_draft(author, post, DraftValues('T', 'body', 1))

    publish_draft(author, post.id)
    db.session.commit()

    assert post.updated_at is None


def test_unpublish_and_republish_counts_as_a_new_publication(application, users):
    author, post = publish_new(users)
    post.timestamp = LONG_AGO
    post.updated_at = LONG_AGO
    db.session.commit()

    unpublish_post(author, post.id)
    publish_draft(author, post.id)
    db.session.commit()

    assert (datetime.now(timezone.utc) - aware(post.timestamp)).total_seconds() < 60
    assert post.updated_at is None


def test_an_update_on_the_publish_day_is_not_announced(application):
    published = datetime(2024, 1, 2, 1, 0)      # 09:00 in China
    same_day = datetime(2024, 1, 2, 10, 0)      # 18:00 in China
    next_day = datetime(2024, 1, 2, 17, 0)      # 01:00 the next day in China

    with application.app_context():
        assert later_update(published, None) is None
        assert later_update(published, same_day) is None
        assert later_update(published, next_day).day == 3


def article(client, post_id):
    return html.fromstring(client.get(f'/post/{post_id}').data)


def test_article_header_shows_the_publish_date(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.timestamp = datetime(2024, 3, 5, 4, 0)
        db.session.commit()

    page = article(client, users['post'])

    times = page.xpath('//header[contains(@class,"article-header")]//time')
    assert [t.text_content().strip() for t in times] == ['发布于 2024年3月5日']
    assert times[0].get('datetime').startswith('2024-03-05T12:00:00')


def test_article_header_adds_the_update_date_when_it_is_a_later_day(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.timestamp = datetime(2024, 3, 5, 4, 0)
        post.updated_at = datetime(2024, 4, 9, 4, 0)
        db.session.commit()

    page = article(client, users['post'])

    times = page.xpath('//header[contains(@class,"article-header")]//time')
    assert [t.text_content().strip() for t in times] == ['发布于 2024年3月5日', '更新于 2024年4月9日']


def test_article_header_hides_a_same_day_update(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.timestamp = datetime(2024, 3, 5, 4, 0)
        post.updated_at = datetime(2024, 3, 5, 9, 0)
        db.session.commit()

    times = article(client, users['post']).xpath('//header[contains(@class,"article-header")]//time')

    assert len(times) == 1


def test_sitemap_carries_the_update_time(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.timestamp = datetime(2024, 3, 5, 4, 0)
        post.updated_at = datetime(2024, 4, 9, 4, 0)
        db.session.commit()

    sitemap = client.get('/sitemap.xml').get_data(as_text=True)

    assert '<lastmod>2024-04-09T04:00:00</lastmod>' in sitemap


def test_preview_shows_how_the_dates_will_read(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.timestamp = datetime(2024, 3, 5, 4, 0)
        db.session.commit()
    login(client, 'author')

    live = html.fromstring(client.post('/admin/posts/preview', data={
        'post_id': users['post'], 'title': 'T', 'body': 'x'}).data)
    new = html.fromstring(client.post('/admin/posts/preview', data={'title': 'T', 'body': 'x'}).data)

    live_times = [t.text_content().strip() for t in live.xpath('//header[contains(@class,"article-header")]//time')]
    new_times = [t.text_content().strip() for t in new.xpath('//header[contains(@class,"article-header")]//time')]
    today = datetime.now(timezone.utc).strftime('%Y年%-m月')
    assert live_times[0] == '发布于 2024年3月5日'
    assert live_times[1].startswith('更新于 ') and today in live_times[1]
    assert len(new_times) == 1 and today in new_times[0]


def test_migration_adds_a_nullable_column_and_keeps_existing_posts():
    path = Path(__file__).parents[1] / 'migrations' / 'versions' / 'a4c8e2f61b07_add_post_updated_at.py'
    spec = importlib.util.spec_from_file_location('post_updated_at', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('title', sa.String(120), nullable=False))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(title='Existing'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            rows = connection.execute(sa.text('SELECT title, updated_at FROM post')).all()
            assert rows == [('Existing', None)]
            revision.downgrade()
            columns = [c['name'] for c in sa.inspect(connection).get_columns('post')]
    assert 'updated_at' not in columns
