"""drop the legacy about table

The about text lives in the page table (slug "about") since 9c8e2f3a4b5d.
Upgrade permanently drops the old table; downgrade recreates it empty.

Revision ID: c8d3a5e7b102
Revises: 5a1f9c0d7e42
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'c8d3a5e7b102'
down_revision = '5a1f9c0d7e42'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')


def upgrade():
    connection = op.get_bind()
    if 'about' not in sa.inspect(connection).get_table_names():
        return
    rows = connection.execute(sa.select(sa.func.count()).select_from(
        sa.table('about'))).scalar_one()
    log.info('Dropping table about (%s rows)', rows)
    op.drop_table('about')


def downgrade():
    op.create_table(
        'about',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
