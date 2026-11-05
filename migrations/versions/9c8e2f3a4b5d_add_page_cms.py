"""add page cms

Revision ID: 9c8e2f3a4b5d
Revises: 8b7d1e2f3a4c
Create Date: 2026-08-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '9c8e2f3a4b5d'
down_revision = '8b7d1e2f3a4c'
branch_labels = None
depends_on = None


def _seed_page(connection, pages, values):
    conditions = [pages.c.slug == values['slug']]
    if values['module_key'] is not None:
        conditions.append(pages.c.module_key == values['module_key'])
    exists = connection.scalar(sa.select(sa.func.count()).select_from(
        pages).where(sa.or_(*conditions)))
    if not exists:
        connection.execute(pages.insert().values(**values))


def upgrade():
    op.create_table(
        'page',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('summary', sa.String(length=300), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False,
                  server_default=sa.text("'content'")),
        sa.Column('module_key', sa.String(length=20), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('show_in_nav', sa.Boolean(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('nav_order', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("kind IN ('content', 'module')",
                           name='ck_page_kind'),
        sa.CheckConstraint(
            "(kind = 'content' AND module_key IS NULL) OR "
            "(kind = 'module' AND module_key IN "
            "('todo', 'movie', 'links', 'guestbook'))",
            name='ck_page_module_key'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module_key', name='uq_page_module_key'),
        sa.UniqueConstraint('slug', name='uq_page_slug'),
    )
    op.create_index('ix_page_slug', 'page', ['slug'], unique=False)
    op.create_table(
        'page_redirect',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['page_id'], ['page.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_page_redirect_slug'),
    )
    op.create_index(
        'ix_page_redirect_page_id', 'page_redirect', ['page_id'], unique=False)
    op.create_index(
        'ix_page_redirect_slug', 'page_redirect', ['slug'], unique=False)

    connection = op.get_bind()
    about_body = ''
    if sa.inspect(connection).has_table('about'):
        about_body = connection.scalar(sa.text(
            'SELECT body FROM about ORDER BY id LIMIT 1')) or ''

    pages = sa.table(
        'page',
        sa.column('title'), sa.column('slug'), sa.column('summary'),
        sa.column('body'), sa.column('kind'), sa.column('module_key'),
        sa.column('is_published'), sa.column('show_in_nav'),
        sa.column('nav_order'),
    )
    seeds = [
        dict(title='About', slug='about', summary=None, body=about_body,
             kind='content', module_key=None, is_published=True,
             show_in_nav=True, nav_order=10),
        dict(title='Todo', slug='todo', summary=None, body=None,
             kind='module', module_key='todo', is_published=True,
             show_in_nav=True, nav_order=20),
        dict(title='Movie', slug='movie', summary=None, body=None,
             kind='module', module_key='movie', is_published=True,
             show_in_nav=True, nav_order=30),
        dict(title='Links', slug='links', summary=None, body=None,
             kind='module', module_key='links', is_published=True,
             show_in_nav=True, nav_order=40),
        dict(title='Guestbook', slug='comment', summary=None, body=None,
             kind='module', module_key='guestbook', is_published=True,
             show_in_nav=True, nav_order=50),
    ]
    for seed in seeds:
        _seed_page(connection, pages, seed)


def downgrade():
    op.drop_index('ix_page_redirect_slug', table_name='page_redirect')
    # MySQL retains the foreign-key index until its table is dropped.
    if op.get_bind().dialect.name not in ('mysql', 'mariadb'):
        op.drop_index('ix_page_redirect_page_id', table_name='page_redirect')
    op.drop_table('page_redirect')
    op.drop_index('ix_page_slug', table_name='page')
    op.drop_table('page')
