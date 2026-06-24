"""add study plan and adaptive learning tables

新增学习规划与自适应出题相关表：
- study_plans: 学习计划
- practice_sessions: 练习会话
- practice_session_questions: 会话题目关联

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # ---- study_plans 表 ----
    op.create_table(
        'study_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('config', postgresql.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_study_plans_user_id', 'study_plans', ['user_id'])

    # ---- practice_sessions 表 ----
    op.create_table(
        'practice_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('study_plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('mode', sa.String(30), server_default='adaptive'),
        sa.Column('status', sa.String(20), server_default='in_progress'),
        sa.Column('question_count', sa.Integer(), server_default='5'),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_practice_sessions_user_id', 'practice_sessions', ['user_id'])
    op.create_index('ix_practice_sessions_status', 'practice_sessions', ['status'])

    # ---- practice_session_questions 表 ----
    op.create_table(
        'practice_session_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('practice_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sequence', sa.Integer(), server_default='0'),
        sa.Column('selected_reason', sa.String(50), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('answered_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_psq_session_id', 'practice_session_questions', ['session_id'])
    op.create_index('ix_psq_question_id', 'practice_session_questions', ['question_id'])


def downgrade():
    op.drop_index('ix_psq_question_id', table_name='practice_session_questions')
    op.drop_index('ix_psq_session_id', table_name='practice_session_questions')
    op.drop_table('practice_session_questions')

    op.drop_index('ix_practice_sessions_status', table_name='practice_sessions')
    op.drop_index('ix_practice_sessions_user_id', table_name='practice_sessions')
    op.drop_table('practice_sessions')

    op.drop_index('ix_study_plans_user_id', table_name='study_plans')
    op.drop_table('study_plans')
