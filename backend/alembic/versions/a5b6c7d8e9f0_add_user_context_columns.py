"""add user context columns

给 test_sessions 增加 user_id，给 documents 增加 owner_id，
为多用户隔离做准备。现有数据默认填充 'default_user'。

Revision ID: a5b6c7d8e9f0
Revises: f6a7b8c9d0e1
Create Date: 2026-06-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # test_sessions.user_id
    op.add_column(
        'test_sessions',
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
    )
    op.create_index('ix_test_sessions_user_id', 'test_sessions', ['user_id'])

    # documents.owner_id
    op.add_column(
        'documents',
        sa.Column('owner_id', sa.String(100), nullable=False, server_default='default_user'),
    )
    op.create_index('ix_documents_owner_id', 'documents', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_documents_owner_id', table_name='documents')
    op.drop_column('documents', 'owner_id')

    op.drop_index('ix_test_sessions_user_id', table_name='test_sessions')
    op.drop_column('test_sessions', 'user_id')
