"""add editor write ordering

Revision ID: e3a6f5d7c8b9
Revises: f6d41a2b9c03
"""
from alembic import op
import sqlalchemy as sa


revision = 'e3a6f5d7c8b9'
down_revision = 'f6d41a2b9c03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post') as batch:
        batch.add_column(sa.Column('editor_session_key', sa.String(64)))
        batch.create_unique_constraint(
            'uq_post_editor_session_key', ['editor_session_key'])
    op.add_column('post_draft', sa.Column(
        'last_editor_sequence', sa.Integer(), nullable=False,
        server_default=sa.text('0')))


def downgrade():
    op.drop_column('post_draft', 'last_editor_sequence')
    with op.batch_alter_table('post') as batch:
        batch.drop_constraint('uq_post_editor_session_key', type_='unique')
        batch.drop_column('editor_session_key')
