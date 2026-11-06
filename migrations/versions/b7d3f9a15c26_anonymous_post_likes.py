"""let visitors like posts without signing in"""
from alembic import op
import sqlalchemy as sa


revision = 'b7d3f9a15c26'
down_revision = 'a4c8e2f61b07'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post_like') as batch:
        batch.alter_column('user_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('visitor_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('ip_hash', sa.String(length=64), nullable=True))
        batch.create_index('ix_post_like_ip_hash', ['ip_hash'])
        batch.create_unique_constraint('uq_post_like_visitor', ['post_id', 'visitor_id'])


def downgrade():
    # Likes that have no signed-in user cannot be kept once user_id is required.
    op.execute('DELETE FROM post_like WHERE user_id IS NULL')
    with op.batch_alter_table('post_like') as batch:
        batch.drop_constraint('uq_post_like_visitor', type_='unique')
        batch.drop_index('ix_post_like_ip_hash')
        batch.drop_column('ip_hash')
        batch.drop_column('visitor_id')
        batch.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
