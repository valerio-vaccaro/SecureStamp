"""Add API token permissions

Revision ID: f2a4c2b8d1aa
Revises: d4a7b6c3e9f1
Create Date: 2026-07-05 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a4c2b8d1aa'
down_revision = 'd4a7b6c3e9f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_list_files', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('can_upload_files', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('can_download_files', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('can_download_timestamps', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('can_download_signatures', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('can_manage_symbols', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_column('can_manage_symbols')
        batch_op.drop_column('can_download_signatures')
        batch_op.drop_column('can_download_timestamps')
        batch_op.drop_column('can_download_files')
        batch_op.drop_column('can_upload_files')
        batch_op.drop_column('can_list_files')
