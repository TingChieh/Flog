"""add image width and height

Revision ID: a9b1c3d5e7f2
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b1c3d5e7f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('image') as batch:
        batch.add_column(sa.Column('width', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('height', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('image') as batch:
        batch.drop_column('height')
        batch.drop_column('width')
