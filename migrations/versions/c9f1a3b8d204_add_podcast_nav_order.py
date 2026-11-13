"""add nav_order to podcast_show

Revision ID: c9f1a3b8d204
Revises: 478e950345ef
Create Date: 2026-11-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9f1a3b8d204'
down_revision = '478e950345ef'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('podcast_show')}
    if 'nav_order' not in columns:
        with op.batch_alter_table('podcast_show') as batch:
            batch.add_column(sa.Column(
                'nav_order', sa.Integer(), nullable=False,
                server_default=sa.text('100')))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('podcast_show')}
    if 'nav_order' in columns:
        with op.batch_alter_table('podcast_show') as batch:
            batch.drop_column('nav_order')
