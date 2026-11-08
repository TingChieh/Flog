"""a like carries the emoji the reader picked"""
from alembic import op
import sqlalchemy as sa


revision = 'a9c3e7f2d514'
down_revision = 'f4b9d2a73e15'
branch_labels = None
depends_on = None

HEART = '❤️'


def upgrade():
    # Every like made so far was a plain like, which is now the heart.
    with op.batch_alter_table('post_like') as batch:
        batch.add_column(sa.Column(
            'emoji', sa.String(length=16), nullable=False, server_default=HEART))


def downgrade():
    with op.batch_alter_table('post_like') as batch:
        batch.drop_column('emoji')
