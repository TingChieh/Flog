"""add persisted user roles

Revision ID: 8b7d1e2f3a4c
Revises: 5c1f31ac842e
Create Date: 2026-08-20 00:00:00
"""
import logging
import os

from alembic import op
import sqlalchemy as sa


revision = '8b7d1e2f3a4c'
down_revision = '5c1f31ac842e'
branch_labels = None
depends_on = None

ROLE_USER = 'user'
ROLE_ADMIN = 'admin'


def configured_admin_emails(value):
    return {item.strip().lower() for item in (value or '').split(',')
            if item.strip()}


def require_admin_match(configured, existing):
    matches = configured & {email.lower() for email in existing}
    if not matches:
        raise RuntimeError(
            'Role migration stopped: ADMIN_EMAILS must contain an existing user email.'
        )
    return matches


def upgrade():
    connection = op.get_bind()
    configured = configured_admin_emails(os.environ.get('ADMIN_EMAILS'))
    existing = connection.execute(sa.text('SELECT email FROM user')).scalars().all()
    if existing:
        matches = require_admin_match(configured, existing)
    else:
        logging.getLogger('alembic').warning(
            'No users exist, so no admin role can be assigned. '
            'Assign roles via ADMIN_EMAILS after users are created.'
        )
        matches = set()

    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column(
            'role', sa.String(length=16), nullable=True,
            server_default=sa.text("'user'")))

    users = sa.table('user', sa.column('email'), sa.column('role'))
    op.execute(users.update().where(
        sa.func.lower(users.c.email).in_(matches)
    ).values(role=ROLE_ADMIN))

    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column(
            'role', existing_type=sa.String(length=16), nullable=False,
            server_default=sa.text("'user'"))
        batch_op.create_check_constraint(
            'ck_user_role', "role IN ('user', 'admin')")


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_constraint('ck_user_role', type_='check')
        batch_op.drop_column('role')
