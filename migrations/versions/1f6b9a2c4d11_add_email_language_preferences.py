"""Add email language preferences

Revision ID: 1f6b9a2c4d11
Revises: a1c4d8e7f9b2
Create Date: 2026-07-10 14:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f6b9a2c4d11'
down_revision = 'a1c4d8e7f9b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'email_notification_language',
                sa.String(length=8),
                nullable=False,
                server_default='en',
            )
        )

    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'notification_email_language',
                sa.String(length=8),
                nullable=True,
            )
        )


def downgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_column('notification_email_language')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_notification_language')
