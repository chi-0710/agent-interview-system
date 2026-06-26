"""add document source metadata fields

新增 Document 表的来源元数据字段：
- source_type: upload / git_repository / generated
- source_uri: Git 地址、原始路径、网页 URL
- content_hash: SHA-256 内容去重
- source_metadata: JSON，保存 commit SHA、页数、语言等
- parse_status: ready / partial / needs_ocr / failed
- parse_warning: 解析警告文本

Revision ID: e2f3a4b5c6d7
Revises: a5b6c7d8e9f0
Create Date: 2026-06-26 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('source_type', sa.String(30), nullable=False, server_default='upload'),
    )
    op.add_column(
        'documents',
        sa.Column('source_uri', sa.String(2000), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('content_hash', sa.String(64), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('source_metadata', JSON, nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('parse_status', sa.String(30), nullable=False, server_default='ready'),
    )
    op.add_column(
        'documents',
        sa.Column('parse_warning', sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('documents', 'parse_warning')
    op.drop_column('documents', 'parse_status')
    op.drop_column('documents', 'source_metadata')
    op.drop_column('documents', 'content_hash')
    op.drop_column('documents', 'source_uri')
    op.drop_column('documents', 'source_type')