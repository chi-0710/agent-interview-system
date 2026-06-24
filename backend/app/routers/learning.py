"""学习状态路由 - 掌握度、复习任务、知识点体系

提供用户学习状态查询和管理的 API：
- GET  /api/learning/mastery          获取用户掌握度列表
- GET  /api/learning/mastery/{kp_id}  获取单个知识点掌握详情
- GET  /api/learning/weak-points      获取薄弱知识点
- GET  /api/learning/review-tasks     获取复习任务列表
- POST /api/learning/review-tasks/{task_id}/complete  标记复习任务完成
- GET  /api/learning/knowledge-tree   获取知识点树
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import async_session_factory
from app.models import KnowledgePoint
from app.services.mastery import get_mastery_service
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])

USER_ID = "default_user"


# ---- 掌握度相关 ----

@router.get("/mastery")
async def get_user_mastery(
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> list:
    """获取用户所有知识点的掌握情况

    Args:
        category: 按学科分类筛选（如 "计算机基础"、"前端"）
        status: 按状态筛选（unknown/learning/unstable/mastered/forgotten）
    """
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            result = await mastery_service.get_user_mastery_list(
                db=session,
                user_id=USER_ID,
                category=category,
                status=status,
            )
            return result
    except Exception as e:
        logger.error(f"[learning/mastery] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取掌握度失败")


@router.get("/mastery/{kp_id}")
async def get_mastery_detail(kp_id: str) -> dict:
    """获取单个知识点的掌握详情"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            mastery = await mastery_service.get_or_create_mastery(
                db=session,
                user_id=USER_ID,
                knowledge_point_id=kp_id,
            )

            # 加载知识点信息
            kp_result = await session.execute(
                select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
            )
            kp = kp_result.scalar_one_or_none()

            return {
                "kp_id": kp_id,
                "kp_name": kp.name if kp else None,
                "kp_path": kp.path if kp else None,
                "importance": kp.importance if kp else None,
                "status": mastery.status,
                "mastery_score": round(mastery.mastery_score, 1),
                "streak": mastery.streak,
                "correct_count": mastery.correct_count,
                "wrong_count": mastery.wrong_count,
                "confidence": round(mastery.confidence, 2) if mastery.confidence else 0,
                "review_due_at": mastery.review_due_at.isoformat() if mastery.review_due_at else None,
                "last_practiced_at": mastery.last_practiced_at.isoformat() if mastery.last_practiced_at else None,
            }
    except Exception as e:
        logger.error(f"[learning/mastery/detail] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取掌握详情失败")


@router.get("/weak-points")
async def get_weak_points(
    limit: int = Query(10, ge=1, le=50),
) -> list:
    """获取用户最薄弱的知识点列表"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            result = await mastery_service.get_weak_points(
                db=session,
                user_id=USER_ID,
                limit=limit,
            )
            return result
    except Exception as e:
        logger.error(f"[learning/weak-points] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取薄弱知识点失败")


# ---- 复习任务相关 ----

@router.get("/review-tasks")
async def get_review_tasks(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> list:
    """获取用户的复习任务列表

    Args:
        status: 按状态筛选（pending/in_progress/completed/skipped）
        limit: 返回数量限制
    """
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            tasks = await mastery_service.get_review_tasks(
                db=session,
                user_id=USER_ID,
                status=status,
                limit=limit,
            )
            return tasks
    except Exception as e:
        logger.error(f"[learning/review-tasks] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取复习任务失败")


@router.post("/review-tasks/{task_id}/complete")
async def complete_review_task(task_id: str) -> dict:
    """标记复习任务为已完成"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            result = await mastery_service.complete_review_task(
                db=session,
                user_id=USER_ID,
                task_id=task_id,
            )
            if not result:
                raise HTTPException(status_code=404, detail="复习任务不存在")
            await session.commit()
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/complete-review-task] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="完成复习任务失败")


# ---- 知识点体系相关 ----

@router.get("/knowledge-tree")
async def get_knowledge_tree(
    category: Optional[str] = None,
) -> list:
    """获取知识点树（层级结构）

    Args:
        category: 按分类筛选（如 "计算机基础"、"前端"）
    """
    try:
        async with async_session_factory() as session:
            query = select(KnowledgePoint).order_by(
                KnowledgePoint.level.asc(),
                KnowledgePoint.path.asc(),
            )
            if category:
                query = query.where(KnowledgePoint.category == category)

            result = await session.execute(query)
            kps = result.scalars().all()

            # 构建树形结构
            kp_map = {}
            roots = []

            for kp in kps:
                kp_data = {
                    "id": str(kp.id),
                    "name": kp.name,
                    "level": kp.level,
                    "path": kp.path,
                    "description": kp.description,
                    "importance": kp.importance,
                    "category": kp.category,
                    "children": [],
                }
                kp_map[str(kp.id)] = kp_data

                if not kp.parent_id:
                    roots.append(kp_data)
                else:
                    parent_id = str(kp.parent_id)
                    if parent_id in kp_map:
                        kp_map[parent_id]["children"].append(kp_data)

            return roots
    except Exception as e:
        logger.error(f"[learning/knowledge-tree] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取知识点树失败")


@router.get("/knowledge-points/{kp_id}")
async def get_knowledge_point_detail(kp_id: str) -> dict:
    """获取单个知识点的详细信息，包括关联的题目和资料"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
            )
            kp = result.scalar_one_or_none()

            if not kp:
                raise HTTPException(status_code=404, detail="知识点不存在")

            # 加载关联题目数量
            question_count = len(kp.question_links) if kp.question_links else 0

            # 加载关联资料片段数量
            chunk_count = len(kp.chunk_links) if kp.chunk_links else 0

            return {
                "id": str(kp.id),
                "name": kp.name,
                "level": kp.level,
                "path": kp.path,
                "description": kp.description,
                "importance": kp.importance,
                "category": kp.category,
                "parent_id": str(kp.parent_id) if kp.parent_id else None,
                "question_count": question_count,
                "chunk_count": chunk_count,
                "created_at": kp.created_at.isoformat() if kp.created_at else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/knowledge-point-detail] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取知识点详情失败")
