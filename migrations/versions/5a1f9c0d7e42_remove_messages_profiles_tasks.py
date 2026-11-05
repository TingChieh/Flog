"""remove private messages, notifications and background tasks

Upgrade permanently drops the message, notification and task tables with all
their rows. Downgrade recreates them empty; deleted rows are unrecoverable.

Revision ID: 5a1f9c0d7e42
Revises: bad2dd157a5f
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = '5a1f9c0d7e42'
down_revision = 'bad2dd157a5f'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')
DROPPED_TABLES = ('message', 'notification', 'task')


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    for name in DROPPED_TABLES:
        if name not in tables:
            continue
        rows = connection.execute(sa.select(sa.func.count()).select_from(
            sa.table(name))).scalar_one()
        log.info('Dropping table %s (%s rows)', name, rows)
        op.drop_table(name)


def downgrade():
    op.create_table(
        'message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('recipient_id', sa.Integer(), nullable=False),
        sa.Column('body', sa.String(length=140), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sender_id'], ['user.id']),
        sa.ForeignKeyConstraint(['recipient_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_message_sender_id', 'message', ['sender_id'])
    op.create_index('ix_message_recipient_id', 'message', ['recipient_id'])
    op.create_index('ix_message_timestamp', 'message', ['timestamp'])
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_name', 'notification', ['name'])
    op.create_index('ix_notification_user_id', 'notification', ['user_id'])
    op.create_index('ix_notification_timestamp', 'notification', ['timestamp'])
    op.create_table(
        'task',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=128), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_name', 'task', ['name'])
