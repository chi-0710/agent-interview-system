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

from app.models import UserMastery, KnowledgePoint, ReviewTask, MasteryEvent

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
        answer_id: str = None,
        question_id: str = None,
        error_category: str = None,
        error_pattern_id: str = None,
    ) -> Dict[str, dict]:
        """
        应用掌握度变化量，更新用户掌握状态。
        为每个知识点创建 MasteryEvent 记录。

        注意：这里 is_correct 是"这道题"的对错，不是整套题。
        每道题的每个知识点单独调用本方法。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            mastery_delta: {kp_id: delta_value} 正值加分，负值扣分
            is_correct: 本题是否答对
            question_difficulty: 题目难度
            answer_id: 作答记录 ID
            question_id: 题目 ID
            error_category: 错误分类（答错时）
            error_pattern_id: 错误模式 ID（答错时）

        Returns:
            {kp_id: {status, mastery_score, streak, ...}} 更新后的掌握度信息
        """
        results = {}
        now = datetime.utcnow()
        event_type = "answer_correct" if is_correct else "answer_wrong"

        for kp_id, delta in mastery_delta.items():
            mastery = await self.get_or_create_mastery(db, user_id, kp_id)

            # 保存变化前状态（用于事件记录）
            score_before = mastery.mastery_score or 0.0
            status_before = mastery.status
            old_streak = mastery.streak or 0

            # 应用分数变化，限制在 0-100
            new_score = max(0.0, min(100.0, score_before + delta))
            mastery.mastery_score = new_score

            # 更新计数（按本题的对错，不是整场）
            if is_correct:
                mastery.correct_count = (mastery.correct_count or 0) + 1
                mastery.streak = old_streak + 1
                mastery.last_success_at = now
            else:
                mastery.wrong_count = (mastery.wrong_count or 0) + 1
                mastery.streak = 0  # 答错重置连续正确

            # 更新最近正确率
            total = (mastery.correct_count or 0) + (mastery.wrong_count or 0)
            if total > 0:
                mastery.recent_accuracy = (mastery.correct_count or 0) / total

            # 先用旧的 last_practiced_at 计算状态（不传入 now，避免用当前时间判断遗忘）
            # 这样只有答题结果的分数、计数变化会影响状态
            new_status = self._calculate_status_for_answer(
                mastery,
                is_correct=is_correct,
                delta=delta,
            )
            mastery.status = new_status

            # 更新最后练习时间（在状态计算之后）
            mastery.last_practiced_at = now

            # 记录首次 mastered 时间
            if new_status == "mastered" and not mastery.mastered_at:
                mastery.mastered_at = now

            # 计算置信度
            mastery.confidence = self._calculate_confidence(mastery)

            # 计算下次复习时间
            mastery.review_due_at = self._calculate_review_due(mastery)

            # 创建掌握度事件记录
            event = MasteryEvent(
                user_id=user_id,
                mastery_id=mastery.id,
                knowledge_point_id=kp_id,
                answer_id=answer_id,
                question_id=question_id,
                event_type=event_type,
                is_correct=is_correct,
                delta=delta,
                score_before=score_before,
                score_after=new_score,
                status_before=status_before,
                status_after=new_status,
                error_category=error_category if not is_correct else None,
                error_pattern_id=error_pattern_id if not is_correct else None,
            )
            db.add(event)

            # 记录状态变化
            if status_before != new_status:
                logger.info(
                    f"[mastery] user={user_id} kp={kp_id}: "
                    f"{status_before} → {new_status} "
                    f"(score: {score_before:.1f} → {new_score:.1f})"
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
                "last_success_at": mastery.last_success_at.isoformat() if mastery.last_success_at else None,
                "mastered_at": mastery.mastered_at.isoformat() if mastery.mastered_at else None,
                "status_changed": status_before != new_status,
                "old_status": status_before,
                "delta": delta,
            }

        await db.flush()
        return results

    async def get_user_mastery_list(
        self,
        db: AsyncSession,
        user_id: str,
        category: str = None,
        status: str = None,
        refresh: bool = True,
    ) -> List[dict]:
        """获取用户所有知识点的掌握情况

        Args:
            refresh: 是否先刷新状态（检查遗忘等）
        """
        query = select(UserMastery).where(UserMastery.user_id == user_id)

        if status:
            query = query.where(UserMastery.status == status)

        result = await db.execute(query)
        masteries = result.scalars().all()

        # 读取时刷新状态（检查遗忘）
        if refresh and masteries:
            now = datetime.utcnow()
            for m in masteries:
                old_status = m.status
                new_status = self.refresh_time_decay(m, now=now)
                if old_status != new_status:
                    logger.info(f"[mastery/refresh] kp={m.knowledge_point_id}: {old_status} → {new_status}")
                    m.status = new_status
                    m.confidence = self._calculate_confidence(m)
                    m.review_due_at = self._calculate_review_due(m)

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
                "last_success_at": m.last_success_at.isoformat() if m.last_success_at else None,
                "mastered_at": m.mastered_at.isoformat() if m.mastered_at else None,
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

    async def get_evidence_chunks_for_kps(
        self,
        db: AsyncSession,
        kp_ids: List[str],
        limit_per_kp: int = 3,
    ) -> dict:
        """
        批量获取知识点对应的证据文档段落。

        Returns:
            { kp_id: [ {chunk_id, document_id, section_path, start_line, end_line, content, relevance} ] }
        """
        from app.models import DocumentChunk, ChunkKnowledgeLink, Document
        from sqlalchemy import select

        if not kp_ids:
            return {}

        # 查询关联表，按相关度排序
        result = await db.execute(
            select(
                ChunkKnowledgeLink,
                DocumentChunk,
                Document,
            )
            .join(DocumentChunk, ChunkKnowledgeLink.chunk_id == DocumentChunk.id)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(ChunkKnowledgeLink.knowledge_point_id.in_(kp_ids))
            .order_by(
                ChunkKnowledgeLink.knowledge_point_id,
                ChunkKnowledgeLink.relevance.desc(),
            )
        )
        rows = result.all()

        result_map = {kp_id: [] for kp_id in kp_ids}
        counts = {kp_id: 0 for kp_id in kp_ids}

        for link, chunk, doc in rows:
            kp_id = str(link.knowledge_point_id)
            if counts.get(kp_id, 0) >= limit_per_kp:
                continue
            result_map[kp_id].append({
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "document_path": doc.file_path,
                "document_title": doc.title,
                "section_path": chunk.section_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content_preview": chunk.content[:200] if chunk.content else "",
                "relevance": link.relevance,
            })
            counts[kp_id] = counts.get(kp_id, 0) + 1

        return result_map

    async def create_review_tasks_from_diagnosis(
        self,
        db: AsyncSession,
        user_id: str,
        diagnosis: dict,
        diagnosis_id: str = None,
        question_id: str = None,
        evidence_map: dict = None,
    ) -> List[dict]:
        """
        根据诊断结果生成复习任务。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            diagnosis: 诊断结果 {review_suggestions, error_category, weak_kp_ids, evidence_chunks, ...}
            diagnosis_id: 诊断记录 ID
            question_id: 触发诊断的题目 ID
            evidence_map: {kp_id: [{chunk_id, document_id, section_path, content_preview, ...}]}

        Returns:
            创建的复习任务列表
        """
        suggestions = diagnosis.get("review_suggestions", [])
        if not suggestions:
            return []

        created_tasks = []
        now = datetime.utcnow()
        evidence_map = evidence_map or {}

        for i, suggestion in enumerate(suggestions):
            action = suggestion.get("action", "review_material")
            kp_id = suggestion.get("kp_id")
            title = suggestion.get("title", "复习任务")
            description = suggestion.get("description", "")
            priority = suggestion.get("priority", 5)
            delay_hours = suggestion.get("delay_hours", 0)
            target_kp_ids = suggestion.get("target_kp_ids") or ([kp_id] if kp_id else [])

            # 计算截止时间
            due_at = None
            if delay_hours:
                due_at = now + timedelta(hours=delay_hours)

            # 避免重复创建同类型任务
            existing = await self._find_existing_task(db, user_id, kp_id, action)
            if existing:
                # 更新已有任务的优先级
                if priority > (existing.priority or 0):
                    existing.priority = priority
                created_tasks.append(self._task_to_dict(existing))
                continue

            # 获取知识点对应的 evidence chunks
            kp_chunks = evidence_map.get(str(kp_id), []) if kp_id else []
            document_ids = list(set(c.get("document_id") for c in kp_chunks if c.get("document_id")))
            chunk_ids = [c.get("chunk_id") for c in kp_chunks if c.get("chunk_id")]

            # 构建 target（任务目标）
            target = {
                "knowledge_point_id": kp_id,
                "knowledge_point_ids": target_kp_ids,
                "question_id": question_id,
                "document_ids": document_ids,
                "chunk_ids": chunk_ids,
            }

            # 构建 action（具体动作，包含可执行信息）
            action_obj = {
                "type": action,
                "kp_id": kp_id,
            }
            if kp_chunks:
                # 填充具体资料段落信息
                action_obj["document_id"] = document_ids[0] if document_ids else None
                action_obj["chunk_ids"] = chunk_ids
                action_obj["section_path"] = kp_chunks[0].get("section_path") if kp_chunks else None

            # 构建 next_action（完成任务后的下一步）
            next_action = None
            if action == "review_material":
                next_action = {
                    "type": "practice_question",
                    "knowledge_point_id": kp_id,
                    "question_count": 2,
                    "difficulty": "medium",
                }
            elif action in ("concept_comparison", "practice_question"):
                next_action = {
                    "type": "follow_up_test",
                    "delay_hours": 48,
                    "knowledge_point_id": kp_id,
                }

            task = ReviewTask(
                user_id=user_id,
                knowledge_point_id=kp_id,
                task_type=action,
                title=title,
                description=description,
                action=action_obj,
                target=target,
                next_action=next_action,
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

    def _calculate_status(
        self,
        mastery: UserMastery,
        now: datetime = None,
        use_current_last_practiced: bool = False,
    ) -> str:
        """
        根据分数、连续正确次数、遗忘时间计算掌握状态。

        状态机：
        - 分数 < 10: unknown
        - 10 <= 分数 < 40: learning
        - 40 <= 分数 < 70: unstable（或 forgotten，取决于是否曾掌握且长期未复习）
        - 分数 >= 70 且 连续正确 >= 3: mastered
        - 长时间未练习: mastered → unstable → forgotten

        关键修复：
        1. 遗忘判断从严重到轻：先判断 forgotten（14天），再判断 unstable（7天）
        2. 使用旧的 last_practiced_at 计算，而不是刚更新的 now
        3. 只有曾经 mastered 过的才会进入 forgotten

        Args:
            mastery: 掌握度记录
            now: 当前时间（用于计算时间差）
            use_current_last_practiced: True=使用 mastery 上现有的 last_practiced_at（更新前的旧值）
        """
        score = mastery.mastery_score or 0.0
        streak = mastery.streak or 0
        current_status = mastery.status or "unknown"
        if now is None:
            now = datetime.utcnow()

        # 取最后练习时间（使用更新前的旧值，避免刚答完题就判断遗忘）
        last_practiced = mastery.last_practiced_at

        # ---- 第一步：基于分数判断基础状态 ----
        if score < 10:
            base_state = "unknown"
        elif score < 40:
            base_state = "learning"
        elif score < 70:
            # 40-70 分区间
            # 曾掌握过（mastered 或 forgotten）且长期未复习 → forgotten
            # 注意：先判断更严重的 forgotten，再 fallback 到 unstable
            was_ever_mastered = (
                current_status in ("mastered", "forgotten")
                or mastery.mastered_at is not None
            )
            if was_ever_mastered and last_practiced:
                days_since = (now - last_practiced).days
                if days_since >= self.forget_days_forgotten:
                    return "forgotten"  # 严重遗忘，直接返回
            base_state = "unstable"
        else:
            # 分数 >= 70
            if streak >= self.mastery_streak_threshold:
                base_state = "mastered"
            else:
                base_state = "unstable"

        # ---- 第二步：遗忘检测（仅针对 mastered 状态）----
        # 注意：判断顺序从严重到轻微 — 先 forgotten 后 unstable
        if base_state == "mastered" and last_practiced:
            days_since = (now - last_practiced).days
            # 先判断更严重的
            if days_since >= self.forget_days_forgotten:
                return "forgotten"
            if days_since >= self.forget_days_unstable:
                return "unstable"

        # ---- 第三步：状态转换合法性检查 ----
        if base_state in STATE_TRANSITIONS.get(current_status, []) or base_state == current_status:
            return base_state

        # 如果不在合法转换中，但分数变化明显，也允许转换
        return base_state

    def _calculate_status_for_answer(
        self,
        mastery: UserMastery,
        is_correct: bool,
        delta: float,
    ) -> str:
        """
        只根据本次答题结果计算状态（不做遗忘判断）。

        遗忘判断应该由 refresh_time_decay() 在读取掌握度时单独处理。

        状态转换规则：
        - 分数 < 10: unknown
        - 10 <= 分数 < 40: learning
        - 40 <= 分数 < 70: unstable
        - 分数 >= 70 且 连续正确 >= 3: mastered
        """
        score = mastery.mastery_score or 0.0
        streak = mastery.streak or 0
        current_status = mastery.status or "unknown"

        # 基于分数判断目标状态
        if score < 10:
            target_state = "unknown"
        elif score < 40:
            target_state = "learning"
        elif score < 70:
            target_state = "unstable"
        else:
            # 分数 >= 70
            if streak >= self.mastery_streak_threshold:
                target_state = "mastered"
            else:
                target_state = "unstable"

        # 检查状态转换合法性
        if target_state in STATE_TRANSITIONS.get(current_status, []) or target_state == current_status:
            return target_state

        # 如果不在合法转换中，但分数变化明显，也允许转换
        return target_state

    def refresh_time_decay(self, mastery: UserMastery, now: datetime = None) -> str:
        """
        刷新遗忘状态（基于时间衰减）。

        在读取掌握度、生成今日任务时调用。
        判断顺序从严重到轻微：先 forgotten（14天），再 unstable（7天）。

        Args:
            mastery: 掌握度记录
            now: 当前时间

        Returns:
            新的状态（可能与原来相同）
        """
        if now is None:
            now = datetime.utcnow()

        current_status = mastery.status
        last_practiced = mastery.last_practiced_at

        # 如果没有练习记录，不触发遗忘
        if not last_practiced:
            return current_status

        days_since = (now - last_practiced).days

        # 只有曾掌握过（mastered 或 forgotten）才可能进入遗忘流程
        was_ever_mastered = (
            current_status in ("mastered", "forgotten")
            or mastery.mastered_at is not None
        )

        # 先判断更严重的 forgotten（14天以上）
        if was_ever_mastered and days_since >= self.forget_days_forgotten:
            new_status = "forgotten"
            logger.info(f"[mastery/time_decay] kp={mastery.knowledge_point_id}: "
                       f"{current_status} → {new_status} (days_since={days_since})")
            return new_status

        # 再判断 unstable（7-13天）
        if was_ever_mastered and days_since >= self.forget_days_unstable:
            new_status = "unstable"
            logger.info(f"[mastery/time_decay] kp={mastery.knowledge_point_id}: "
                       f"{current_status} → {new_status} (days_since={days_since})")
            return new_status

        return current_status

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
            "target": task.target,
            "next_action": task.next_action,
            "source_diagnosis_id": str(task.source_diagnosis_id) if task.source_diagnosis_id else None,
        }


# ============== 全局单例 ==============

_mastery_service = None


def get_mastery_service() -> MasteryService:
    global _mastery_service
    if _mastery_service is None:
        _mastery_service = MasteryService()
    return _mastery_service
