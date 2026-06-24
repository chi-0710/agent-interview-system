"""add knowledge system tables

Revision ID: a1b2c3d4e5f6
Revises: e48ada565f2a
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e48ada565f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 新增字段到已有表 ===

    # questions 表新增字段
    op.add_column('questions', sa.Column('rubric', sa.JSON, nullable=True))
    op.add_column('questions', sa.Column('common_mistakes', sa.JSON, nullable=True))
    op.add_column('questions', sa.Column('follow_up_questions', sa.JSON, nullable=True))
    op.add_column('questions', sa.Column('status', sa.String(20), nullable=True, server_default='active'))
    op.add_column('questions', sa.Column('updated_at', sa.DateTime, nullable=True))

    # test_sessions 表新增 mode 字段
    op.add_column('test_sessions', sa.Column('mode', sa.String(30), nullable=True, server_default='learn'))

    # test_answers 表新增 time_spent 字段
    op.add_column('test_answers', sa.Column('time_spent', sa.Integer, nullable=True))

    # === 新增表 ===

    # document_chunks
    op.create_table(
        'document_chunks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('headers', sa.JSON, nullable=True),
        sa.Column('section_path', sa.String(1000), nullable=True),
        sa.Column('start_line', sa.Integer, nullable=True),
        sa.Column('end_line', sa.Integer, nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # knowledge_points
    op.create_table(
        'knowledge_points',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='SET NULL'), nullable=True),
        sa.Column('level', sa.Integer, nullable=True, server_default='1'),
        sa.Column('path', sa.String(1000), nullable=True),
        sa.Column('importance', sa.Integer, nullable=True, server_default='5'),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # knowledge_relations
    op.create_table(
        'knowledge_relations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relation_type', sa.String(30), nullable=False),
        sa.Column('strength', sa.Float, nullable=True, server_default='1.0'),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('source_id', 'target_id', 'relation_type', name='uq_kp_relation'),
    )

    # chunk_knowledge_links
    op.create_table(
        'chunk_knowledge_links',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('chunk_id', UUID(as_uuid=True), sa.ForeignKey('document_chunks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('knowledge_point_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relevance', sa.Float, nullable=True, server_default='1.0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('chunk_id', 'knowledge_point_id', name='uq_chunk_kp'),
    )

    # question_knowledge_links
    op.create_table(
        'question_knowledge_links',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('knowledge_point_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(30), nullable=True, server_default='primary'),
        sa.Column('weight', sa.Float, nullable=True, server_default='1.0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('question_id', 'knowledge_point_id', name='uq_question_kp'),
    )

    # diagnoses
    op.create_table(
        'diagnoses',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('answer_id', UUID(as_uuid=True), sa.ForeignKey('test_answers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('error_category', sa.String(50), nullable=True),
        sa.Column('error_conclusion', sa.Text, nullable=True),
        sa.Column('knowledge_point_ids', sa.JSON, nullable=True),
        sa.Column('evidence_chunk_ids', sa.JSON, nullable=True),
        sa.Column('mastery_delta', sa.JSON, nullable=True),
        sa.Column('review_suggestions', sa.JSON, nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # user_mastery
    op.create_table(
        'user_mastery',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('knowledge_point_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=True, server_default='unknown'),
        sa.Column('mastery_score', sa.Float, nullable=True, server_default='0.0'),
        sa.Column('wrong_count', sa.Integer, nullable=True, server_default='0'),
        sa.Column('correct_count', sa.Integer, nullable=True, server_default='0'),
        sa.Column('recent_accuracy', sa.Float, nullable=True),
        sa.Column('last_practiced_at', sa.DateTime, nullable=True),
        sa.Column('confidence', sa.Float, nullable=True, server_default='0.0'),
        sa.Column('review_due_at', sa.DateTime, nullable=True),
        sa.Column('streak', sa.Integer, nullable=True, server_default='0'),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'knowledge_point_id', name='uq_user_kp_mastery'),
    )

    # review_tasks
    op.create_table(
        'review_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('knowledge_point_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=True),
        sa.Column('task_type', sa.String(30), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('action', sa.JSON, nullable=True),
        sa.Column('priority', sa.Integer, nullable=True, server_default='5'),
        sa.Column('status', sa.String(20), nullable=True, server_default='pending'),
        sa.Column('due_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('source_diagnosis_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    # 按创建逆序删除
    op.drop_table('review_tasks')
    op.drop_table('user_mastery')
    op.drop_table('diagnoses')
    op.drop_table('question_knowledge_links')
    op.drop_table('chunk_knowledge_links')
    op.drop_table('knowledge_relations')
    op.drop_table('knowledge_points')
    op.drop_table('document_chunks')

    # 删除新增的列
    op.drop_column('test_answers', 'time_spent')
    op.drop_column('test_sessions', 'mode')
    op.drop_column('questions', 'updated_at')
    op.drop_column('questions', 'status')
    op.drop_column('questions', 'follow_up_questions')
    op.drop_column('questions', 'common_mistakes')
    op.drop_column('questions', 'rubric')
