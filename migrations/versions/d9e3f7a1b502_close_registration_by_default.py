"""public registration is closed unless an admin opens it"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e3f7a1b502'
down_revision = 'c4d8e2f6a913'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings') as batch_op:
        batch_op.alter_column(
            'registration_open', existing_type=sa.Boolean(),
            nullable=False, server_default=sa.false())
    op.execute(sa.text('UPDATE site_settings SET registration_open = false'))


def downgrade():
    with op.batch_alter_table('site_settings') as batch_op:
        batch_op.alter_column(
            'registration_open', existing_type=sa.Boolean(),
            nullable=False, server_default=sa.true())
