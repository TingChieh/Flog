"""add post updated_at"""
from alembic import op
import sqlalchemy as sa


revision = 'a4c8e2f61b07'
down_revision = 'b2c4d6e8f013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('post', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('post', 'updated_at')
