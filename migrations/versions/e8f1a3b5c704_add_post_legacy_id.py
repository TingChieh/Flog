"""add posts.legacy_id for the old blog's /archives/<id>/ addresses

Revision ID: e8f1a3b5c704
Revises: d5e7b9c1f203
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8f1a3b5c704'
down_revision = 'd5e7b9c1f203'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post') as batch:
        batch.add_column(sa.Column('legacy_id', sa.Integer(), nullable=True))
        batch.create_index('ix_post_legacy_id', ['legacy_id'], unique=True)


def downgrade():
    with op.batch_alter_table('post') as batch:
        batch.drop_index('ix_post_legacy_id')
        batch.drop_column('legacy_id')
