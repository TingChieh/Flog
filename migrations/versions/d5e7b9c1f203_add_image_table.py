"""add the image table

Records every uploaded image (name, note, size, uploader). Files on disk are
not touched; the image library registers existing files on first use.
Downgrade drops the table only.

Revision ID: d5e7b9c1f203
Revises: c8d3a5e7b102
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e7b9c1f203'
down_revision = 'c8d3a5e7b102'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'image',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=80), nullable=False),
        sa.Column('original_name', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_image_filename', 'image', ['filename'], unique=True)
    op.create_index('ix_image_user_id', 'image', ['user_id'])


def downgrade():
    op.drop_index('ix_image_user_id', table_name='image')
    op.drop_index('ix_image_filename', table_name='image')
    op.drop_table('image')
