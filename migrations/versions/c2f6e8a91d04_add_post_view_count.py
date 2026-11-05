"""add post view count"""
from alembic import op
import sqlalchemy as sa


revision = 'c2f6e8a91d04'
down_revision = 'b1d4e6f70819'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('post', sa.Column(
        'view_count', sa.Integer(), nullable=False,
        server_default=sa.text('0')))


def downgrade():
    op.drop_column('post', 'view_count')
