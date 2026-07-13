"""Add confirmed_at to files

Revision ID: 6a9f5d21c4e7
Revises: 3c8d4a9b2f10
Create Date: 2026-07-13 11:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a9f5d21c4e7'
down_revision = '3c8d4a9b2f10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_column('confirmed_at')
