"""add correct_option and option_explanations to questions

为选择题支持新增两个字段：
- correct_option: 正确答案索引 (0=A, 1=B, 2=C, 3=D)
- option_explanations: 每个选项的解释数组

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-27 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = (
    'f6a7b8c9d0e1',
    'e2f3a4b5c6d7',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('questions', sa.Column('correct_option', sa.Integer(), nullable=True))
    op.add_column('questions', sa.Column('option_explanations', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('questions', 'option_explanations')
    op.drop_column('questions', 'correct_option')
