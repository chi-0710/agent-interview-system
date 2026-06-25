"""add knowledge base and import jobs

新增 knowledge_bases 和 import_jobs 表，
以及 documents 和 knowledge_points 的 knowledge_base_id 外键。

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd4e5f6a7b8c9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'knowledge_bases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSON(), nullable=True),
        sa.Column('owner_id', sa.String(100), nullable=False, server_default='default_user'),
        sa.Column('status', sa.String(30), server_default='draft'),
        sa.Column('document_count', sa.Integer(), server_default='0'),
        sa.Column('chunk_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_knowledge_bases_owner_id', 'knowledge_bases', ['owner_id'])

    op.create_table(
        'import_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(30), server_default='queued'),
        sa.Column('total_files', sa.Integer(), server_default='0'),
        sa.Column('completed_files', sa.Integer(), server_default='0'),
        sa.Column('failed_files', sa.Integer(), server_default='0'),
        sa.Column('current_step', sa.String(50), nullable=True),
        sa.Column('progress_percent', sa.Integer(), server_default='0'),
        sa.Column('file_details', postgresql.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_import_jobs_kb_id', 'import_jobs', ['knowledge_base_id'])

    op.add_column('documents',
                  sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True),
                            sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_documents_kb_id', 'documents', ['knowledge_base_id'])

    op.add_column('knowledge_points',
                  sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=True),
                            sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_knowledge_points_kb_id', 'knowledge_points', ['knowledge_base_id'])


def downgrade():
    op.drop_index('ix_knowledge_points_kb_id', table_name='knowledge_points')
    op.drop_column('knowledge_points', 'knowledge_base_id')

    op.drop_index('ix_documents_kb_id', table_name='documents')
    op.drop_column('documents', 'knowledge_base_id')

    op.drop_index('ix_import_jobs_kb_id', table_name='import_jobs')
    op.drop_table('import_jobs')

    op.drop_index('ix_knowledge_bases_owner_id', table_name='knowledge_bases')
    op.drop_table('knowledge_bases')
