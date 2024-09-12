"""back

Revision ID: 7f170b65b8fb
Revises: 59ab55d254a3
Create Date: 2024-09-11 20:52:19.067491

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '7f170b65b8fb'
down_revision = '59ab55d254a3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.drop_column('category')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', mysql.VARCHAR(length=128), nullable=True))

    # ### end Alembic commands ###
