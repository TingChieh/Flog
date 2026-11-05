"""Add a rebuildable SQLite search index without changing existing tables.

Revision ID: b5e1a7c9d234
Revises: a8c2d4e6f901
"""
from alembic import op
import sqlalchemy as sa
from app.search_index import rebuild_search_index

revision = 'b5e1a7c9d234'
down_revision = 'a8c2d4e6f901'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != 'sqlite':
        return
    # Never take ownership of or alter a pre-existing object with one of our names.
    collision = connection.execute(sa.text(
        "SELECT 1 FROM sqlite_master WHERE lower(name) IN "
        "('post_search', 'post_search_insert', 'post_search_update', "
        "'post_search_delete') LIMIT 1"
    )).first()
    if not collision:
        rebuild_search_index(connection)


def downgrade():
    # Leave the disposable index in place: its name might predate this migration,
    # and dropping it could destroy data owned by another application.
    pass
