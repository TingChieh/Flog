"""podcast switch: off until an admin turns it on, and a menu link switch"""
from alembic import op
import sqlalchemy as sa


revision = 'f4b9d2a73e15'
down_revision = 'e2a7c5d81f36'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('podcast_show') as batch:
        batch.add_column(sa.Column(
            'enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column(
            'show_in_nav', sa.Boolean(), nullable=False,
            server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('podcast_show') as batch:
        batch.drop_column('show_in_nav')
        batch.drop_column('enabled')
