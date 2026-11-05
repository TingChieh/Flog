"""remove the built-in site modules

Upgrade permanently deletes module pages (and their redirects) and drops the
todo, movie, link and comment (guestbook) tables with all their rows.
Downgrade recreates the four tables empty; deleted rows and module pages are
unrecoverable.

Revision ID: bad2dd157a5f
Revises: b5e1a7c9d234
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'bad2dd157a5f'
down_revision = 'b5e1a7c9d234'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')
MODULE_TABLES = ('todo', 'movie', 'link', 'comment')


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())

    if 'page' in tables:
        page = sa.table('page', sa.column('id'), sa.column('kind'))
        module_ids = sa.select(page.c.id).where(page.c.kind == 'module')
        if 'page_redirect' in tables:
            redirect = sa.table('page_redirect', sa.column('page_id'))
            result = connection.execute(
                sa.delete(redirect).where(redirect.c.page_id.in_(module_ids)))
            log.info('Removed %s redirects of module pages', result.rowcount)
        result = connection.execute(
            sa.delete(page).where(page.c.kind == 'module'))
        log.info('Removed %s module pages', result.rowcount)

    for name in MODULE_TABLES:
        if name not in tables:
            continue
        rows = connection.execute(sa.select(sa.func.count()).select_from(
            sa.table(name))).scalar_one()
        log.info('Dropping table %s (%s rows)', name, rows)
        op.drop_table(name)


def downgrade():
    op.create_table(
        'todo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'movie',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=60), nullable=False),
        sa.Column('year', sa.String(length=5), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'link',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('text', sa.String(length=128), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('body', sa.String(length=240), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_comment_timestamp', 'comment', ['timestamp'])
