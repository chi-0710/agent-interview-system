"""add submission idempotency fields to test_sessions

为 TestSession 增加幂等提交支持:
- client_submission_id: 前端生成的幂等键
- request_hash: 完整请求哈希,用于 409 冲突检测
- evaluation_snapshot: 即时评判快照,用于幂等回放
- learning_record_snapshot: 学习档案快照,用于幂等回放

并增加 partial unique index (user_id, client_submission_id) WHERE client_submission_id IS NOT NULL,
兼容历史数据(NULL 允许多行),仅对显式携带幂等键的提交去重。

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('test_sessions', sa.Column('client_submission_id', sa.String(64), nullable=True))
    op.add_column('test_sessions', sa.Column('request_hash', sa.String(64), nullable=True))
    op.add_column('test_sessions', sa.Column('evaluation_snapshot', sa.JSON(), nullable=True))
    op.add_column('test_sessions', sa.Column('learning_record_snapshot', sa.JSON(), nullable=True))
    op.create_index(
        'ix_test_sessions_client_submission_id',
        'test_sessions',
        ['client_submission_id'],
    )
    # Partial unique index: NULL 允许多行(兼容历史数据),仅对显式携带幂等键的提交去重
    op.execute(
        "CREATE UNIQUE INDEX uq_test_session_user_submission "
        "ON test_sessions (user_id, client_submission_id) "
        "WHERE client_submission_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_test_session_user_submission")
    op.drop_index('ix_test_sessions_client_submission_id', table_name='test_sessions')
    op.drop_column('test_sessions', 'client_submission_id')
    op.drop_column('test_sessions', 'request_hash')
    op.drop_column('test_sessions', 'evaluation_snapshot')
    op.drop_column('test_sessions', 'learning_record_snapshot')
