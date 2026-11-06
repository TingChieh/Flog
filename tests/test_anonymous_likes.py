import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from lxml import html

from app import app, db
from app.models import Post, PostLike
from tests.conftest import login

JSON = {'Accept': 'application/json'}


def like(client, post_id, address='10.0.0.1', **headers):
    return client.post(f'/post/{post_id}/like', headers={**JSON, **headers},
                       environ_overrides={'REMOTE_ADDR': address})


def count(application):
    with application.app_context():
        return db.session.scalar(sa.select(sa.func.count()).select_from(PostLike))


def test_a_guest_can_like_and_take_the_like_back(client, application, users):
    first = like(client, users['post'])
    second = like(client, users['post'])

    assert first.status_code == 200 and first.get_json() == {'liked': True, 'count': 1}
    assert second.get_json() == {'liked': False, 'count': 0}
    assert count(application) == 0


def test_the_browser_gets_a_long_lived_private_cookie_once(client, users):
    first = like(client, users['post'])
    cookie = first.headers['Set-Cookie']

    assert cookie.startswith('flog_visitor=')
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie and 'Max-Age=63072000' in cookie
    assert 'Set-Cookie' not in like(client, users['post']).headers


def test_the_page_remembers_what_this_browser_liked(client, application, users):
    like(client, users['post'])

    liked = html.fromstring(client.get(f'/post/{users["post"]}').data)
    stranger = html.fromstring(application.test_client().get(f'/post/{users["post"]}').data)

    assert liked.xpath('//button[contains(@class,"like-button")]/@aria-pressed') == ['true']
    assert liked.xpath('//span[@data-like-label]/text()') == ['已点赞']
    assert stranger.xpath('//button[contains(@class,"like-button")]/@aria-pressed') == ['false']
    assert stranger.xpath('//form[@data-like-form]')


def test_two_browsers_on_different_networks_both_count(client, application, users):
    like(client, users['post'], address='10.0.0.1')
    other = like(application.test_client(), users['post'], address='10.0.0.2')

    assert other.get_json() == {'liked': True, 'count': 2}


def test_one_network_is_capped_per_post_even_without_cookies(application, users):
    results = [like(application.test_client(), users['post']) for _ in range(5)]

    assert [r.status_code for r in results] == [200, 200, 200, 429, 429]
    assert results[2].get_json()['count'] == 3
    assert results[3].get_json() == {'liked': False, 'count': 3}
    assert count(application) == 3


def test_the_cap_is_per_post_and_per_network(application, users):
    with application.app_context():
        second = Post(title='Two', body='b', user_id=users['author'], is_published=True)
        db.session.add(second)
        db.session.commit()
        second_id = second.id
    for _ in range(3):
        like(application.test_client(), users['post'])

    assert like(application.test_client(), second_id).status_code == 200
    assert like(application.test_client(), users['post'], address='10.0.0.9').status_code == 200


def test_a_browser_that_already_liked_can_still_take_it_back_at_the_cap(client, application, users):
    like(client, users['post'])
    for _ in range(2):
        like(application.test_client(), users['post'])

    assert like(application.test_client(), users['post']).status_code == 429
    assert like(client, users['post']).get_json() == {'liked': False, 'count': 2}


def test_a_visitor_cannot_choose_their_address_through_the_forwarded_header(application, users):
    # The proxy appends the real address last; earlier entries are the visitor's.
    codes = [like(application.test_client(), users['post'],
                  **{'X-Forwarded-For': f'203.0.113.{n}, 198.51.100.7'}).status_code
             for n in range(5)]

    assert codes == [200, 200, 200, 429, 429]


def test_a_limited_like_from_a_plain_form_comes_back_with_a_message(application, users):
    for _ in range(3):
        like(application.test_client(), users['post'])
    client = application.test_client()

    response = client.post(f'/post/{users["post"]}/like', follow_redirects=True,
                           environ_overrides={'REMOTE_ADDR': '10.0.0.1'})

    assert '你所在的网络对这篇文章的点赞已达上限。' in response.get_data(as_text=True)


def test_only_hashes_are_stored(client, application, users):
    response = like(client, users['post'], address='192.0.2.55')
    token = response.headers['Set-Cookie'].split('=', 1)[1].split(';', 1)[0]

    with application.app_context():
        row = db.session.scalar(sa.select(PostLike))
        stored = f'{row.visitor_id} {row.ip_hash}'
        assert '192.0.2.55' not in stored and token not in stored
        assert len(row.visitor_id) == len(row.ip_hash) == 64
        assert row.user_id is None


def test_a_signed_in_like_also_records_the_user(client, application, users):
    login(client, 'other')
    like(client, users['post'])

    with application.app_context():
        row = db.session.scalar(sa.select(PostLike))
        assert row.user_id == users['other'] and row.visitor_id


def test_a_like_made_before_anonymous_likes_still_counts_for_that_user(client, application, users):
    with application.app_context():
        db.session.add(PostLike(post_id=users['post'], user_id=users['other']))
        db.session.commit()
    login(client, 'other')

    page = html.fromstring(client.get(f'/post/{users["post"]}').data)
    result = like(client, users['post'])

    assert page.xpath('//button[contains(@class,"like-button")]/@aria-pressed') == ['true']
    assert result.get_json() == {'liked': False, 'count': 0}


def test_unpublished_posts_cannot_be_liked(client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).is_published = False
        db.session.commit()

    assert like(client, users['post']).status_code == 404


def test_the_proxy_setting_is_one_hop_unless_told_otherwise():
    assert app.config['TRUSTED_PROXY_HOPS'] == 1
    assert app.config['LIKES_PER_IP_PER_POST'] == 3


def load_revision():
    path = Path(__file__).parents[1] / 'migrations' / 'versions' / 'b7d3f9a15c26_anonymous_post_likes.py'
    spec = importlib.util.spec_from_file_location('anonymous_likes', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_like_table(connection):
    connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY)'))
    connection.execute(sa.text('CREATE TABLE user (id INTEGER PRIMARY KEY)'))
    connection.execute(sa.text(
        'CREATE TABLE post_like (id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, '
        'user_id INTEGER NOT NULL, timestamp DATETIME NOT NULL, '
        'FOREIGN KEY(post_id) REFERENCES post (id), FOREIGN KEY(user_id) REFERENCES "user" (id), '
        'CONSTRAINT uq_post_like UNIQUE (post_id, user_id))'))
    connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
    connection.execute(sa.text('INSERT INTO "user" (id) VALUES (7)'))
    connection.execute(sa.text("INSERT INTO post_like (post_id, user_id, timestamp) VALUES (1, 7, '2024-01-01')"))


def test_migration_keeps_existing_likes_and_allows_anonymous_ones():
    revision = load_revision()
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        old_like_table(connection)
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post_like (post_id, user_id, visitor_id, ip_hash, timestamp) "
                "VALUES (1, NULL, 'v1', 'i1', '2024-01-02'), (1, NULL, 'v2', 'i1', '2024-01-02')"))
            rows = connection.execute(sa.text(
                'SELECT user_id, visitor_id FROM post_like ORDER BY id')).all()
            assert rows == [(7, None), (None, 'v1'), (None, 'v2')]
            try:
                connection.execute(sa.text(
                    "INSERT INTO post_like (post_id, visitor_id, timestamp) VALUES (1, 'v1', '2024-01-03')"))
            except sa.exc.IntegrityError:
                duplicate_refused = True
            else:
                duplicate_refused = False
            assert duplicate_refused


def test_migration_downgrade_drops_anonymous_likes_and_restores_the_old_shape():
    revision = load_revision()
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        old_like_table(connection)
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post_like (post_id, visitor_id, timestamp) VALUES (1, 'v1', '2024-01-02')"))
            revision.downgrade()
            columns = {c['name']: c for c in sa.inspect(connection).get_columns('post_like')}
            remaining = connection.execute(sa.text('SELECT user_id FROM post_like')).all()

    assert 'visitor_id' not in columns and 'ip_hash' not in columns
    assert columns['user_id']['nullable'] is False
    assert remaining == [(7,)]
