"""remove followers

Upgrade permanently deletes all follow relationships. Downgrade restores only
the empty association-table schema; deleted relationship rows are unrecoverable.

Revision ID: d4a7c9e20f13
Revises: c2f6e8a91d04
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a7c9e20f13'
down_revision = 'c2f6e8a91d04'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('followers')


def downgrade():
    op.create_table(
        'followers',
        sa.Column('follower_id', sa.Integer(), nullable=False),
        sa.Column('followed_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['followed_id'], ['user.id']),
        sa.ForeignKeyConstraint(['follower_id'], ['user.id']),
        sa.PrimaryKeyConstraint('follower_id', 'followed_id'),
    )
