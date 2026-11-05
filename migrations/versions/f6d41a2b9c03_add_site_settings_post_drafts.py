"""add site settings and post drafts

Revision ID: f6d41a2b9c03
Revises: d4a7c9e20f13
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6d41a2b9c03'
down_revision = 'd4a7c9e20f13'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('post', sa.Column(
        'is_published', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute(sa.text('UPDATE post SET is_published = true'))

    op.create_table(
        'site_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('registration_open', sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column('post_revision_limit', sa.Integer(), nullable=False,
                  server_default=sa.text('20')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(
        sa.table(
            'site_settings', sa.column('id'), sa.column('registration_open'),
            sa.column('post_revision_limit')),
        [{'id': 1, 'registration_open': True, 'post_revision_limit': 20}],
    )

    op.create_table(
        'post_draft',
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(length=5), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['category.id']),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('post_id'),
    )

    op.create_table(
        'post_revision',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(length=5), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['category.id']),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_post_revision_post_id', 'post_revision', ['post_id'])
    op.create_index('ix_post_revision_created_at', 'post_revision',
                    ['created_at'])


def downgrade():
    op.drop_index('ix_post_revision_created_at', table_name='post_revision')
    # MySQL requires this index for the foreign key until the table is dropped.
    if op.get_bind().dialect.name not in ('mysql', 'mariadb'):
        op.drop_index('ix_post_revision_post_id', table_name='post_revision')
    op.drop_table('post_revision')
    op.drop_table('post_draft')
    op.drop_table('site_settings')
    op.drop_column('post', 'is_published')
