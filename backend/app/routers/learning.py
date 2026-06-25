"""学习规划与自适应出题路由

- POST /api/learning/next-session     → 生成下一个练习会话
- GET  /api/learning/sessions          → 练习会话列表
- GET  /api/learning/plans             → 学习计划列表
- POST /api/learning/plans             → 创建学习计划
- GET  /api/learning/mastery           → 用户掌握度列表
- GET  /api/learning/review-tasks      → 复习任务列表
- GET  /api/learning/weak-points       → 薄弱知识点列表
- POST /api/learning/review-tasks/{id}/complete → 完成复习任务
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.database import async_session_factory
from app.services.learning import get_learning_service
from app.services.mastery import get_mastery_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/learning", tags=["learning"])

USER_ID = "default_user"  # 临时：默认用户


# ---- 请求模型 ----

class NextSessionRequest(BaseModel):
    mode: str = "adaptive"  # adaptive | review | explore
    count: int = 5
    kp_ids: Optional[List[str]] = None


# ---- 路由 ----

@router.post("/next-session")
async def generate_next_session(req: NextSessionRequest):
    """生成下一个自适应练习会话"""
    try:
        learning_service = get_learning_service()
        async with async_session_factory() as session:
            result = await learning_service.generate_next_session(
                db=session,
                user_id=USER_ID,
                mode=req.mode,
                count=req.count,
                kp_ids=req.kp_ids,
            )
            return result
    except Exception as e:
        logger.error(f"[learning/next-session] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(limit: int = 10):
    """获取练习会话列表"""
    try:
        from app.models import PracticeSession
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(PracticeSession)
                .where(PracticeSession.user_id == USER_ID)
                .order_by(PracticeSession.created_at.desc())
                .limit(limit)
            )
            sessions = result.scalars().all()

            return {
                "sessions": [
                    {
                        "id": str(s.id),
                        "mode": s.mode,
                        "status": s.status,
                        "question_count": s.question_count,
                        "score": s.score,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    }
                    for s in sessions
                ]
            }
    except Exception as e:
        logger.error(f"[learning/sessions] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans")
async def list_plans():
    """获取学习计划列表"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(StudyPlan)
                .where(StudyPlan.user_id == USER_ID)
                .order_by(StudyPlan.created_at.desc())
            )
            plans = result.scalars().all()

            return {
                "plans": [
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "objective": p.objective,
                        "status": p.status,
                        "config": p.config,
                        "created_at": p.created_at.isoformat(),
                    }
                    for p in plans
                ]
            }
    except Exception as e:
        logger.error(f"[learning/plans] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans")
async def create_plan():
    """创建学习计划（stub）"""
    return {"message": "学习计划创建功能开发中，先使用 next-session 体验自适应出题"}


# ---- 学习状态面板 ----

@router.get("/mastery")
async def get_mastery_list(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """获取用户所有知识点的掌握情况"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_user_mastery_list(
                db=session,
                user_id=USER_ID,
                category=category,
                status=status,
            )
            return data
    except Exception as e:
        logger.error(f"[learning/mastery] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/review-tasks")
async def get_review_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(20),
):
    """获取用户的复习任务列表"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_review_tasks(
                db=session,
                user_id=USER_ID,
                status=status,
                limit=limit,
            )
            return data
    except Exception as e:
        logger.error(f"[learning/review-tasks] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weak-points")
async def get_weak_points(limit: int = Query(10)):
    """获取用户最薄弱的知识点列表"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_weak_points(
                db=session,
                user_id=USER_ID,
                limit=limit,
            )
            return data
    except Exception as e:
        logger.error(f"[learning/weak-points] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review-tasks/{task_id}/complete")
async def complete_review_task(task_id: str):
    """标记复习任务为已完成"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            result = await mastery_service.complete_review_task(
                db=session,
                user_id=USER_ID,
                task_id=task_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail=f"Review task {task_id} not found")
            await session.commit()
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/review-tasks/complete] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
