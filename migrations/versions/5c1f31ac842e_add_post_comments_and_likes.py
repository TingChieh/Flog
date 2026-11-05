"""add post comments and likes

Revision ID: 5c1f31ac842e
Revises: 7aa1cb1910ea
Create Date: 2026-08-12 15:40:00

"""
from alembic import op
import sqlalchemy as sa


revision = '5c1f31ac842e'
down_revision = '7aa1cb1910ea'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'post_comment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_post_comment_post_id', 'post_comment', ['post_id'])
    op.create_index('ix_post_comment_timestamp', 'post_comment', ['timestamp'])

    op.create_table(
        'post_like',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),
    )
    op.create_index('ix_post_like_post_id', 'post_like', ['post_id'])
    op.create_index('ix_post_like_user_id', 'post_like', ['user_id'])


def downgrade():
    op.drop_index('ix_post_like_user_id', table_name='post_like')
    op.drop_index('ix_post_like_post_id', table_name='post_like')
    op.drop_table('post_like')
    op.drop_index('ix_post_comment_timestamp', table_name='post_comment')
    op.drop_index('ix_post_comment_post_id', table_name='post_comment')
    op.drop_table('post_comment')
