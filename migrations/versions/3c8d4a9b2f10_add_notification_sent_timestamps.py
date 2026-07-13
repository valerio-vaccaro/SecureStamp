"""Add notification sent timestamps to files

Revision ID: 3c8d4a9b2f10
Revises: 1f6b9a2c4d11
Create Date: 2026-07-13 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c8d4a9b2f10'
down_revision = '1f6b9a2c4d11'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('primary_notification_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('secondary_notification_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_column('secondary_notification_sent_at')
        batch_op.drop_column('primary_notification_sent_at')
