"""Add email notifications flag to User model

Revision ID: b3f8a1c9d2e4
Revises: 7d2c5346c599
Create Date: 2026-07-05 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f8a1c9d2e4'
down_revision = '7d2c5346c599'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_notifications', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_notifications')
