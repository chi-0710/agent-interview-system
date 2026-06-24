"""学习规划与自适应出题路由

- POST /api/learning/next-session  → 生成下一个练习会话
- GET  /api/learning/sessions       → 练习会话列表
- GET  /api/learning/plans          → 学习计划列表
- POST /api/learning/plans          → 创建学习计划
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.database import async_session_factory
from app.services.learning import get_learning_service

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
