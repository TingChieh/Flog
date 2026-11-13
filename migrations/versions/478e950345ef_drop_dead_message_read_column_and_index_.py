"""drop dead message read column and index comment email

Revision ID: 478e950345ef
Revises: d9e3f7a1b502
Create Date: 2026-11-13 10:43:35.473947

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '478e950345ef'
down_revision = 'd9e3f7a1b502'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    user_columns = {c['name'] for c in inspector.get_columns('user')}
    if 'last_message_read_time' in user_columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.drop_column('last_message_read_time')

    comment_indexes = {i['name'] for i in inspector.get_indexes('post_comment')}
    if 'ix_post_comment_email' not in comment_indexes:
        op.create_index('ix_post_comment_email', 'post_comment', ['email'], unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    comment_indexes = {i['name'] for i in inspector.get_indexes('post_comment')}
    if 'ix_post_comment_email' in comment_indexes:
        op.drop_index('ix_post_comment_email', table_name='post_comment')

    user_columns = {c['name'] for c in inspector.get_columns('user')}
    if 'last_message_read_time' not in user_columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(sa.Column('last_message_read_time', sa.DateTime(), nullable=True))
