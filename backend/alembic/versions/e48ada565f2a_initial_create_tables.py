"""initial create tables

Revision ID: e48ada565f2a
Revises:
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'e48ada565f2a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # documents 表
    op.create_table(
        'documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # questions 表
    op.create_table(
        'questions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('expected_answer', sa.Text, nullable=True),
        sa.Column('difficulty', sa.String(20), nullable=True, server_default='medium'),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('type', sa.String(20), nullable=True, server_default='text'),
        sa.Column('options', sa.JSON, nullable=True),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('sections', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # test_sessions 表
    op.create_table(
        'test_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False, server_default='Untitled Session'),
        sa.Column('total_questions', sa.Integer, nullable=True, server_default='0'),
        sa.Column('completed_questions', sa.Integer, nullable=True, server_default='0'),
        sa.Column('score', sa.Float, nullable=True),
        sa.Column('status', sa.String(20), nullable=True, server_default='in_progress'),
        sa.Column('settings', sa.JSON, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )

    # test_answers 表
    op.create_table(
        'test_answers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('test_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('answer_text', sa.Text, nullable=True),
        sa.Column('is_correct', sa.Boolean, nullable=True),
        sa.Column('score', sa.Float, nullable=True),
        sa.Column('error_type', sa.String(50), nullable=True),
        sa.Column('feedback', sa.Text, nullable=True),
        sa.Column('error_tags', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('test_answers')
    op.drop_table('test_sessions')
    op.drop_table('questions')
    op.drop_table('documents')
