"""
学习规划与自适应出题服务

核心流程：
1. 读取用户掌握度（UserMastery）
2. 计算各知识点的学习优先级
3. 选择合适的题目组成练习会话
4. 创建 PracticeSession 记录

优先级权重：
- 复习到期（forgotten/unstable + 天数）：权重 3.0
- 低掌握度（learning/unstable）：权重 2.0
- 高重要性（面试高频）：权重 1.5
- 最近错误（最近 7 天内答错）：权重 1.2
- 前置知识不足：权重 1.5
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    UserMastery,
    KnowledgePoint,
    KnowledgeRelation,
    Question,
    QuestionKnowledgeLink,
    PracticeSession,
    PracticeSessionQuestion,
    MasteryEvent,
    StudyPlan,
)
from app.services.mastery import get_mastery_service

# 熟练度等级到内部分数的映射
PROFICIENCY_LEVELS = {
    "acquainted": {"label": "了解", "score_threshold": 35},
    "familiar": {"label": "熟悉", "score_threshold": 55},
    "proficient": {"label": "掌握", "score_threshold": 75},
    "expert": {"label": "精通", "score_threshold": 90},
}


class LearningService:
    """学习规划服务"""

    def __init__(self):
        self.default_question_count = 5
        self.forget_days_forgotten = 14
        self.forget_days_unstable = 7

    # ---------- 核心：生成下一个练习会话 ----------

    async def generate_next_session(
        self,
        db: AsyncSession,
        user_id: str,
        mode: str = "adaptive",
        count: int = 5,
        kp_ids: List[str] = None,
    ) -> dict:
        """
        生成下一个练习会话。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            mode: 模式（adaptive/review/explore）
            count: 题目数量
            kp_ids: 限定知识点范围（可选）

        Returns:
            { session_id, questions, mode, reason_summary }
        """
        now = datetime.utcnow()

        # 1. 计算知识点优先级
        kp_priorities = await self._calculate_kp_priorities(
            db=db,
            user_id=user_id,
            mode=mode,
            kp_ids=kp_ids,
        )

        if not kp_priorities:
            # 没有知识点数据，返回空
            return {
                "session_id": None,
                "questions": [],
                "mode": mode,
                "reason_summary": "暂无知识点数据，请先导入题目和文档",
            }

        # 2. 按优先级选题
        selected_questions = await self._select_questions(
            db=db,
            kp_priorities=kp_priorities,
            count=count,
        )

        if not selected_questions:
            return {
                "session_id": None,
                "questions": [],
                "mode": mode,
                "reason_summary": "未找到匹配的题目",
            }

        # 3. 创建 PracticeSession
        session = PracticeSession(
            user_id=user_id,
            mode=mode,
            question_count=len(selected_questions),
            status="in_progress",
            started_at=now,
        )
        db.add(session)
        await db.flush()

        # 4. 创建 PracticeSessionQuestion 记录
        for i, (q, reason, kp_id) in enumerate(selected_questions):
            sq = PracticeSessionQuestion(
                session_id=session.id,
                question_id=q.id,
                sequence=i,
                selected_reason=reason,
            )
            db.add(sq)

        await db.commit()

        # 5. 组装返回
        reason_summary = self._build_reason_summary(kp_priorities, mode)

        return {
            "session_id": str(session.id),
            "mode": mode,
            "question_count": len(selected_questions),
            "reason_summary": reason_summary,
            "questions": [
                {
                    "id": str(q.id),
                    "type": q.type,
                    "difficulty": q.difficulty,
                    "content": q.content,
                    "options": q.options,
                    "selected_reason": reason,
                    "kp_id": kp_id,
                }
                for q, reason, kp_id in selected_questions
            ],
        }

    # ---------- Step 1: 计算知识点优先级 ----------

    async def _calculate_kp_priorities(
        self,
        db: AsyncSession,
        user_id: str,
        mode: str,
        kp_ids: List[str] = None,
    ) -> List[Tuple[str, float, dict]]:
        """
        计算每个知识点的学习优先级。

        Returns:
            [(kp_id, priority_score, info_dict), ...]，按优先级从高到低排序
        """
        # 查询所有知识点
        kp_query = select(KnowledgePoint)
        if kp_ids:
            kp_query = kp_query.where(KnowledgePoint.id.in_(kp_ids))
        kp_result = await db.execute(kp_query)
        all_kps = kp_result.scalars().all()

        if not all_kps:
            return []

        all_kp_ids = [str(kp.id) for kp in all_kps]
        kp_map = {str(kp.id): kp for kp in all_kps}

        # 查询用户掌握度
        mastery_result = await db.execute(
            select(UserMastery).where(
                UserMastery.user_id == user_id,
                UserMastery.knowledge_point_id.in_(all_kp_ids),
            )
        )
        masteries = mastery_result.scalars().all()
        mastery_map = {str(m.knowledge_point_id): m for m in masteries}

        # 刷新遗忘衰减状态（可能在用户未查看掌握度页面时已超期）
        now = datetime.utcnow()
        mastery_service = get_mastery_service()
        for m in masteries:
            old_status = m.status
            new_status = mastery_service.refresh_time_decay(m, now=now)
            if old_status != new_status:
                m.status = new_status
                m.confidence = mastery_service._calculate_confidence(m)
                m.review_due_at = mastery_service._calculate_review_due(m)

        # 查询前置依赖关系
        prereq_result = await db.execute(
            select(KnowledgeRelation).where(
                KnowledgeRelation.relation_type == "prerequisite",
                KnowledgeRelation.target_id.in_(all_kp_ids),
            )
        )
        prereqs = prereq_result.scalars().all()
        prereq_map: Dict[str, List[str]] = {}
        for pr in prereqs:
            target_id = str(pr.target_id)
            if target_id not in prereq_map:
                prereq_map[target_id] = []
            prereq_map[target_id].append(str(pr.source_id))

        # 查询最近错误时间（从 MasteryEvent 获取，避免在 UserMastery 上维护 last_wrong_at）
        last_wrong_result = await db.execute(
            select(MasteryEvent.knowledge_point_id, MasteryEvent.created_at)
            .where(
                MasteryEvent.user_id == user_id,
                MasteryEvent.event_type == "answer_wrong",
                MasteryEvent.knowledge_point_id.in_(all_kp_ids),
            )
            .order_by(MasteryEvent.created_at.desc())
        )
        last_wrong_rows = last_wrong_result.all()
        # 取每个知识点的最近错误时间（只保留最新的）
        last_wrong_map: Dict[str, datetime] = {}
        for kp_id_from_event, created_at in last_wrong_rows:
            kp_id_str = str(kp_id_from_event)
            if kp_id_str not in last_wrong_map:
                last_wrong_map[kp_id_str] = created_at

        priorities = []

        for kp_id, kp in kp_map.items():
            mastery = mastery_map.get(kp_id)
            score = 0.0
            info = {
                "kp_id": kp_id,
                "kp_name": kp.name,
                "status": mastery.status if mastery else "unknown",
                "mastery_score": mastery.mastery_score if mastery else 0.0,
                "importance": kp.importance or 5,
            }

            if mode == "adaptive":
                # 复习到期权重
                if mastery and mastery.last_practiced_at:
                    days_since = (now - mastery.last_practiced_at).days
                    if mastery.status == "forgotten":
                        score += 3.0 + min(days_since * 0.1, 2.0)
                        info["review_urgency"] = "forgotten"
                    elif mastery.status == "unstable" and days_since >= self.forget_days_unstable:
                        score += 2.0 + min((days_since - self.forget_days_unstable) * 0.15, 1.5)
                        info["review_urgency"] = "unstable_due"

                # 低掌握度权重
                if mastery:
                    if mastery.status == "forgotten":
                        score += 2.0
                    elif mastery.status in ("learning", "unstable"):
                        score += 2.0 * (1.0 - min((mastery.mastery_score or 0) / 70.0, 1.0))
                else:
                    score += 0.8

                # 高重要性权重
                importance = kp.importance or 5
                score += (importance / 10.0) * 1.5
                info["importance"] = importance

                # 最近错误权重（从 MasteryEvent 查询，而非直接访问不存在的 last_wrong_at）
                last_wrong_at = last_wrong_map.get(kp_id)
                if last_wrong_at:
                    days_since_wrong = (now - last_wrong_at).days
                    if days_since_wrong <= 7:
                        score += 1.2 * (1.0 - days_since_wrong / 7.0)
                        info["recently_wrong"] = True

                # 前置知识不足检查
                if kp_id in prereq_map:
                    for prereq_id in prereq_map[kp_id]:
                        prereq_mastery = mastery_map.get(prereq_id)
                        if not prereq_mastery or prereq_mastery.status in ("learning", "unknown", "forgotten"):
                            score += 0.5  # 前置未掌握，提高目标题优先级（暴露知识缺口）
                            info["has_weak_prereq"] = True
                            break

            elif mode == "review":
                # 只看复习到期的
                if mastery and mastery.last_practiced_at:
                    days_since = (now - mastery.last_practiced_at).days
                    if mastery.status == "forgotten":
                        score += 4.0
                    elif mastery.status == "unstable" and days_since >= self.forget_days_unstable:
                        score += 3.0
                    elif days_since >= 3:
                        score += 1.0

            elif mode == "explore":
                # 优先探索未学过的知识点
                if not mastery or mastery.status == "unknown":
                    score += 2.0
                elif mastery.status == "learning":
                    score += 1.0
                # 加一点重要性权重
                score += (kp.importance or 5) / 20.0

            priorities.append((kp_id, score, info))

        # 按优先级排序
        priorities.sort(key=lambda x: x[1], reverse=True)
        return priorities

    # ---------- Step 2: 选题 ----------

    async def _select_questions(
        self,
        db: AsyncSession,
        kp_priorities: List[Tuple[str, float, dict]],
        count: int,
    ) -> List[Tuple[Question, str, str]]:
        """
        根据知识点优先级选择题目。

        Returns:
            [(question, selected_reason, kp_id), ...]
        """
        if not kp_priorities:
            return []

        selected = []
        used_question_ids = set()
        target_per_kp = max(1, count // min(len(kp_priorities), count))

        for kp_id, priority, info in kp_priorities:
            if len(selected) >= count:
                break

            # 查询该知识点的题目
            result = await db.execute(
                select(Question)
                .join(QuestionKnowledgeLink, Question.id == QuestionKnowledgeLink.question_id)
                .where(
                    QuestionKnowledgeLink.knowledge_point_id == kp_id,
                    QuestionKnowledgeLink.role.in_(["primary", "secondary"]),
                )
                .order_by(Question.difficulty.asc())
                .limit(target_per_kp * 2)
            )
            questions = result.scalars().all()

            if not questions:
                continue

            # 决定选题原因
            if info.get("review_urgency") == "forgotten":
                reason = "review_due"
            elif info.get("recently_wrong"):
                reason = "recent_error"
            elif info.get("status") in ("learning", "unknown"):
                reason = "low_mastery"
            else:
                reason = "reinforce"

            # 选题：尽量选不同难度
            added = 0
            for q in questions:
                if str(q.id) in used_question_ids:
                    continue
                if added >= target_per_kp:
                    break
                selected.append((q, reason, kp_id))
                used_question_ids.add(str(q.id))
                added += 1

        # 如果不够，再从所有题目中补
        if len(selected) < count:
            remaining = count - len(selected)
            top_kp_ids = [kp_id for kp_id, _, _ in kp_priorities[:10]]
            result = await db.execute(
                select(Question)
                .join(QuestionKnowledgeLink, Question.id == QuestionKnowledgeLink.question_id)
                .where(QuestionKnowledgeLink.knowledge_point_id.in_(top_kp_ids))
                .limit(remaining * 3)
            )
            extra_questions = result.scalars().all()
            for q in extra_questions:
                if len(selected) >= count:
                    break
                if str(q.id) in used_question_ids:
                    continue
                selected.append((q, "fill", top_kp_ids[0] if top_kp_ids else None))
                used_question_ids.add(str(q.id))

        return selected[:count]

    # ---------- 辅助：生成原因摘要 ----------

    def _build_reason_summary(self, kp_priorities: list, mode: str) -> str:
        """生成人类可读的选题原因摘要"""
        if not kp_priorities:
            return "暂无推荐"

        top_kps = kp_priorities[:3]
        kp_names = [info.get("kp_name", "") for _, _, info in top_kps]

        if mode == "adaptive":
            reasons = []
            for _, _, info in top_kps:
                if info.get("review_urgency") == "forgotten":
                    reasons.append("遗忘复习")
                elif info.get("recently_wrong"):
                    reasons.append("近期错题")
                elif info.get("status") == "learning":
                    reasons.append("巩固提高")
                else:
                    reasons.append("持续强化")

            unique_reasons = list(dict.fromkeys(reasons))
            return f"重点复习 {'、'.join(kp_names[:2])}，原因：{'、'.join(unique_reasons[:2])}"

        elif mode == "review":
            return f"复习到期知识点：{'、'.join(kp_names[:3])}"

        elif mode == "explore":
            return f"探索新知识点：{'、'.join(kp_names[:3])}"

        return f"推荐知识点：{'、'.join(kp_names[:3])}"

    # ---------- 学习计划相关 ----------

    async def create_plan(
        self,
        db: AsyncSession,
        user_id: str,
        name: str,
        objective: str,
        source_type: str,
        source_id: str,
        target_proficiency: str,
        selected_kp_ids: List[str] = None,
        schedule: dict = None,
    ) -> dict:
        """
        创建学习计划。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            name: 计划名称
            objective: 学习目标描述
            source_type: 来源类型 (knowledge_base | document)
            source_id: 来源 ID
            target_proficiency: 目标熟练度等级 (acquainted | familiar | proficient | expert)
            selected_kp_ids: 用户勾选的知识点 ID 列表（可选，为空则自动提取）
            schedule: 学习节奏配置

        Returns:
            创建的 StudyPlan 信息
        """
        if target_proficiency not in PROFICIENCY_LEVELS:
            raise ValueError(f"无效的目标熟练度等级: {target_proficiency}")

        now = datetime.utcnow()

        # 1. 确定知识点范围
        kp_ids = selected_kp_ids or []

        # 如果用户未指定，从 source 中提取知识点
        if not kp_ids:
            kp_ids = await self._extract_kp_ids_from_source(
                db=db,
                source_type=source_type,
                source_id=source_id,
            )

        if not kp_ids:
            raise ValueError("未找到可学习的知识点，请确保知识库或文档中有内容")

        # 2. 查询知识点详情
        kp_result = await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))
        )
        kps = kp_result.scalars().all()

        kp_list = [
            {
                "kp_id": str(kp.id),
                "name": kp.name,
                "path": kp.path,
            }
            for kp in kps
        ]

        # 3. 估算完成时间
        sessions_per_week = schedule.get("sessions_per_week", 5) if schedule else 5
        questions_per_session = schedule.get("questions_per_session", 8) if schedule else 8
        total_kps = len(kp_list)
        # 假设每个知识点需要 2-3 次练习达到目标
        estimated_sessions = total_kps * 2
        estimated_weeks = estimated_sessions / max(sessions_per_week, 1)
        target_end_date = now + timedelta(weeks=estimated_weeks)

        # 4. 构建 config
        config = {
            "target_proficiency": target_proficiency,
            "target_score_threshold": PROFICIENCY_LEVELS[target_proficiency]["score_threshold"],
            "scope": {
                "source_type": source_type,
                "source_id": source_id,
                "knowledge_points": kp_list,
            },
            "schedule": schedule or {
                "sessions_per_week": sessions_per_week,
                "questions_per_session": questions_per_session,
            },
            "timeframe": {
                "start_date": now.strftime("%Y-%m-%d"),
                "target_end_date": target_end_date.strftime("%Y-%m-%d"),
                "estimated_weeks": round(estimated_weeks, 1),
                "estimated_sessions": estimated_sessions,
            },
            "strategy": {
                "review_ratio": 0.6,
                "new_kp_ratio": 0.3,
            },
        }

        # 5. 创建 StudyPlan
        plan = StudyPlan(
            user_id=user_id,
            name=name,
            objective=objective,
            status="active",
            config=config,
            started_at=now,
        )
        db.add(plan)
        await db.flush()

        return {
            "id": str(plan.id),
            "name": plan.name,
            "objective": plan.objective,
            "status": plan.status,
            "config": plan.config,
            "created_at": plan.created_at.isoformat(),
            "started_at": plan.started_at.isoformat(),
            "kp_count": total_kps,
            "estimated_sessions": estimated_sessions,
            "estimated_weeks": round(estimated_weeks, 1),
        }

    async def _extract_kp_ids_from_source(
        self,
        db: AsyncSession,
        source_type: str,
        source_id: str,
    ) -> List[str]:
        """
        从知识库或文档中提取知识点 ID。

        策略：
        1. 优先从现有 knowledge_points 表中按 category 或 knowledge_base_id 筛选
        2. 如果没有，返回空列表（需要用户手动指定）
        """
        kp_ids = []

        if source_type == "knowledge_base":
            # 从知识库关联的知识点中提取
            result = await db.execute(
                select(KnowledgePoint.id).where(
                    KnowledgePoint.knowledge_base_id == source_id
                )
            )
            rows = result.all()
            kp_ids = [str(row[0]) for row in rows]

        elif source_type == "document":
            # 从文档关联的知识点中提取（通过 chunks -> chunk_knowledge_links）
            from app.models import DocumentChunk, ChunkKnowledgeLink
            result = await db.execute(
                select(ChunkKnowledgeLink.knowledge_point_id)
                .join(DocumentChunk, DocumentChunk.id == ChunkKnowledgeLink.chunk_id)
                .where(DocumentChunk.document_id == source_id)
                .distinct()
            )
            rows = result.all()
            kp_ids = [str(row[0]) for row in rows]

        return kp_ids

    async def get_plan_progress(
        self,
        db: AsyncSession,
        plan_id: str,
        user_id: str,
    ) -> dict:
        """
        获取学习计划的进度（按等级维度统计）。

        Returns:
            进度数据，包含各等级分布、目标达成率等
        """
        # 1. 读取计划
        plan_result = await db.execute(
            select(StudyPlan).where(
                StudyPlan.id == plan_id,
                StudyPlan.user_id == user_id,
            )
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            return None

        config = plan.config or {}
        scope = config.get("scope", {})
        kp_list = scope.get("knowledge_points", [])
        target_proficiency = config.get("target_proficiency", "proficient")
        target_score = PROFICIENCY_LEVELS.get(target_proficiency, {}).get("score_threshold", 75)

        if not kp_list:
            return {
                "plan_id": str(plan.id),
                "name": plan.name,
                "status": plan.status,
                "target_proficiency": target_proficiency,
                "kp_distribution": {},
                "target_reached_count": 0,
                "total_kp_count": 0,
                "progress_percent": 0,
                "completed_sessions": 0,
                "estimated_total_sessions": config.get("timeframe", {}).get("estimated_sessions", 0),
                "current_streak_days": 0,
                "weakest_kps": [],
            }

        kp_ids = [kp["kp_id"] for kp in kp_list]

        # 2. 查询用户掌握度
        mastery_result = await db.execute(
            select(UserMastery).where(
                UserMastery.user_id == user_id,
                UserMastery.knowledge_point_id.in_(kp_ids),
            )
        )
        masteries = mastery_result.scalars().all()
        mastery_map = {str(m.knowledge_point_id): m for m in masteries}

        # 3. 按等级分布统计
        distribution = {
            "unknown": 0,
            "acquainted": 0,
            "familiar": 0,
            "proficient": 0,
            "expert": 0,
        }

        target_reached = 0
        weakest_kps = []

        for kp_info in kp_list:
            kp_id = kp_info["kp_id"]
            mastery = mastery_map.get(kp_id)
            score = mastery.mastery_score if mastery else 0.0

            # 判断当前等级
            if score >= 90:
                current_level = "expert"
            elif score >= 75:
                current_level = "proficient"
            elif score >= 55:
                current_level = "familiar"
            elif score >= 35:
                current_level = "acquainted"
            else:
                current_level = "unknown"

            distribution[current_level] += 1

            # 是否达到目标
            if score >= target_score:
                target_reached += 1
            else:
                weakest_kps.append({
                    "kp_id": kp_id,
                    "name": kp_info.get("name", ""),
                    "path": kp_info.get("path", ""),
                    "current_score": round(score, 1),
                    "target_score": target_score,
                })

        # 4. 统计练习会话数
        session_result = await db.execute(
            select(PracticeSession).where(
                PracticeSession.plan_id == plan_id,
                PracticeSession.user_id == user_id,
                PracticeSession.status == "completed",
            )
        )
        completed_sessions = len(session_result.scalars().all())

        # 5. 计算连续学习天数（简化版：最近 7 天有练习就算连续）
        now = datetime.utcnow()
        recent_result = await db.execute(
            select(PracticeSession.completed_at)
            .where(
                PracticeSession.plan_id == plan_id,
                PracticeSession.user_id == user_id,
                PracticeSession.status == "completed",
                PracticeSession.completed_at >= now - timedelta(days=7),
            )
            .order_by(PracticeSession.completed_at.desc())
        )
        recent_completed = recent_result.scalars().all()
        streak_days = self._calculate_streak_days(recent_completed)

        # 6. 按分数排序薄弱知识点
        weakest_kps.sort(key=lambda x: x["current_score"])
        weakest_kps = weakest_kps[:5]  # 只返回最薄弱的 5 个

        total_kps = len(kp_list)
        progress_percent = round((target_reached / total_kps * 100) if total_kps > 0 else 0, 1)

        return {
            "plan_id": str(plan.id),
            "name": plan.name,
            "status": plan.status,
            "target_proficiency": target_proficiency,
            "kp_distribution": distribution,
            "target_reached_count": target_reached,
            "total_kp_count": total_kps,
            "progress_percent": progress_percent,
            "completed_sessions": completed_sessions,
            "estimated_total_sessions": config.get("timeframe", {}).get("estimated_sessions", 0),
            "current_streak_days": streak_days,
            "weakest_kps": weakest_kps,
        }

    def _calculate_streak_days(self, completed_dates: List[datetime]) -> int:
        """计算连续学习天数"""
        if not completed_dates:
            return 0

        # 去重并按日期排序
        unique_dates = sorted(set(d.date() for d in completed_dates), reverse=True)

        streak = 1
        today = datetime.utcnow().date()

        # 检查是否从今天或昨天开始
        if unique_dates[0] < today - timedelta(days=1):
            return 0  # 断档超过 1 天

        for i in range(1, len(unique_dates)):
            if unique_dates[i] == unique_dates[i - 1] - timedelta(days=1):
                streak += 1
            else:
                break

        return streak

    async def generate_plan_session(
        self,
        db: AsyncSession,
        plan_id: str,
        user_id: str,
    ) -> dict:
        """
        为学习计划生成下一次练习。

        复用 generate_next_session，但限定在计划范围内的知识点。
        """
        # 1. 读取计划配置
        plan_result = await db.execute(
            select(StudyPlan).where(
                StudyPlan.id == plan_id,
                StudyPlan.user_id == user_id,
            )
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise ValueError("计划不存在")

        if plan.status != "active":
            raise ValueError(f"计划状态为 {plan.status}，无法生成练习")

        config = plan.config or {}
        scope = config.get("scope", {})
        kp_list = scope.get("knowledge_points", [])
        kp_ids = [kp["kp_id"] for kp in kp_list]

        questions_per_session = config.get("schedule", {}).get("questions_per_session", 8)

        # 2. 决定模式（根据计划进度动态选择）
        mode = self._determine_session_mode(db, plan_id, user_id, kp_ids)

        # 3. 调用现有的 generate_next_session
        result = await self.generate_next_session(
            db=db,
            user_id=user_id,
            mode=mode,
            count=questions_per_session,
            kp_ids=kp_ids,
        )

        # 4. 关联到计划
        if result.get("session_id"):
            from sqlalchemy import update
            await db.execute(
                update(PracticeSession)
                .where(PracticeSession.id == result["session_id"])
                .values(plan_id=plan.id)
            )
            await db.commit()

        return result

    def _determine_session_mode(
        self,
        db: AsyncSession,
        plan_id: str,
        user_id: str,
        kp_ids: List[str],
    ) -> str:
        """
        根据计划进度决定本次练习模式。

        策略：
        - 如果有大量复习到期的知识点 → review
        - 否则 → adaptive
        """
        # 简化版：默认 adaptive，后续可根据掌握度数据优化
        return "adaptive"


# ============== 全局单例 ==============

_learning_service = None


def get_learning_service() -> LearningService:
    global _learning_service
    if _learning_service is None:
        _learning_service = LearningService()
    return _learning_service
