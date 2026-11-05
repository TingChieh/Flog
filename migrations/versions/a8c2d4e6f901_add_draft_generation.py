"""persist the draft generation and atomic ordering fence

Revision ID: a8c2d4e6f901
Revises: e3a6f5d7c8b9
"""
from alembic import op
import sqlalchemy as sa


revision = 'a8c2d4e6f901'
down_revision = 'e3a6f5d7c8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('post', sa.Column('draft_generation', sa.Integer(),
                                  nullable=False, server_default=sa.text('0')))
    op.add_column('post', sa.Column('draft_sequence', sa.Integer(),
                                  nullable=False, server_default=sa.text('0')))
    post = sa.table('post', sa.column('id'), sa.column('draft_sequence'))
    draft = sa.table('post_draft', sa.column('post_id'),
                     sa.column('last_editor_sequence'))
    op.execute(post.update().values(draft_sequence=sa.func.coalesce(
        sa.select(draft.c.last_editor_sequence).where(
            draft.c.post_id == post.c.id).scalar_subquery(), 0)))


def downgrade():
    op.drop_column('post', 'draft_sequence')
    op.drop_column('post', 'draft_generation')
