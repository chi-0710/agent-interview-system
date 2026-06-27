"""学习规划与自适应出题路由

- POST /api/learning/next-session                     → 生成下一个练习会话
- GET  /api/learning/sessions                          → 练习会话列表
- GET  /api/learning/plans                             → 学习计划列表
- POST /api/learning/plans                             → 创建学习计划
- GET  /api/learning/plans/{id}                        → 计划详情 + 进度
- POST /api/learning/plans/{id}/next-session           → 为计划生成下一次练习
- PUT  /api/learning/plans/{id}                        → 修改计划配置
- POST /api/learning/plans/{id}/pause                  → 暂停计划
- POST /api/learning/plans/{id}/resume                 → 恢复计划
- POST /api/learning/plans/{id}/complete               → 完成/归档计划
- DELETE /api/learning/plans/{id}                      → 删除计划
- GET  /api/learning/mastery                           → 用户掌握度列表
- GET  /api/learning/review-tasks                      → 复习任务列表
- GET  /api/learning/weak-points                       → 薄弱知识点列表
- POST /api/learning/review-tasks/{id}/complete        → 完成复习任务
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from app.database import async_session_factory
from app.dependencies import CurrentUser, get_current_user
from app.services.learning import get_learning_service
from app.services.mastery import get_mastery_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/learning", tags=["learning"])


# ---- 请求模型 ----

class NextSessionRequest(BaseModel):
    mode: str = "adaptive"  # adaptive | review | explore
    count: int = 5
    kp_ids: Optional[List[str]] = None


class CreatePlanRequest(BaseModel):
    name: str
    objective: str
    source_type: str  # knowledge_base | document
    source_id: str
    target_proficiency: str  # acquainted | familiar | proficient | expert
    selected_kp_ids: Optional[List[str]] = None
    schedule: Optional[dict] = None


class UpdatePlanRequest(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    schedule: Optional[dict] = None
    target_proficiency: Optional[str] = None


# ---- 路由 ----

@router.post("/next-session")
async def generate_next_session(
    req: NextSessionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """生成下一个自适应练习会话"""
    try:
        learning_service = get_learning_service()
        async with async_session_factory() as session:
            result = await learning_service.generate_next_session(
                db=session,
                user_id=current_user.user_id,
                mode=req.mode,
                count=req.count,
                kp_ids=req.kp_ids,
            )
            return result
    except Exception as e:
        logger.error(f"[learning/next-session] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    limit: int = 10,
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取练习会话列表"""
    try:
        from app.models import PracticeSession
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(PracticeSession)
                .where(PracticeSession.user_id == current_user.user_id)
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
async def list_plans(current_user: CurrentUser = Depends(get_current_user)):
    """获取学习计划列表"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(StudyPlan)
                .where(StudyPlan.user_id == current_user.user_id)
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
async def create_plan(
    req: CreatePlanRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """创建学习计划"""
    try:
        learning_service = get_learning_service()
        async with async_session_factory() as session:
            result = await learning_service.create_plan(
                db=session,
                user_id=current_user.user_id,
                name=req.name,
                objective=req.objective,
                source_type=req.source_type,
                source_id=req.source_id,
                target_proficiency=req.target_proficiency,
                selected_kp_ids=req.selected_kp_ids,
                schedule=req.schedule,
            )
            await session.commit()
            return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[learning/plans/create] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取计划详情 + 进度"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        learning_service = get_learning_service()
        async with async_session_factory() as session:
            # 读取计划基本信息
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            # 获取进度
            progress = await learning_service.get_plan_progress(
                db=session,
                plan_id=plan_id,
                user_id=current_user.user_id,
            )

            return {
                "id": str(plan.id),
                "name": plan.name,
                "objective": plan.objective,
                "status": plan.status,
                "config": plan.config,
                "created_at": plan.created_at.isoformat(),
                "started_at": plan.started_at.isoformat() if plan.started_at else None,
                "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
                "progress": progress,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/{plan_id}/next-session")
async def generate_plan_session(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """为学习计划生成下一次练习"""
    try:
        learning_service = get_learning_service()
        async with async_session_factory() as session:
            result = await learning_service.generate_plan_session(
                db=session,
                plan_id=plan_id,
                user_id=current_user.user_id,
            )
            await session.commit()
            return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/next-session] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    req: UpdatePlanRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """修改计划配置"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            # 更新字段
            if req.name is not None:
                plan.name = req.name
            if req.objective is not None:
                plan.objective = req.objective
            if req.schedule is not None:
                config = plan.config or {}
                config["schedule"] = req.schedule
                plan.config = config
            if req.target_proficiency is not None:
                from app.services.learning import PROFICIENCY_LEVELS
                if req.target_proficiency not in PROFICIENCY_LEVELS:
                    raise HTTPException(status_code=400, detail=f"无效的目标熟练度等级: {req.target_proficiency}")
                config = plan.config or {}
                config["target_proficiency"] = req.target_proficiency
                config["target_score_threshold"] = PROFICIENCY_LEVELS[req.target_proficiency]["score_threshold"]
                plan.config = config

            await session.commit()

            return {
                "id": str(plan.id),
                "name": plan.name,
                "objective": plan.objective,
                "status": plan.status,
                "config": plan.config,
                "updated_at": plan.updated_at.isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/update] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/{plan_id}/pause")
async def pause_plan(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """暂停学习计划"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            if plan.status != "active":
                raise HTTPException(status_code=400, detail=f"计划状态为 {plan.status}，无法暂停")

            plan.status = "paused"
            await session.commit()

            return {"id": str(plan.id), "status": "paused", "message": "计划已暂停"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/pause] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/{plan_id}/resume")
async def resume_plan(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """恢复学习计划"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            if plan.status != "paused":
                raise HTTPException(status_code=400, detail=f"计划状态为 {plan.status}，无法恢复")

            plan.status = "active"
            await session.commit()

            return {"id": str(plan.id), "status": "active", "message": "计划已恢复"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/resume] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plans/{plan_id}/complete")
async def complete_plan(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """完成/归档学习计划"""
    try:
        from datetime import datetime
        from app.models import StudyPlan
        from sqlalchemy import select

        async with async_session_factory() as session:
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            plan.status = "completed"
            plan.completed_at = datetime.utcnow()
            await session.commit()

            # 获取最终进度
            learning_service = get_learning_service()
            async with async_session_factory() as session2:
                progress = await learning_service.get_plan_progress(
                    db=session2,
                    plan_id=plan_id,
                    user_id=current_user.user_id,
                )

            return {
                "id": str(plan.id),
                "status": "completed",
                "completed_at": plan.completed_at.isoformat(),
                "final_progress": progress,
                "message": "计划已完成",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/complete] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """删除学习计划"""
    try:
        from app.models import StudyPlan
        from sqlalchemy import select, delete

        async with async_session_factory() as session:
            plan_result = await session.execute(
                select(StudyPlan).where(
                    StudyPlan.id == plan_id,
                    StudyPlan.user_id == current_user.user_id,
                )
            )
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail="计划不存在")

            await session.execute(
                delete(StudyPlan).where(StudyPlan.id == plan_id)
            )
            await session.commit()

            return {"id": plan_id, "message": "计划已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[learning/plans/{plan_id}/delete] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---- 学习状态面板 ----

@router.get("/mastery")
async def get_mastery_list(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取用户所有知识点的掌握情况"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_user_mastery_list(
                db=session,
                user_id=current_user.user_id,
                category=category,
                status=status,
            )
            await session.commit()
            return data
    except Exception as e:
        logger.error(f"[learning/mastery] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/review-tasks")
async def get_review_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(20),
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取用户的复习任务列表"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_review_tasks(
                db=session,
                user_id=current_user.user_id,
                status=status,
                limit=limit,
            )
            return data
    except Exception as e:
        logger.error(f"[learning/review-tasks] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weak-points")
async def get_weak_points(
    limit: int = Query(10),
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取用户最薄弱的知识点列表"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            data = await mastery_service.get_weak_points(
                db=session,
                user_id=current_user.user_id,
                limit=limit,
            )
            await session.commit()
            return data
    except Exception as e:
        logger.error(f"[learning/weak-points] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review-tasks/{task_id}/complete")
async def complete_review_task(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """标记复习任务为已完成"""
    try:
        mastery_service = get_mastery_service()
        async with async_session_factory() as session:
            result = await mastery_service.complete_review_task(
                db=session,
                user_id=current_user.user_id,
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
