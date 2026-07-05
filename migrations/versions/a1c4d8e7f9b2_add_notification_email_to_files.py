"""Add notification email to files

Revision ID: a1c4d8e7f9b2
Revises: f2a4c2b8d1aa
Create Date: 2026-07-05 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4d8e7f9b2'
down_revision = 'f2a4c2b8d1aa'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notification_email', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_column('notification_email')
