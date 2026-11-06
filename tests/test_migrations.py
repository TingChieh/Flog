import importlib.util
import logging
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    '8b7d1e2f3a4c_add_persisted_user_roles.py')
PAGE_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    '9c8e2f3a4b5d_add_page_cms.py')
MARKDOWN_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'b1d4e6f70819_add_content_body_formats.py')
VIEW_COUNT_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'c2f6e8a91d04_add_post_view_count.py')
FOLLOW_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / (
    'versions/d4a7c9e20f13_remove_followers.py')
DRAFTS_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'f6d41a2b9c03_add_site_settings_post_drafts.py')
EDITOR_ORDERING_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'e3a6f5d7c8b9_add_editor_write_ordering.py')
MODULE_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'bad2dd157a5f_remove_site_modules.py')
MESSAGES_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    '5a1f9c0d7e42_remove_messages_profiles_tasks.py')


def load_revision():
    spec = importlib.util.spec_from_file_location('persisted_user_roles',
                                                  REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_page_revision():
    spec = importlib.util.spec_from_file_location('page_cms',
                                                  PAGE_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_markdown_revision():
    spec = importlib.util.spec_from_file_location(
        'content_body_formats', MARKDOWN_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_view_count_revision():
    spec = importlib.util.spec_from_file_location(
        'post_view_count', VIEW_COUNT_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_follow_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_followers', FOLLOW_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_drafts_revision():
    spec = importlib.util.spec_from_file_location(
        'site_settings_post_drafts', DRAFTS_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_editor_ordering_revision():
    spec = importlib.util.spec_from_file_location(
        'editor_write_ordering', EDITOR_ORDERING_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_site_modules', MODULE_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_messages_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'remove_messages_profiles_tasks', MESSAGES_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_drafts_migration_publishes_existing_posts_and_seeds_settings():
    revision = load_drafts_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(title='Existing', body='Body'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()

        post = sa.table('post', sa.column('is_published', sa.Boolean()))
        assert connection.execute(sa.select(post.c.is_published)).scalar_one() is True
        assert connection.execute(sa.text(
            'SELECT registration_open, post_revision_limit FROM site_settings'
        )).mappings().one() == {
            'registration_open': True, 'post_revision_limit': 20}


def test_view_count_migration_backfills_and_preserves_existing_posts():
    revision = load_view_count_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(
            title='Existing', body='<p>Keep me</p>'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post (title, body) VALUES ('Later', '<p>New</p>')"))
            rows = connection.execute(sa.text(
                'SELECT title, body, view_count FROM post ORDER BY id'
            )).mappings().all()
            assert rows == [
                {'title': 'Existing', 'body': '<p>Keep me</p>', 'view_count': 0},
                {'title': 'Later', 'body': '<p>New</p>', 'view_count': 0},
            ]
            column = next(item for item in sa.inspect(connection).get_columns(
                'post') if item['name'] == 'view_count')
            assert column['nullable'] is False
            revision.downgrade()

        assert 'view_count' not in {
            item['name'] for item in sa.inspect(connection).get_columns('post')}
        assert connection.execute(sa.text(
            'SELECT title, body FROM post ORDER BY id'
        )).mappings().all()[0] == {
            'title': 'Existing', 'body': '<p>Keep me</p>'}


def test_follow_removal_upgrade_drops_only_followers_and_preserves_content():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(64), nullable=False),
    )
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id')),
    )
    pages = sa.Table(
        'page', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('module_key', sa.String(32)),
        sa.Column('is_published', sa.Boolean, nullable=False),
        sa.Column('show_in_nav', sa.Boolean, nullable=False),
        sa.Column('nav_order', sa.Integer, nullable=False),
    )
    followers = sa.Table(
        'followers', metadata,
        sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
        sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(users.insert(), [
            {'id': 1, 'username': 'author'},
            {'id': 2, 'username': 'reader'},
        ])
        connection.execute(posts.insert().values(
            id=7, title='Preserved', user_id=1))
        connection.execute(pages.insert().values(
            id=9, module_key='todo', is_published=False,
            show_in_nav=True, nav_order=27))
        connection.execute(followers.insert().values(
            follower_id=2, followed_id=1))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

        inspector = sa.inspect(connection)
        assert 'followers' not in inspector.get_table_names()
        assert connection.execute(sa.text(
            'SELECT id, username FROM user ORDER BY id'
        )).mappings().all() == [
            {'id': 1, 'username': 'author'},
            {'id': 2, 'username': 'reader'},
        ]
        assert connection.execute(sa.text(
            'SELECT id, title, user_id FROM post')).mappings().one() == {
                'id': 7, 'title': 'Preserved', 'user_id': 1}
        assert connection.execute(sa.text(
            'SELECT id, module_key, is_published, show_in_nav, nav_order '
            'FROM page')).mappings().one() == {
                'id': 9, 'module_key': 'todo', 'is_published': False,
                'show_in_nav': True, 'nav_order': 27}


def test_follow_removal_downgrade_recreates_empty_table_with_constraints():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'followers', metadata,
        sa.Column('follower_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
        sa.Column('followed_id', sa.Integer, sa.ForeignKey('user.id'),
                  primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()

        inspector = sa.inspect(connection)
        assert connection.execute(sa.text(
            'SELECT COUNT(*) FROM followers')).scalar_one() == 0
        assert inspector.get_pk_constraint('followers')[
            'constrained_columns'] == ['follower_id', 'followed_id']
        foreign_keys = inspector.get_foreign_keys('followers')
        assert {tuple(item['constrained_columns']) for item in foreign_keys} == {
            ('follower_id',), ('followed_id',)}
        assert {item['referred_table'] for item in foreign_keys} == {'user'}


def test_follow_removal_upgrade_refuses_missing_followers_table():
    revision = load_follow_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with pytest.raises(sa.exc.OperationalError):
                revision.upgrade()


def test_anonymous_likes_revision_is_the_only_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations = Path(__file__).parents[1] / 'migrations'
    config = Config(str(migrations / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations))

    assert ScriptDirectory.from_config(config).get_heads() == [
        'b7d3f9a15c26']


def test_draft_generation_migration_preserves_existing_sequence():
    path = Path(__file__).parents[1] / 'migrations/versions/a8c2d4e6f901_add_draft_generation.py'
    spec = importlib.util.spec_from_file_location('draft_generation', path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    post = sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True))
    draft = sa.Table('post_draft', metadata,
                     sa.Column('post_id', sa.Integer, primary_key=True),
                     sa.Column('last_editor_sequence', sa.Integer, nullable=False))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(post.insert(), [{'id': 1}, {'id': 2}])
        connection.execute(draft.insert().values(post_id=1, last_editor_sequence=9))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.execute(sa.text(
            'SELECT draft_generation, draft_sequence FROM post ORDER BY id'
        )).all() == [(0, 9), (0, 0)]
        with Operations.context(MigrationContext.configure(connection)):
            revision.downgrade()
        assert connection.execute(sa.select(post.c.id).order_by(post.c.id)).all() == [(1,), (2,)]


def test_editor_ordering_migration_adds_session_key_and_sequence():
    revision = load_editor_ordering_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('post_draft', metadata,
             sa.Column('post_id', sa.Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        inspector = sa.inspect(connection)
        assert {'editor_session_key'} <= {
            column['name'] for column in inspector.get_columns('post')}
        sequence = next(column for column in inspector.get_columns('post_draft')
                        if column['name'] == 'last_editor_sequence')
        assert sequence['nullable'] is False


def test_configured_admin_emails_normalizes_case_and_whitespace():
    revision = load_revision()

    assert revision.configured_admin_emails(
        ' Admin@Example.com, second@example.com, ADMIN@example.com, '
    ) == {'admin@example.com', 'second@example.com'}


def test_require_admin_match_requires_an_existing_user_email():
    revision = load_revision()

    with pytest.raises(RuntimeError, match='ADMIN_EMAILS must contain an existing user email'):
        revision.require_admin_match({'missing@example.com'},
                                     ['member@example.com'])


def test_role_upgrade_refusal_leaves_schema_unchanged(monkeypatch):
    revision = load_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(120), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(users.insert().values(email='member@example.com'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            monkeypatch.setenv('ADMIN_EMAILS', 'missing@example.com')
            with pytest.raises(RuntimeError, match='existing user email'):
                revision.upgrade()

        columns = {item['name'] for item in sa.inspect(connection).get_columns(
            'user')}
        assert columns == {'id', 'email'}


@pytest.mark.parametrize('admin_emails', [None, 'missing@example.com'])
def test_role_upgrade_empty_users_warns_and_creates_role(
        monkeypatch, caplog, admin_emails):
    revision = load_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('user', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('email', sa.String(120), nullable=False))
    metadata.create_all(engine)
    if admin_emails is None:
        monkeypatch.delenv('ADMIN_EMAILS', raising=False)
    else:
        monkeypatch.setenv('ADMIN_EMAILS', admin_emails)

    with engine.begin() as connection:
        with caplog.at_level(logging.WARNING, logger='alembic'):
            with Operations.context(MigrationContext.configure(connection)):
                revision.upgrade()
        column = next(column for column in sa.inspect(connection).get_columns('user')
                      if column['name'] == 'role')
        assert column['nullable'] is False
        assert connection.execute(sa.text('SELECT COUNT(*) FROM user')).scalar_one() == 0
        connection.execute(sa.text("INSERT INTO user (email) VALUES ('later@example.com')"))
        assert connection.execute(sa.text('SELECT role FROM user')).scalar_one() == 'user'

    warning = ' '.join(record.getMessage() for record in caplog.records
                       if record.levelno == logging.WARNING and
                       record.name.startswith('alembic'))
    assert 'no users' in warning.lower()
    assert 'admin' in warning.lower()
    assert 'ADMIN_EMAILS' in warning
    assert 'after users are created' in warning.lower()


def test_role_upgrade_with_users_and_unset_admin_emails_raises(monkeypatch):
    revision = load_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users = sa.Table('user', metadata,
                     sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('email', sa.String(120), nullable=False))
    metadata.create_all(engine)
    monkeypatch.delenv('ADMIN_EMAILS', raising=False)
    with engine.begin() as connection:
        connection.execute(users.insert().values(email='member@example.com'))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match='existing user email'):
                revision.upgrade()
        assert 'role' not in {column['name'] for column in
                              sa.inspect(connection).get_columns('user')}


def test_upgrade_promotes_configured_emails_and_downgrade_removes_role(
        monkeypatch):
    revision = load_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(120), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(users.insert(), [
            {'email': 'Admin@Example.com'},
            {'email': 'member@example.com'},
        ])
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            monkeypatch.setenv('ADMIN_EMAILS', 'admin@example.com')
            revision.upgrade()

            rows = connection.execute(sa.text(
                'SELECT email, role FROM user ORDER BY id')).mappings().all()
            assert rows == [
                {'email': 'Admin@Example.com', 'role': 'admin'},
                {'email': 'member@example.com', 'role': 'user'},
            ]

            revision.downgrade()

        assert 'role' not in sa.inspect(connection).get_columns('user')


def test_page_migration_seeds_content_and_module_pages():
    revision = load_page_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    about = sa.Table(
        'about', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('body', sa.Text, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(about.insert().values(body='<p>Existing about</p>'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            pages = connection.execute(sa.text(
                'SELECT slug, kind, module_key, body, is_published, '
                'show_in_nav, nav_order FROM page ORDER BY nav_order'
            )).mappings().all()
            assert len(pages) == 5
            assert pages[0]['slug'] == 'about'
            assert pages[0]['body'] == '<p>Existing about</p>'
            assert {row['module_key'] for row in pages[1:]} == {
                'todo', 'movie', 'links', 'guestbook'}
            assert all(row['is_published'] for row in pages)
            assert all(row['show_in_nav'] for row in pages)

            revision.downgrade()

        tables = sa.inspect(connection).get_table_names()
        assert 'page' not in tables
        assert 'page_redirect' not in tables
        assert 'about' in tables


def test_content_format_migration_preserves_existing_bodies():
    revision = load_markdown_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table('post', metadata,
                     sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('body', sa.Text, nullable=False))
    pages = sa.Table('page', metadata,
                     sa.Column('id', sa.Integer, primary_key=True),
                     sa.Column('body', sa.Text))
    metadata.create_all(engine)
    post_body = '<table><tr><td>legacy</td></tr></table>'
    page_body = '<p data-old="yes">legacy page</p>'

    with engine.begin() as connection:
        connection.execute(posts.insert().values(body=post_body))
        connection.execute(pages.insert().values(body=page_body))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            assert connection.execute(sa.text(
                'SELECT body, body_format FROM post')).mappings().one() == {
                    'body': post_body, 'body_format': 'html'}
            assert connection.execute(sa.text(
                'SELECT body, body_format FROM page')).mappings().one() == {
                    'body': page_body, 'body_format': 'html'}
            revision.downgrade()

        assert 'body_format' not in {
            column['name'] for column in sa.inspect(connection).get_columns('post')}


@pytest.mark.parametrize(('invalid_table', 'invalid_format'), [
    pytest.param('post', 'markdown', id='post-markdown'),
    pytest.param('page', 'markdown', id='page-markdown'),
    pytest.param('post', None, id='post-null'),
    pytest.param('page', None, id='page-null'),
    pytest.param('post', 'HTML', id='post-uppercase-html'),
    pytest.param('page', 'HTML', id='page-uppercase-html'),
    pytest.param('post', 'Html', id='post-titlecase-html'),
    pytest.param('page', 'hTmL', id='page-mixedcase-html'),
])
def test_content_format_downgrade_refuses_lossy_rows_before_schema_changes(
        invalid_table, invalid_format):
    revision = load_markdown_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('body_format', sa.String(20, collation='NOCASE')),
    )
    pages = sa.Table(
        'page', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('body', sa.Text),
        sa.Column('body_format', sa.String(20, collation='NOCASE')),
    )
    metadata.create_all(engine)
    expected = {
        'post': {'body': '<p>post source</p>', 'body_format': 'html'},
        'page': {'body': '<p>page source</p>', 'body_format': 'html'},
    }
    expected[invalid_table]['body_format'] = invalid_format

    with engine.begin() as connection:
        connection.execute(posts.insert().values(**expected['post']))
        connection.execute(pages.insert().values(**expected['page']))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with pytest.raises(RuntimeError):
                revision.downgrade()

        inspector = sa.inspect(connection)
        for table_name in ('post', 'page'):
            assert 'body_format' in {
                column['name']
                for column in inspector.get_columns(table_name)
            }
            assert connection.execute(sa.text(
                f'SELECT body, body_format FROM {table_name}'
            )).mappings().one() == expected[table_name]


def _module_removal_tables(metadata):
    users = sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False))
    pages = sa.Table(
        'page', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('slug', sa.String(120), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('module_key', sa.String(20)))
    redirects = sa.Table(
        'page_redirect', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('slug', sa.String(120), nullable=False),
        sa.Column('page_id', sa.Integer, sa.ForeignKey('page.id'), nullable=False))
    legacy = {
        'todo': sa.Table('todo', metadata, sa.Column('id', sa.Integer, primary_key=True),
                         sa.Column('title', sa.String(120))),
        'movie': sa.Table('movie', metadata, sa.Column('id', sa.Integer, primary_key=True),
                          sa.Column('title', sa.String(60))),
        'link': sa.Table('link', metadata, sa.Column('id', sa.Integer, primary_key=True),
                         sa.Column('name', sa.String(64))),
        'comment': sa.Table('comment', metadata, sa.Column('id', sa.Integer, primary_key=True),
                            sa.Column('name', sa.String(64))),
    }
    return users, posts, pages, redirects, legacy


def test_module_removal_upgrade_drops_module_data_and_keeps_content(caplog):
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _, posts, pages, redirects, legacy = _module_removal_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(id=7, title='Preserved'))
        connection.execute(pages.insert(), [
            {'id': 1, 'slug': 'about', 'kind': 'content', 'module_key': None},
            {'id': 2, 'slug': 'links', 'kind': 'module', 'module_key': 'links'},
            {'id': 3, 'slug': 'guestbook', 'kind': 'module', 'module_key': 'guestbook'},
            {'id': 4, 'slug': 'notes', 'kind': 'content', 'module_key': None},
        ])
        connection.execute(redirects.insert(), [
            {'id': 1, 'slug': 'old-links', 'page_id': 2},
            {'id': 2, 'slug': 'old-notes', 'page_id': 4},
        ])
        for table in legacy.values():
            connection.execute(table.insert().values(id=1))
        context = MigrationContext.configure(connection)
        with caplog.at_level(logging.INFO, logger='alembic.runtime.migration'):
            with Operations.context(context):
                revision.upgrade()

        tables = sa.inspect(connection).get_table_names()
        assert {'todo', 'movie', 'link', 'comment'}.isdisjoint(tables)
        assert connection.execute(sa.text(
            'SELECT slug FROM page ORDER BY id')).scalars().all() == ['about', 'notes']
        assert connection.execute(sa.text(
            'SELECT slug FROM page_redirect')).scalars().all() == ['old-notes']
        assert connection.execute(sa.text(
            'SELECT title FROM post')).scalars().all() == ['Preserved']
    messages = ' '.join(record.getMessage() for record in caplog.records)
    for name in ('todo', 'movie', 'link', 'comment', 'module pages'):
        assert name in messages


def test_module_removal_upgrade_tolerates_missing_tables():
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('page', metadata, sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('kind', sa.String(20), nullable=False))
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
        assert sa.inspect(connection).get_table_names() == ['page']

    bare = sa.create_engine('sqlite://')
    with bare.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()


def test_module_removal_downgrade_recreates_empty_tables():
    revision = load_module_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _module_removal_tables(metadata)
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()
        inspector = sa.inspect(connection)
        columns = {name: {c['name'] for c in inspector.get_columns(name)}
                   for name in ('todo', 'movie', 'link', 'comment')}
        assert columns['todo'] == {'id', 'title', 'complete'}
        assert columns['movie'] == {'id', 'title', 'year'}
        assert columns['link'] == {'id', 'name', 'email', 'text', 'url', 'created_at'}
        assert columns['comment'] == {'id', 'email', 'name', 'body', 'timestamp'}
        for name in columns:
            assert connection.execute(sa.text(
                f'SELECT COUNT(*) FROM {name}')).scalar_one() == 0
        assert {'ix_comment_timestamp'} <= {
            index['name'] for index in inspector.get_indexes('comment')}


def _messages_removal_tables(metadata):
    users = sa.Table(
        'user', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(64), nullable=False))
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False))
    legacy = {
        'message': sa.Table(
            'message', metadata, sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('sender_id', sa.Integer, sa.ForeignKey('user.id'))),
        'notification': sa.Table(
            'notification', metadata, sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'))),
        'task': sa.Table(
            'task', metadata, sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'))),
    }
    return users, posts, legacy


def test_messages_removal_upgrade_drops_tables_and_keeps_content(caplog):
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    users, posts, legacy = _messages_removal_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(users.insert().values(id=1, username='author'))
        connection.execute(posts.insert().values(id=7, title='Preserved'))
        connection.execute(legacy['message'].insert().values(id=1, sender_id=1))
        connection.execute(legacy['notification'].insert().values(id=1, user_id=1))
        connection.execute(legacy['task'].insert().values(id='t1', user_id=1))
        context = MigrationContext.configure(connection)
        with caplog.at_level(logging.INFO, logger='alembic.runtime.migration'):
            with Operations.context(context):
                revision.upgrade()

        tables = sa.inspect(connection).get_table_names()
        assert {'message', 'notification', 'task'}.isdisjoint(tables)
        assert connection.execute(sa.text(
            'SELECT username FROM user')).scalars().all() == ['author']
        assert connection.execute(sa.text(
            'SELECT title FROM post')).scalars().all() == ['Preserved']
    messages = ' '.join(record.getMessage() for record in caplog.records)
    for name in ('message', 'notification', 'task'):
        assert name in messages


def test_messages_removal_upgrade_tolerates_missing_tables():
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()


def test_messages_removal_downgrade_recreates_empty_tables():
    revision = load_messages_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    _messages_removal_tables(metadata)
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            revision.downgrade()
        inspector = sa.inspect(connection)
        columns = {name: {c['name'] for c in inspector.get_columns(name)}
                   for name in ('message', 'notification', 'task')}
        assert columns['message'] == {
            'id', 'sender_id', 'recipient_id', 'body', 'timestamp'}
        assert columns['notification'] == {
            'id', 'name', 'user_id', 'timestamp', 'payload_json'}
        assert columns['task'] == {
            'id', 'name', 'description', 'user_id', 'complete'}
        for name in columns:
            assert connection.execute(sa.text(
                f'SELECT COUNT(*) FROM {name}')).scalar_one() == 0
        indexed = {name: {tuple(i['column_names'])
                          for i in inspector.get_indexes(name)}
                   for name in columns}
        assert {('sender_id',), ('recipient_id',), ('timestamp',)} <= indexed['message']
        assert {('name',), ('user_id',), ('timestamp',)} <= indexed['notification']
        assert ('name',) in indexed['task']
        assert {fk['referred_table'] for fk in inspector.get_foreign_keys('message')} == {'user'}


ABOUT_REMOVAL_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'c8d3a5e7b102_drop_about_table.py')


def load_about_removal_revision():
    spec = importlib.util.spec_from_file_location(
        'about_removal', ABOUT_REMOVAL_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_about_removal_drops_the_table_and_downgrade_recreates_it_empty():
    revision = load_about_removal_revision()
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('about', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('body', sa.Text, nullable=False))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO about (body) VALUES ('<p>x</p>')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            assert 'about' not in sa.inspect(connection).get_table_names()

            revision.downgrade()
            assert 'about' in sa.inspect(connection).get_table_names()
            assert connection.execute(sa.text(
                'SELECT COUNT(*) FROM about')).scalar_one() == 0


def test_about_removal_upgrade_tolerates_a_missing_table():
    revision = load_about_removal_revision()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()


IMAGE_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'd5e7b9c1f203_add_image_table.py')


def test_image_migration_creates_and_drops_the_table():
    spec = importlib.util.spec_from_file_location(
        'image_table', IMAGE_REVISION_PATH)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            inspector = sa.inspect(connection)
            columns = {c['name'] for c in inspector.get_columns('image')}
            assert columns == {'id', 'filename', 'original_name', 'title',
                               'note', 'size', 'user_id', 'created_at'}
            unique = {tuple(i['column_names']) for i in inspector.get_indexes('image')
                      if i['unique']}
            assert ('filename',) in unique

            revision.downgrade()
            assert 'image' not in sa.inspect(connection).get_table_names()


LEGACY_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'e8f1a3b5c704_add_post_legacy_id.py')


def test_legacy_id_migration_adds_and_removes_the_column():
    spec = importlib.util.spec_from_file_location('legacy_id', LEGACY_REVISION_PATH)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1), (2)'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            inspector = sa.inspect(connection)
            assert 'legacy_id' in {c['name'] for c in inspector.get_columns('post')}
            assert any(i['unique'] and i['column_names'] == ['legacy_id']
                       for i in inspector.get_indexes('post'))
            # existing posts keep working and several may have no legacy id
            assert connection.execute(sa.text(
                'SELECT COUNT(*) FROM post WHERE legacy_id IS NULL')).scalar_one() == 2

            revision.downgrade()
            assert 'legacy_id' not in {
                c['name'] for c in sa.inspect(connection).get_columns('post')}
