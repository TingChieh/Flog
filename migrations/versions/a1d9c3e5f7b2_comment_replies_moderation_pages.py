"""comment replies, moderation, page comments and per-item switches"""
from alembic import op
import sqlalchemy as sa


revision = 'a1d9c3e5f7b2'
down_revision = 'c4e8a1f2b7d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post') as batch:
        batch.add_column(sa.Column(
            'comments_enabled', sa.Boolean(), nullable=False,
            server_default=sa.true()))
    with op.batch_alter_table('page') as batch:
        batch.add_column(sa.Column(
            'comments_enabled', sa.Boolean(), nullable=False,
            server_default=sa.false()))
    with op.batch_alter_table('post_comment') as batch:
        batch.alter_column('post_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('page_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column(
            'status', sa.String(length=10), nullable=False,
            server_default='approved'))
        batch.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('ip_hash', sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            'fk_post_comment_page_id_page', 'page', ['page_id'], ['id'],
            ondelete='CASCADE')
        batch.create_foreign_key(
            'fk_post_comment_parent_id_post_comment', 'post_comment',
            ['parent_id'], ['id'], ondelete='CASCADE')
        batch.create_foreign_key(
            'fk_post_comment_user_id_user', 'user', ['user_id'], ['id'],
            ondelete='SET NULL')
        batch.create_index('ix_post_comment_page_id', ['page_id'])
        batch.create_index('ix_post_comment_parent_id', ['parent_id'])
        batch.create_index('ix_post_comment_user_id', ['user_id'])
        batch.create_index('ix_post_comment_ip_hash', ['ip_hash'])
        batch.create_check_constraint(
            'ck_post_comment_target',
            '(post_id IS NOT NULL) <> (page_id IS NOT NULL)')
        batch.create_check_constraint(
            'ck_post_comment_status', "status IN ('pending', 'approved')")


def downgrade():
    # The old schema has no replies, pages or review queue: drop what it
    # cannot hold rather than show unreviewed comments as published.
    op.execute(
        "DELETE FROM post_comment WHERE page_id IS NOT NULL "
        "OR parent_id IS NOT NULL OR status = 'pending'")
    with op.batch_alter_table('post_comment') as batch:
        batch.drop_constraint('ck_post_comment_status', type_='check')
        batch.drop_constraint('ck_post_comment_target', type_='check')
        # MySQL will not drop an index a foreign key still relies on.
        batch.drop_constraint('fk_post_comment_user_id_user', type_='foreignkey')
        batch.drop_constraint(
            'fk_post_comment_parent_id_post_comment', type_='foreignkey')
        batch.drop_constraint('fk_post_comment_page_id_page', type_='foreignkey')
        batch.drop_index('ix_post_comment_ip_hash')
        batch.drop_index('ix_post_comment_user_id')
        batch.drop_index('ix_post_comment_parent_id')
        batch.drop_index('ix_post_comment_page_id')
        batch.drop_column('ip_hash')
        batch.drop_column('user_id')
        batch.drop_column('status')
        batch.drop_column('parent_id')
        batch.drop_column('page_id')
        batch.alter_column('post_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('page') as batch:
        batch.drop_column('comments_enabled')
    with op.batch_alter_table('post') as batch:
        batch.drop_column('comments_enabled')
