"""comment email notifications: consent flag and the comment a reply answers"""
from alembic import op
import sqlalchemy as sa


revision = 'd7b3a9e41c58'
down_revision = 'a1d9c3e5f7b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post_comment') as batch:
        batch.add_column(sa.Column(
            'notify_replies', sa.Boolean(), nullable=False,
            server_default=sa.false()))
        batch.add_column(sa.Column('answered_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_post_comment_answered_id_post_comment', 'post_comment',
            ['answered_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_post_comment_answered_id', ['answered_id'])


def downgrade():
    with op.batch_alter_table('post_comment') as batch:
        # MySQL will not drop an index a foreign key still relies on.
        batch.drop_constraint(
            'fk_post_comment_answered_id_post_comment', type_='foreignkey')
        batch.drop_index('ix_post_comment_answered_id')
        batch.drop_column('answered_id')
        batch.drop_column('notify_replies')
