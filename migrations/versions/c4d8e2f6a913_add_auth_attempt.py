"""failed sign-ins and reset requests are counted to slow down guessing"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d8e2f6a913'
down_revision = 'a9c3e7f2d514'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auth_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_auth_attempt_lookup', 'auth_attempt',
                    ['action', 'key_hash', 'created_at'])
    op.create_index(op.f('ix_auth_attempt_created_at'), 'auth_attempt',
                    ['created_at'])


def downgrade():
    op.drop_index(op.f('ix_auth_attempt_created_at'), table_name='auth_attempt')
    op.drop_index('ix_auth_attempt_lookup', table_name='auth_attempt')
    op.drop_table('auth_attempt')
