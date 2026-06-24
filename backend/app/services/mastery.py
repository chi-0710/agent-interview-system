"""
MasteryService - 用户掌握度服务

五状态模型：
    unknown      未学习
    learning     正在学习
    unstable     学过但掌握不稳
    mastered     已稳定掌握
    forgotten    曾掌握但出现遗忘

核心规则：
    答对且解释完整 → mastery_score 上升
    答错或遗漏关键点 → mastery_score 下降
    连续多次答对 → 状态变为 mastered
    长时间未练习 → 状态从 mastered 变为 unstable
    同类错误重复出现 → 生成 targeted review task
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserMastery, KnowledgePoint, ReviewTask

logger = logging.getLogger(__name__)

# ============== 状态定义 ==============

MASTERY_STATES = {
    "unknown": {
        "label": "未学习",
        "color": "gray",
        "score_range": (0, 10),
    },
    "learning": {
        "label": "学习中",
        "color": "blue",
        "score_range": (10, 40),
    },
    "unstable": {
        "label": "掌握不稳",
        "color": "yellow",
        "score_range": (40, 70),
    },
    "mastered": {
        "label": "已掌握",
        "color": "green",
        "score_range": (70, 100),
    },
    "forgotten": {
        "label": "已遗忘",
        "color": "orange",
        "score_range": (40, 70),
    },
}

# 状态转换规则
STATE_TRANSITIONS = {
    "unknown": ["learning", "unstable"],
    "learning": ["unknown", "unstable", "mastered"],
    "unstable": ["learning", "mastered", "forgotten"],
    "mastered": ["unstable", "forgotten"],
    "forgotten": ["unstable", "mastered"],
}


# ============== MasteryService ==============

class MasteryService:
    """用户掌握度管理服务"""

    def __init__(self):
        # 连续答对次数阈值：达到此值升为 mastered
        self.mastery_streak_threshold = 3
        # 遗忘天数：mastered 状态下超过此天数未练习 → unstable
        self.forget_days_unstable = 7
        # 遗忘天数：超过此天数 → forgotten
        self.forget_days_forgotten = 14
        # 复习间隔（小时）
        self.review_intervals = {
            "unknown": 24,
            "learning": 24,
            "unstable": 48,
            "mastered": 168,  # 7天
            "forgotten": 24,
        }

    # ---------- 公开接口 ----------

    async def get_or_create_mastery(
        self,
        db: AsyncSession,
        user_id: str,
        knowledge_point_id: str,
    ) -> UserMastery:
        """获取或创建用户对某个知识点的掌握记录"""
        result = await db.execute(
            select(UserMastery).where(
                UserMastery.user_id == user_id,
                UserMastery.knowledge_point_id == knowledge_point_id,
            )
        )
        mastery = result.scalar_one_or_none()

        if not mastery:
            mastery = UserMastery(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
                status="unknown",
                mastery_score=0.0,
                wrong_count=0,
                correct_count=0,
                streak=0,
                confidence=0.0,
            )
            db.add(mastery)
            await db.flush()

        return mastery

    async def apply_mastery_delta(
        self,
        db: AsyncSession,
        user_id: str,
        mastery_delta: Dict[str, float],
        is_correct: bool,
        question_difficulty: str = "medium",
    ) -> Dict[str, dict]:
        """
        应用掌握度变化量，更新用户掌握状态。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            mastery_delta: {kp_id: delta_value} 正值加分，负值扣分
            is_correct: 本次是否答对
            question_difficulty: 题目难度

        Returns:
            {kp_id: {status, mastery_score, streak, ...}} 更新后的掌握度信息
        """
        results = {}
        now = datetime.utcnow()

        for kp_id, delta in mastery_delta.items():
            mastery = await self.get_or_create_mastery(db, user_id, kp_id)

            # 应用分数变化，限制在 0-100
            old_score = mastery.mastery_score or 0.0
            new_score = max(0.0, min(100.0, old_score + delta))
            mastery.mastery_score = new_score

            # 更新计数
            if is_correct:
                mastery.correct_count = (mastery.correct_count or 0) + 1
                mastery.streak = (mastery.streak or 0) + 1
            else:
                mastery.wrong_count = (mastery.wrong_count or 0) + 1
                mastery.streak = 0  # 答错重置连续正确

            # 更新最近正确率（最近10次）
            total = (mastery.correct_count or 0) + (mastery.wrong_count or 0)
            if total > 0:
                mastery.recent_accuracy = (mastery.correct_count or 0) / total

            # 更新最后练习时间
            mastery.last_practiced_at = now

            # 重新计算状态
            old_status = mastery.status
            new_status = self._calculate_status(mastery)
            mastery.status = new_status

            # 计算置信度
            mastery.confidence = self._calculate_confidence(mastery)

            # 计算下次复习时间
            mastery.review_due_at = self._calculate_review_due(mastery)

            # 记录状态变化
            if old_status != new_status:
                logger.info(
                    f"[mastery] user={user_id} kp={kp_id}: "
                    f"{old_status} → {new_status} "
                    f"(score: {old_score:.1f} → {new_score:.1f})"
                )

            results[kp_id] = {
                "id": str(mastery.id),
                "kp_id": kp_id,
                "status": mastery.status,
                "mastery_score": round(mastery.mastery_score, 1),
                "streak": mastery.streak,
                "correct_count": mastery.correct_count,
                "wrong_count": mastery.wrong_count,
                "confidence": round(mastery.confidence, 2),
                "review_due_at": mastery.review_due_at.isoformat() if mastery.review_due_at else None,
                "last_practiced_at": mastery.last_practiced_at.isoformat() if mastery.last_practiced_at else None,
                "status_changed": old_status != new_status,
                "old_status": old_status,
                "delta": delta,
            }

        return results

    async def get_user_mastery_list(
        self,
        db: AsyncSession,
        user_id: str,
        category: str = None,
        status: str = None,
    ) -> List[dict]:
        """获取用户所有知识点的掌握情况"""
        query = select(UserMastery).where(UserMastery.user_id == user_id)

        if status:
            query = query.where(UserMastery.status == status)

        result = await db.execute(query)
        masteries = result.scalars().all()

        # 关联知识点信息
        kp_ids = [str(m.knowledge_point_id) for m in masteries]
        if kp_ids:
            kp_result = await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))
            )
            kp_map = {str(kp.id): kp for kp in kp_result.scalars().all()}
        else:
            kp_map = {}

        output = []
        for m in masteries:
            kp = kp_map.get(str(m.knowledge_point_id))
            if category and kp and kp.category != category:
                continue
            output.append({
                "kp_id": str(m.knowledge_point_id),
                "kp_name": kp.name if kp else None,
                "kp_path": kp.path if kp else None,
                "importance": kp.importance if kp else None,
                "status": m.status,
                "mastery_score": round(m.mastery_score, 1),
                "streak": m.streak,
                "correct_count": m.correct_count,
                "wrong_count": m.wrong_count,
                "confidence": round(m.confidence, 2) if m.confidence else 0,
                "review_due_at": m.review_due_at.isoformat() if m.review_due_at else None,
                "last_practiced_at": m.last_practiced_at.isoformat() if m.last_practiced_at else None,
            })

        # 按掌握度排序，最薄弱的在前
        output.sort(key=lambda x: x["mastery_score"])
        return output

    async def get_weak_points(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 10,
    ) -> List[dict]:
        """获取用户最薄弱的知识点列表"""
        result = await db.execute(
            select(UserMastery)
            .where(
                UserMastery.user_id == user_id,
                UserMastery.status.in_(["learning", "unstable", "forgotten"]),
            )
            .order_by(UserMastery.mastery_score.asc())
            .limit(limit)
        )
        masteries = result.scalars().all()

        kp_ids = [str(m.knowledge_point_id) for m in masteries]
        if kp_ids:
            kp_result = await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))
            )
            kp_map = {str(kp.id): kp for kp in kp_result.scalars().all()}
        else:
            kp_map = {}

        return [
            {
                "kp_id": str(m.knowledge_point_id),
                "kp_name": kp_map.get(str(m.knowledge_point_id)).name if kp_map.get(str(m.knowledge_point_id)) else None,
                "status": m.status,
                "mastery_score": round(m.mastery_score, 1),
                "wrong_count": m.wrong_count,
            }
            for m in masteries
        ]

    async def create_review_tasks_from_diagnosis(
        self,
        db: AsyncSession,
        user_id: str,
        diagnosis: dict,
        diagnosis_id: str = None,
    ) -> List[dict]:
        """
        根据诊断结果生成复习任务。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            diagnosis: 诊断结果 {review_suggestions, error_category, ...}
            diagnosis_id: 诊断记录 ID

        Returns:
            创建的复习任务列表
        """
        suggestions = diagnosis.get("review_suggestions", [])
        if not suggestions:
            return []

        created_tasks = []
        now = datetime.utcnow()

        for i, suggestion in enumerate(suggestions):
            action = suggestion.get("action", "review_material")
            kp_id = suggestion.get("kp_id")
            title = suggestion.get("title", "复习任务")
            description = suggestion.get("description", "")
            priority = suggestion.get("priority", 5)
            delay_hours = suggestion.get("delay_hours", 0)

            # 计算截止时间
            due_at = None
            if delay_hours:
                due_at = now + timedelta(hours=delay_hours)

            # 避免重复创建同类型任务
            existing = await self._find_existing_task(db, user_id, kp_id, action)
            if existing:
                # 更新已有任务的优先级
                if priority > existing.priority:
                    existing.priority = priority
                created_tasks.append(self._task_to_dict(existing))
                continue

            task = ReviewTask(
                user_id=user_id,
                knowledge_point_id=kp_id,
                task_type=action,
                title=title,
                description=description,
                action={"type": action, "kp_id": kp_id},
                priority=priority,
                status="pending",
                due_at=due_at,
                source_diagnosis_id=diagnosis_id,
            )
            db.add(task)
            await db.flush()
            created_tasks.append(self._task_to_dict(task))

        return created_tasks

    async def get_review_tasks(
        self,
        db: AsyncSession,
        user_id: str,
        status: str = None,
        limit: int = 20,
    ) -> List[dict]:
        """获取用户的复习任务列表"""
        query = select(ReviewTask).where(ReviewTask.user_id == user_id)

        if status:
            query = query.where(ReviewTask.status == status)

        query = query.order_by(
            ReviewTask.priority.desc(),
            ReviewTask.due_at.asc().nullslast(),
            ReviewTask.created_at.desc(),
        ).limit(limit)

        result = await db.execute(query)
        tasks = result.scalars().all()

        # 关联知识点信息
        kp_ids = [str(t.knowledge_point_id) for t in tasks if t.knowledge_point_id]
        kp_map = {}
        if kp_ids:
            kp_result = await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))
            )
            kp_map = {str(kp.id): kp for kp in kp_result.scalars().all()}

        return [
            {
                "id": str(t.id),
                "task_type": t.task_type,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "kp_id": str(t.knowledge_point_id) if t.knowledge_point_id else None,
                "kp_name": kp_map.get(str(t.knowledge_point_id)).name if t.knowledge_point_id and kp_map.get(str(t.knowledge_point_id)) else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]

    async def complete_review_task(
        self,
        db: AsyncSession,
        user_id: str,
        task_id: str,
    ) -> Optional[dict]:
        """标记复习任务为已完成"""
        result = await db.execute(
            select(ReviewTask).where(
                ReviewTask.id == task_id,
                ReviewTask.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return None

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        await db.flush()
        return self._task_to_dict(task)

    # ---------- 内部方法 ----------

    def _calculate_status(self, mastery: UserMastery) -> str:
        """
        根据分数、连续正确次数、遗忘时间计算掌握状态。

        状态机：
        - 分数 < 10: unknown
        - 10 <= 分数 < 40: learning
        - 40 <= 分数 < 70: unstable（或 forgotten，取决于是否曾掌握）
        - 分数 >= 70 且 连续正确 >= 3: mastered
        - 长时间未练习: mastered → unstable → forgotten
        """
        score = mastery.mastery_score or 0.0
        streak = mastery.streak or 0
        last_practiced = mastery.last_practiced_at
        current_status = mastery.status or "unknown"
        now = datetime.utcnow()

        # 先基于分数判断基础状态
        if score < 10:
            base_state = "unknown"
        elif score < 40:
            base_state = "learning"
        elif score < 70:
            # 曾掌握过且长时间没练 → forgotten
            if current_status in ("mastered", "forgotten") and last_practiced:
                days_since = (now - last_practiced).days
                if days_since >= self.forget_days_forgotten:
                    return "forgotten"
            base_state = "unstable"
        else:
            # 分数 >= 70
            if streak >= self.mastery_streak_threshold:
                base_state = "mastered"
            else:
                base_state = "unstable"

        # 遗忘检测：mastered 状态长时间未练习
        if base_state == "mastered" and last_practiced:
            days_since = (now - last_practiced).days
            if days_since >= self.forget_days_unstable:
                return "unstable"
            if days_since >= self.forget_days_forgotten:
                return "forgotten"

        # 验证状态转换合法性
        if base_state in STATE_TRANSITIONS.get(current_status, []) or base_state == current_status:
            return base_state

        # 如果不在合法转换中，但分数变化明显，也允许转换
        return base_state

    def _calculate_confidence(self, mastery: UserMastery) -> float:
        """
        计算系统对掌握状态的置信度（0-1）。

        因素：
        - 练习次数：练得越多越可信
        - 近期稳定性：最近正确率稳定则置信度高
        - 时间衰减：越久没练置信度越低
        """
        total_attempts = (mastery.correct_count or 0) + (mastery.wrong_count or 0)

        if total_attempts == 0:
            return 0.0

        # 练习次数因子（对数增长，5次达 0.7）
        import math
        count_factor = min(1.0, math.log(total_attempts + 1) / math.log(6))

        # 稳定性因子（基于最近正确率的波动）
        accuracy = mastery.recent_accuracy or 0.5
        # 正确率越高且 streak 越长，越稳定
        stability_factor = accuracy * min(1.0, (mastery.streak or 0) / 5)

        # 时间衰减因子
        time_factor = 1.0
        if mastery.last_practiced_at:
            days_since = (datetime.utcnow() - mastery.last_practiced_at).days
            # 7天后开始衰减
            if days_since > 7:
                time_factor = max(0.3, 1.0 - (days_since - 7) * 0.05)

        confidence = count_factor * 0.4 + stability_factor * 0.4 + time_factor * 0.2
        return max(0.0, min(1.0, confidence))

    def _calculate_review_due(self, mastery: UserMastery) -> Optional[datetime]:
        """计算下次复习时间"""
        if mastery.status == "mastered":
            interval_hours = self.review_intervals["mastered"]
        elif mastery.status == "unstable":
            interval_hours = self.review_intervals["unstable"]
        elif mastery.status == "forgotten":
            interval_hours = self.review_intervals["forgotten"]
        elif mastery.status == "learning":
            interval_hours = self.review_intervals["learning"]
        else:
            return None

        if mastery.last_practiced_at:
            return mastery.last_practiced_at + timedelta(hours=interval_hours)
        return None

    async def _find_existing_task(
        self,
        db: AsyncSession,
        user_id: str,
        kp_id: str,
        task_type: str,
    ) -> Optional[ReviewTask]:
        """查找是否已有同类型待处理任务"""
        if not kp_id:
            return None

        result = await db.execute(
            select(ReviewTask).where(
                ReviewTask.user_id == user_id,
                ReviewTask.knowledge_point_id == kp_id,
                ReviewTask.task_type == task_type,
                ReviewTask.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    def _task_to_dict(self, task: ReviewTask) -> dict:
        return {
            "id": str(task.id),
            "task_type": task.task_type,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "kp_id": str(task.knowledge_point_id) if task.knowledge_point_id else None,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        }


# ============== 全局单例 ==============

_mastery_service = None


def get_mastery_service() -> MasteryService:
    global _mastery_service
    if _mastery_service is None:
        _mastery_service = MasteryService()
    return _mastery_service
