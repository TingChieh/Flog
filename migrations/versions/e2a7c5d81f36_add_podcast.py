"""podcast: show settings, episodes and episode comments"""
from alembic import op
import sqlalchemy as sa


revision = 'e2a7c5d81f36'
down_revision = 'd7b3a9e41c58'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'podcast_show',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=120), nullable=True),
        sa.Column('owner_email', sa.String(length=120), nullable=True),
        sa.Column('category', sa.String(length=60), nullable=True),
        sa.Column('cover_filename', sa.String(length=80), nullable=True),
        sa.Column('apple_url', sa.String(length=300), nullable=True),
        sa.Column('xiaoyuzhou_url', sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint('id'))
    op.create_table(
        'episode',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('audio_filename', sa.String(length=80), nullable=False),
        sa.Column('audio_size', sa.BigInteger(), nullable=False),
        sa.Column('audio_duration', sa.Integer(), nullable=False),
        sa.Column('audio_mime', sa.String(length=40), nullable=False),
        sa.Column('cover_filename', sa.String(length=80), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('comments_enabled', sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column('published_at', sa.DateTime(), nullable=False),
        sa.Column('legacy_path', sa.String(length=255), nullable=True),
        sa.Column('feed_guid', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('number'),
        sa.UniqueConstraint('legacy_path'))
    op.create_index('ix_episode_published_at', 'episode', ['published_at'])

    with op.batch_alter_table('post_comment') as batch:
        batch.add_column(sa.Column('episode_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_post_comment_episode_id_episode', 'episode', ['episode_id'],
            ['id'], ondelete='CASCADE')
        batch.create_index('ix_post_comment_episode_id', ['episode_id'])
        batch.drop_constraint('ck_post_comment_target', type_='check')
        batch.create_check_constraint(
            'ck_post_comment_target',
            '(post_id IS NOT NULL) + (page_id IS NOT NULL) '
            '+ (episode_id IS NOT NULL) = 1')


def downgrade():
    # Episode comments have nowhere to live in the old schema.
    op.execute('DELETE FROM post_comment WHERE episode_id IS NOT NULL')
    with op.batch_alter_table('post_comment') as batch:
        batch.drop_constraint('ck_post_comment_target', type_='check')
        batch.create_check_constraint(
            'ck_post_comment_target',
            '(post_id IS NOT NULL) <> (page_id IS NOT NULL)')
        # MySQL will not drop an index a foreign key still relies on.
        batch.drop_constraint(
            'fk_post_comment_episode_id_episode', type_='foreignkey')
        batch.drop_index('ix_post_comment_episode_id')
        batch.drop_column('episode_id')
    op.drop_index('ix_episode_published_at', table_name='episode')
    op.drop_table('episode')
    op.drop_table('podcast_show')
