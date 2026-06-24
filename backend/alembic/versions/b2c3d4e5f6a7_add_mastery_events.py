"""add mastery events and new mastery fields

新增掌握度事件表和 UserMastery 新字段：
- mastery_events: 逐题逐知识点的掌握度变更记录
- user_mastery.last_success_at: 最后一次答对时间
- user_mastery.last_reviewed_at: 最后一次复习时间
- user_mastery.mastered_at: 首次达到 mastered 的时间

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # ---- mastery_events 表 ----
    op.create_table(
        'mastery_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('mastery_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_mastery.id', ondelete='CASCADE'), nullable=False),
        sa.Column('knowledge_point_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=False),
        sa.Column('answer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('test_answers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('delta', sa.Float(), server_default='0.0'),
        sa.Column('score_before', sa.Float(), nullable=True),
        sa.Column('score_after', sa.Float(), nullable=True),
        sa.Column('status_before', sa.String(20), nullable=True),
        sa.Column('status_after', sa.String(20), nullable=True),
        sa.Column('error_category', sa.String(50), nullable=True),
        sa.Column('error_pattern_id', sa.String(100), nullable=True),
        sa.Column('metadata', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_mastery_events_user_kp', 'mastery_events', ['user_id', 'knowledge_point_id'])
    op.create_index('ix_mastery_events_mastery_id', 'mastery_events', ['mastery_id'])
    op.create_index('ix_mastery_events_created_at', 'mastery_events', ['created_at'])

    # ---- user_mastery 新增字段 ----
    op.add_column('user_mastery', sa.Column('last_success_at', sa.DateTime(), nullable=True))
    op.add_column('user_mastery', sa.Column('last_reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('user_mastery', sa.Column('mastered_at', sa.DateTime(), nullable=True))

    # ---- review_tasks 新增字段 ----
    op.add_column('review_tasks', sa.Column('target', postgresql.JSON(), nullable=True))
    op.add_column('review_tasks', sa.Column('next_action', postgresql.JSON(), nullable=True))


def downgrade():
    # ---- 删除 review_tasks 新增字段 ----
    op.drop_column('review_tasks', 'next_action')
    op.drop_column('review_tasks', 'target')

    # ---- 删除 user_mastery 新增字段 ----
    op.drop_column('user_mastery', 'mastered_at')
    op.drop_column('user_mastery', 'last_reviewed_at')
    op.drop_column('user_mastery', 'last_success_at')

    # ---- 删除表 ----
    op.drop_index('ix_mastery_events_created_at', table_name='mastery_events')
    op.drop_index('ix_mastery_events_mastery_id', table_name='mastery_events')
    op.drop_index('ix_mastery_events_user_kp', table_name='mastery_events')
    op.drop_table('mastery_events')
