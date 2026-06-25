"""merge study plan and knowledge base heads

合并两个分叉的迁移分支：
- c3d4e5f6a7b8 (add_study_plan)
- d4e5f6a7b8c9 (add_knowledge_base)

两者都以 b2c3d4e5f6a7 为父版本，导致 alembic upgrade head 报多 head 歧义。
本迁移不含任何 DDL，仅负责把版本图收束为单一 head。

Revision ID: f6a7b8c9d0e1
Revises: c3d4e5f6a7b8, d4e5f6a7b8c9
Create Date: 2026-06-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = (
    'c3d4e5f6a7b8',
    'd4e5f6a7b8c9',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 两个分支中的建表、加字段操作已经分别存在。
    # 此迁移只负责把版本图收束为一个 head，不执行任何 DDL。
    pass


def downgrade() -> None:
    # 降级时只回到两个分支 head，不删除业务表。
    pass
