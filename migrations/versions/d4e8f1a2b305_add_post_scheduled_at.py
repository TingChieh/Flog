"""add scheduled_at to post

Revision ID: d4e8f1a2b305
Revises: c9f1a3b8d204
Create Date: 2026-11-22 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e8f1a2b305'
down_revision = 'c9f1a3b8d204'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('post')}
    indexes = {i['name'] for i in inspector.get_indexes('post')}
    if 'scheduled_at' not in columns:
        with op.batch_alter_table('post') as batch:
            batch.add_column(sa.Column('scheduled_at', sa.DateTime(), nullable=True))
    if 'ix_post_scheduled_at' not in indexes:
        op.create_index('ix_post_scheduled_at', 'post', ['scheduled_at'], unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c['name'] for c in inspector.get_columns('post')}
    indexes = {i['name'] for i in inspector.get_indexes('post')}
    if 'ix_post_scheduled_at' in indexes:
        op.drop_index('ix_post_scheduled_at', table_name='post')
    if 'scheduled_at' in columns:
        with op.batch_alter_table('post') as batch:
            batch.drop_column('scheduled_at')
