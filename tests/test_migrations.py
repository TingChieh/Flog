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


def test_post_like_emoji_revision_is_the_only_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations = Path(__file__).parents[1] / 'migrations'
    config = Config(str(migrations / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations))

    assert ScriptDirectory.from_config(config).get_heads() == [
        'c9f1a3b8d204']


def test_podcast_nav_order_migration_round_trip(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from flask import Flask
    from flask_migrate import Migrate
    from flask_sqlalchemy import SQLAlchemy
    import sqlalchemy as sa

    # Avoid alembic env.py's fileConfig(..., disable_existing_loggers=True)
    # muting app.logger for later tests in the session.
    monkeypatch.setattr('logging.config.fileConfig', lambda *a, **kw: None)

    db_path = tmp_path / 'mig_podcast_nav_order.db'
    url = f'sqlite:///{db_path}'
    migrations = Path(__file__).parents[1] / 'migrations'

    mig_app = Flask('mig_podcast_nav_order')
    mig_app.config['SQLALCHEMY_DATABASE_URI'] = url
    mig_db = SQLAlchemy(mig_app)
    Migrate(mig_app, mig_db, directory=str(migrations))

    config = Config(str(migrations / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations))

    engine = sa.create_engine(url)
    try:
        with mig_app.app_context():
            command.upgrade(config, '478e950345ef')
            with engine.begin() as conn:
                podcast_table = sa.Table(
                    'podcast_show', sa.MetaData(), autoload_with=conn
                )
                assert 'nav_order' not in podcast_table.c
                values = {}
                for col in podcast_table.c:
                    if col.name == 'id':
                        values[col.name] = 1
                    elif isinstance(col.type, sa.Boolean):
                        values[col.name] = True
                    elif isinstance(col.type, sa.Integer):
                        values[col.name] = 0
                    elif isinstance(col.type, sa.DateTime):
                        from datetime import datetime, timezone
                        values[col.name] = datetime(2026, 1, 1, tzinfo=timezone.utc)
                    elif not col.nullable:
                        values[col.name] = 'My Pod' if col.name == 'title' else ''
                conn.execute(podcast_table.insert().values(**values))

            command.upgrade(config, 'c9f1a3b8d204')
            with engine.begin() as conn:
                cols_after = {
                    col['name']
                    for col in sa.inspect(conn).get_columns('podcast_show')
                }
                assert 'nav_order' in cols_after
                row = conn.execute(
                    sa.text('SELECT nav_order FROM podcast_show WHERE id = 1')
                ).one()
                assert row[0] == 100

            command.downgrade(config, '478e950345ef')
            with engine.begin() as conn:
                cols_down = {
                    col['name']
                    for col in sa.inspect(conn).get_columns('podcast_show')
                }
                assert 'nav_order' not in cols_down
    finally:
        with mig_app.app_context():
            mig_db.engine.dispose()
        engine.dispose()


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


COMMENT_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'a1d9c3e5f7b2_comment_replies_moderation_pages.py')


def load_comment_revision():
    spec = importlib.util.spec_from_file_location(
        'comment_replies', COMMENT_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_old_comment_schema(engine):
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('page', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'post_comment', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('post_id', sa.Integer,
                  sa.ForeignKey('post.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False))
    metadata.create_all(engine)


def test_comment_migration_keeps_comments_approved_and_adds_targets():
    revision = load_comment_revision()
    engine = sa.create_engine('sqlite://')
    create_old_comment_schema(engine)

    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
        connection.execute(sa.text('INSERT INTO page (id) VALUES (1)'))
        connection.execute(sa.text(
            "INSERT INTO post_comment (id, post_id, name, email, body, timestamp)"
            " VALUES (1, 1, 'A', 'a@example.com', 'hi', '2026-01-01 00:00:00')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            inspector = sa.inspect(connection)
            columns = {c['name']: c for c in inspector.get_columns('post_comment')}
            assert {'page_id', 'parent_id', 'status', 'user_id', 'ip_hash'} <= set(columns)
            assert columns['post_id']['nullable'] is True
            assert 'comments_enabled' in {c['name'] for c in inspector.get_columns('post')}
            assert 'comments_enabled' in {c['name'] for c in inspector.get_columns('page')}

            assert tuple(connection.execute(sa.text(
                'SELECT status, post_id FROM post_comment')).one()) == ('approved', 1)
            assert connection.execute(sa.text(
                'SELECT comments_enabled FROM post')).scalar_one() == 1
            assert connection.execute(sa.text(
                'SELECT comments_enabled FROM page')).scalar_one() == 0

            connection.execute(sa.text(
                "INSERT INTO post_comment (id, page_id, name, email, body, timestamp)"
                " VALUES (2, 1, 'B', 'b@example.com', 'on a page', '2026-01-02 00:00:00')"))
            with pytest.raises(sa.exc.IntegrityError):
                with connection.begin_nested():
                    connection.execute(sa.text(
                        "INSERT INTO post_comment (id, name, email, body, timestamp)"
                        " VALUES (3, 'C', 'c@example.com', 'nowhere', '2026-01-03 00:00:00')"))


def test_comment_migration_downgrade_drops_what_old_schema_cannot_hold():
    revision = load_comment_revision()
    engine = sa.create_engine('sqlite://')
    create_old_comment_schema(engine)

    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
        connection.execute(sa.text('INSERT INTO page (id) VALUES (1)'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, post_id, name, email, body, status, timestamp)"
                " VALUES (1, 1, 'A', 'a@example.com', 'kept', 'approved', '2026-01-01 00:00:00'),"
                " (2, 1, 'B', 'b@example.com', 'pending', 'pending', '2026-01-02 00:00:00')"))
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, post_id, parent_id, name, email, body, status, timestamp)"
                " VALUES (3, 1, 1, 'C', 'c@example.com', 'a reply', 'approved', '2026-01-03 00:00:00')"))
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, page_id, name, email, body, status, timestamp)"
                " VALUES (4, 1, 'D', 'd@example.com', 'on a page', 'approved', '2026-01-04 00:00:00')"))

            revision.downgrade()

            inspector = sa.inspect(connection)
            names = {c['name'] for c in inspector.get_columns('post_comment')}
            assert names == {'id', 'post_id', 'name', 'email', 'body', 'timestamp'}
            assert 'comments_enabled' not in {c['name'] for c in inspector.get_columns('post')}
            assert 'comments_enabled' not in {c['name'] for c in inspector.get_columns('page')}
            assert connection.execute(sa.text(
                'SELECT id FROM post_comment')).scalars().all() == [1]


NOTIFY_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'd7b3a9e41c58_add_comment_notifications.py')


def load_notify_revision():
    spec = importlib.util.spec_from_file_location(
        'comment_notifications', NOTIFY_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comment_notification_migration_adds_and_removes_columns():
    revision = load_notify_revision()
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE post_comment '
            '(id INTEGER PRIMARY KEY, name VARCHAR(64) NOT NULL)'))
        connection.execute(sa.text(
            "INSERT INTO post_comment (id, name) VALUES (1, 'A')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            columns = {c['name'] for c in
                       sa.inspect(connection).get_columns('post_comment')}
            assert {'notify_replies', 'answered_id'} <= columns
            assert tuple(connection.execute(sa.text(
                'SELECT notify_replies, answered_id FROM post_comment'
            )).one()) == (0, None)

            revision.downgrade()

            columns = {c['name'] for c in
                       sa.inspect(connection).get_columns('post_comment')}
            assert columns == {'id', 'name'}


PODCAST_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'e2a7c5d81f36_add_podcast.py')


def load_podcast_revision():
    spec = importlib.util.spec_from_file_location('add_podcast', PODCAST_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_podcast_migration_lets_comments_belong_to_an_episode_and_back():
    revision = load_podcast_revision()
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE post (id INTEGER PRIMARY KEY)'))
        connection.execute(sa.text('CREATE TABLE page (id INTEGER PRIMARY KEY)'))
        connection.execute(sa.text(
            'CREATE TABLE post_comment (id INTEGER PRIMARY KEY, '
            'post_id INTEGER REFERENCES post (id), '
            'page_id INTEGER REFERENCES page (id), '
            'CONSTRAINT ck_post_comment_target CHECK '
            '((post_id IS NOT NULL) <> (page_id IS NOT NULL)))'))
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
        connection.execute(sa.text(
            'INSERT INTO post_comment (id, post_id) VALUES (1, 1)'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            inspector = sa.inspect(connection)
            assert {'episode', 'podcast_show'} <= set(inspector.get_table_names())
            assert 'episode_id' in {c['name'] for c in inspector.get_columns('post_comment')}
            connection.execute(sa.text(
                "INSERT INTO episode (id, number, title, audio_filename, audio_size, "
                "audio_duration, audio_mime, published_at, created_at) VALUES "
                "(7, 1, 't', 'a.mp3', 1, 1, 'audio/mpeg', '2022-01-01', '2022-01-01')"))
            connection.execute(sa.text(
                'INSERT INTO post_comment (id, episode_id) VALUES (2, 7)'))
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text(
                    'INSERT INTO post_comment (id, post_id, episode_id) VALUES (3, 1, 7)'))
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text('INSERT INTO post_comment (id) VALUES (4)'))

            revision.downgrade()

            inspector = sa.inspect(connection)
            assert 'episode' not in inspector.get_table_names()
            assert 'episode_id' not in {c['name'] for c in inspector.get_columns('post_comment')}
            assert connection.execute(sa.text(
                'SELECT id FROM post_comment')).scalars().all() == [1]


PODCAST_SWITCH_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'f4b9d2a73e15_add_podcast_switch.py')


def test_podcast_switch_migration_adds_the_columns_off_by_default():
    spec = importlib.util.spec_from_file_location(
        'add_podcast_switch', PODCAST_SWITCH_REVISION_PATH)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE podcast_show (id INTEGER PRIMARY KEY, title VARCHAR(120))'))
        connection.execute(sa.text("INSERT INTO podcast_show (id, title) VALUES (1, 'x')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            assert tuple(connection.execute(sa.text(
                'SELECT enabled, show_in_nav FROM podcast_show')).one()) == (0, 1)

            revision.downgrade()

            assert {c['name'] for c in sa.inspect(connection).get_columns(
                'podcast_show')} == {'id', 'title'}


CLEANUP_INDEX_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    '478e950345ef_drop_dead_message_read_column_and_index_.py')


def test_cleanup_and_comment_email_index_migration_round_trips():
    spec = importlib.util.spec_from_file_location(
        'cleanup_and_index', CLEANUP_INDEX_REVISION_PATH)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine('sqlite://')

    with engine.begin() as connection:
        connection.execute(sa.text(
            'CREATE TABLE user (id INTEGER PRIMARY KEY, '
            'username VARCHAR(64), last_message_read_time DATETIME)'))
        connection.execute(sa.text(
            'CREATE TABLE post_comment (id INTEGER PRIMARY KEY, '
            'email VARCHAR(120) NOT NULL)'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            inspector = sa.inspect(connection)
            assert 'last_message_read_time' not in {
                c['name'] for c in inspector.get_columns('user')}
            assert 'ix_post_comment_email' in {
                i['name'] for i in inspector.get_indexes('post_comment')}

            revision.downgrade()

            inspector = sa.inspect(connection)
            assert 'last_message_read_time' in {
                c['name'] for c in inspector.get_columns('user')}
            assert 'ix_post_comment_email' not in {
                i['name'] for i in inspector.get_indexes('post_comment')}
