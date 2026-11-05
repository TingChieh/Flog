"""add content body formats"""
from alembic import op
import sqlalchemy as sa


revision = 'b1d4e6f70819'
down_revision = '9c8e2f3a4b5d'
branch_labels = None
depends_on = None


def upgrade():
    for table_name in ('post', 'page'):
        op.add_column(table_name, sa.Column(
            'body_format', sa.String(length=20), nullable=False,
            server_default=sa.text("'html'")))


def downgrade():
    connection = op.get_bind()
    unsafe_rows = {}
    for table_name in ('post', 'page'):
        body_format = sa.column('body_format')
        table = sa.table(table_name, body_format)
        count = connection.scalar(
            sa.select(sa.func.count()).select_from(table).where(sa.or_(
                body_format.is_(None),
                sa.cast(body_format, sa.LargeBinary()) != b'html',
            ))
        )
        if count:
            unsafe_rows[table_name] = count

    if unsafe_rows:
        details = ', '.join(
            f'{table_name}={count}'
            for table_name, count in unsafe_rows.items()
        )
        raise RuntimeError(
            'Cannot downgrade content body formats while null or non-html '
            f'rows exist ({details})'
        )

    op.drop_column('page', 'body_format')
    op.drop_column('post', 'body_format')
