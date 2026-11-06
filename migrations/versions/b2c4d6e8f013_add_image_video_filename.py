"""add image.video_filename for Live Photo clips

Revision ID: b2c4d6e8f013
Revises: a9b1c3d5e7f2
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c4d6e8f013'
down_revision = 'a9b1c3d5e7f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('image') as batch:
        batch.add_column(sa.Column('video_filename', sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table('image') as batch:
        batch.drop_column('video_filename')
