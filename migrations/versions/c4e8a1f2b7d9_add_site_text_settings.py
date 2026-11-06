"""add editable site wording to site settings

Revision ID: c4e8a1f2b7d9
Revises: b7d3f9a15c26
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e8a1f2b7d9'
down_revision = 'b7d3f9a15c26'
branch_labels = None
depends_on = None

COLUMNS = (
    ('site_name', 60),
    ('home_tab_title', 120),
    ('home_heading', 60),
    ('nav_home_label', 20),
    ('nav_archive_label', 20),
    ('nav_categories_label', 20),
)


def upgrade():
    for name, length in COLUMNS:
        op.add_column('site_settings', sa.Column(
            name, sa.String(length=length), nullable=True))


def downgrade():
    for name, _length in reversed(COLUMNS):
        op.drop_column('site_settings', name)
