"""add users.avatar_filename for uploaded avatars

Revision ID: f1a2b3c4d5e6
Revises: e8f1a3b5c704
"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e8f1a3b5c704'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('avatar_filename', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('user') as batch:
        batch.drop_column('avatar_filename')
