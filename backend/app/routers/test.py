"""测试路由

学习闭环核心路由：提交答案 → 评判 → 诊断 → 更新掌握度 → 生成复习任务 → 返回反馈

- POST /api/test/submit              → 提交答案，返回完整学习闭环结果（四态提交协议）
- GET  /api/test/submissions/{id}    → 查询提交状态（用于 outcome_unknown 恢复与对账）
- GET  /api/test/sessions            → 测试会话列表
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Literal, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, InterfaceError

from app.database import get_db, async_session_factory
from app.dependencies import CurrentUser, get_current_user
from app.models import TestSession, TestAnswer, Question, Diagnosis, KnowledgePoint, QuestionKnowledgeLink, PracticeSession, PracticeSessionQuestion, Document
from app.services.evaluator import evaluate_answer as evaluate_single
from app.services.evaluator import evaluate_code_answer
from app.services.error_tags import aggregate_error_tags
from app.services.diagnosis import get_diagnosis_service
from app.services.mastery import get_mastery_service
from app.services.llm import chat as llm_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test"])


# ---- Pydantic Models ----

class AnswerItem(BaseModel):
    question_id: str
    user_answer: str

    @field_validator("question_id")
    @classmethod
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("question_id 不能为空")
        return v.strip()


class SubmitRequest(BaseModel):
    answers: List[AnswerItem] = []
    # 自适应练习会话 ID（推荐）：由 /api/learning/next-session 生成，用于学习闭环
    practice_session_id: Optional[str] = None
    # file_path 仅作为无练习会话时的向后兼容字段（用于错题 chunk 解析）
    file_path: Optional[str] = None
    session_id: Optional[str] = None  # 可选：属于某个练习会话
    mode: Optional[str] = "learn"  # learn | mock_interview
    submission_id: Optional[str] = None  # M4: 幂等键，前端生成

    @field_validator("answers")
    @classmethod
    def answers_not_empty(cls, v):
        if not v:
            raise ValueError("answers 不能为空")
        return v


class ErrorTag(BaseModel):
    tag: str
    count: int
    sections: List[str]


class DetailItem(BaseModel):
    questionId: str
    correct: bool
    errorType: Optional[str] = None
    explanation: str = ""


class EvaluationResult(BaseModel):
    score: float
    summary: str
    details: List[DetailItem]
    errorTags: List[ErrorTag]


class LearningRecord(BaseModel):
    sessionId: Optional[str] = None
    diagnoses: List[dict] = []
    masteryUpdates: dict = {}
    reviewTasks: List[dict] = []
    weakPoints: List[dict] = []


class SubmitResponse(BaseModel):
    submissionId: str
    commitStatus: Literal["committed", "not_committed", "outcome_unknown", "tracking_disabled"]
    retryable: bool = False
    message: Optional[str] = None
    evaluation: EvaluationResult
    learningRecord: Optional[LearningRecord] = None


# ---- 自定义异常 ----

class CommitUnknownError(Exception):
    """commit 阶段连接异常，无法确认 DB 是否已提交。"""


class RetryablePersistenceError(Exception):
    """事务内异常，已回滚，确定未提交。"""


class ConcurrentSubmissionError(Exception):
    """并发重复提交，IntegrityError 触发，需回查。"""


# ---- 幂等哈希 (M4.2) ----

def compute_request_hash(req: SubmitRequest) -> str:
    """计算请求哈希，用于幂等冲突检测。
    包含：answers（按 question_id 排序） + practice_session_id + mode
    不包含：submission_id（幂等键本身）、file_path（派生字段）、session_id（向后兼容字段）
    """
    sorted_answers = sorted(
        [{"question_id": a.question_id, "user_answer": a.user_answer} for a in req.answers],
        key=lambda x: x["question_id"],
    )
    canonical = {
        "answers": sorted_answers,
        "practice_session_id": req.practice_session_id,
        "mode": req.mode,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


# ---- 辅助函数 ----

async def _load_question_knowledge_links(session, question_ids: List[str]) -> dict:
    """加载题目关联的知识点信息"""
    try:
        result = await session.execute(
            select(QuestionKnowledgeLink, KnowledgePoint)
            .join(KnowledgePoint, QuestionKnowledgeLink.knowledge_point_id == KnowledgePoint.id)
            .where(QuestionKnowledgeLink.question_id.in_(question_ids))
        )
        rows = result.all()

        kp_map = {}
        for link, kp in rows:
            qid = str(link.question_id)
            if qid not in kp_map:
                kp_map[qid] = []
            kp_map[qid].append({
                "id": str(kp.id),
                "name": kp.name,
                "path": kp.path,
                "importance": kp.importance,
                "role": link.role,
                "weight": link.weight,
            })
        return kp_map
    except Exception as e:
        logger.warning(f"[test/submit] load knowledge links failed: {e}")
        return {}


# ---- M3.1 拆分函数 1：加载题目 + 严格校验 ----

async def load_submission_questions(
    req: SubmitRequest,
    current_user: CurrentUser,
) -> Tuple[dict, Optional[PracticeSession], Optional[str]]:
    """加载题目并严格校验。

    - 校验 practice_session_id 归属、反查 file_path
    - 严格校验题目（重复 qid→422、不存在→404、归属不符→422）
    - DB 不可用→503

    返回：(questions_map, practice_session_obj, derived_file_path)
    不再有 IN_MEMORY_QUESTIONS 兜底。
    """
    derived_file_path = req.file_path
    practice_session_obj = None

    # Step 0: 处理练习会话（practice_session_id）
    if req.practice_session_id:
        async with async_session_factory() as session:
            try:
                ps_result = await session.execute(
                    select(PracticeSession).where(
                        PracticeSession.id == req.practice_session_id,
                        PracticeSession.user_id == current_user.user_id,
                    )
                )
                practice_session_obj = ps_result.scalar_one_or_none()
                if not practice_session_obj:
                    raise HTTPException(status_code=404, detail="练习会话不存在或无权访问")

                # 反查会话题目关联的文档 file_path（用于错题 chunk 解析）
                if not derived_file_path:
                    doc_result = await session.execute(
                        select(Document.file_path)
                        .join(Question, Question.document_id == Document.id)
                        .join(PracticeSessionQuestion, PracticeSessionQuestion.question_id == Question.id)
                        .where(PracticeSessionQuestion.session_id == practice_session_obj.id)
                        .limit(1)
                    )
                    row = doc_result.first()
                    if row and row[0]:
                        derived_file_path = row[0]
            except HTTPException:
                raise
            except (OperationalError, InterfaceError) as e:
                logger.error(f"[test/submit] DB 不可用（加载练习会话）: {e}", exc_info=True)
                raise HTTPException(status_code=503, detail="数据库不可用，请稍后重试")
            except Exception as e:
                logger.warning(f"[test/submit] 加载练习会话失败: {e}")

    # Step 1: 加载题目 + 严格校验（不再有 IN_MEMORY_QUESTIONS 兜底）
    q_ids = [a.question_id for a in req.answers]
    if len(q_ids) != len(set(q_ids)):
        raise HTTPException(status_code=422, detail="存在重复的 question_id")

    questions: dict = {}
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(Question).where(Question.id.in_(q_ids))
            )
            db_qs = result.scalars().all()
            for q in db_qs:
                questions[str(q.id)] = {
                    "id": str(q.id), "type": q.type or "text", "content": q.content,
                    "expected_answer": q.expected_answer or "", "options": q.options,
                    "tags": q.tags or [], "sections": q.sections or [],
                    "difficulty": q.difficulty or "medium",
                    "common_mistakes": q.common_mistakes,
                    "rubric": q.rubric,
                }
        except (OperationalError, InterfaceError) as e:
            logger.error(f"[test/submit] DB 不可用（加载题目）: {e}", exc_info=True)
            raise HTTPException(status_code=503, detail="数据库不可用，请稍后重试")

    if len(questions) != len(q_ids):
        missing = set(q_ids) - set(questions.keys())
        raise HTTPException(status_code=404, detail=f"题目不存在: {missing}")

    # 校验归属
    if practice_session_obj is not None:
        async with async_session_factory() as session:
            try:
                ps_q_result = await session.execute(
                    select(PracticeSessionQuestion.question_id)
                    .where(PracticeSessionQuestion.session_id == req.practice_session_id)
                )
                ps_q_ids = {str(r[0]) for r in ps_q_result.all()}
            except (OperationalError, InterfaceError) as e:
                logger.error(f"[test/submit] DB 不可用（校验归属）: {e}", exc_info=True)
                raise HTTPException(status_code=503, detail="数据库不可用，请稍后重试")
        if not set(q_ids).issubset(ps_q_ids):
            raise HTTPException(status_code=422, detail="提交的题目不属于该练习会话")

    return questions, practice_session_obj, derived_file_path


# ---- M4.3 拆分函数 2：幂等检查 ----

async def check_idempotency(
    session,
    user_id: str,
    submission_id: str,
    request_hash: str,
) -> Optional[Tuple[Optional[EvaluationResult], Optional[LearningRecord]]]:
    """幂等检查：若同一 (user_id, submission_id) 已存在，按 request_hash 校验一致性后从快照恢复。"""
    result = await session.execute(
        select(TestSession).where(
            TestSession.user_id == user_id,
            TestSession.client_submission_id == submission_id,
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        return None
    if existing.request_hash != request_hash:
        raise HTTPException(status_code=409, detail="submission_id 已存在但请求内容不一致")
    # 从快照恢复
    evaluation = EvaluationResult(**existing.evaluation_snapshot) if existing.evaluation_snapshot else None
    learning_record = LearningRecord(**existing.learning_record_snapshot) if existing.learning_record_snapshot else None
    return evaluation, learning_record


# ---- M3.1 拆分函数 3：评判（事务外，纯计算）----

async def evaluate_submission(
    questions: dict,
    answer_map: List[Tuple[AnswerItem, dict]],
    derived_file_path: Optional[str],
) -> Tuple[EvaluationResult, List[dict], dict]:
    """并发 LLM 评判 + 加载知识点关联 + 逐题诊断 + 聚合 errorTags + 生成 summary。

    事务外纯计算。
    返回：(evaluation_result, diagnosis_drafts, enriched_evals_map)
    - evaluation_result: EvaluationResult Pydantic model
    - diagnosis_drafts: 诊断草稿列表（纯 dict，含 questionId/error_category/...）
    - enriched_evals_map: 供 persist 使用的 enriched_evals，按 questionId 索引
    """
    diagnosis_service = get_diagnosis_service()

    # ========== Step 2: 并发评判 ==========
    eval_tasks = []
    for ans, q in answer_map:
        q_type = q.get("type", "text")
        if q_type == "code":
            eval_tasks.append(
                evaluate_code_answer(
                    question=q["content"],
                    user_code=ans.user_answer,
                    question_id=ans.question_id,
                )
            )
        else:
            eval_tasks.append(
                evaluate_single(
                    question=q["content"],
                    answer=q.get("expected_answer", ""),
                    user_answer=ans.user_answer,
                )
            )

    if not eval_tasks:
        raise HTTPException(status_code=400, detail="没有可评判的题目")

    logger.info(f"[test/submit] evaluating {len(eval_tasks)} questions")
    t0 = datetime.utcnow()
    eval_results = await asyncio.gather(*eval_tasks, return_exceptions=True)
    elapsed = (datetime.utcnow() - t0).total_seconds()
    logger.info(f"[test/submit] evaluation done in {elapsed:.1f}s (mode: LLM)")

    # ========== Step 3: 加载知识点关联 ==========
    question_kps = {}
    try:
        async with async_session_factory() as session:
            q_ids = [str(q["id"]) for q in questions.values()]
            question_kps = await _load_question_knowledge_links(session, q_ids)
    except Exception as e:
        logger.warning(f"[test/submit] load knowledge links failed: {e}")

    # ========== Step 4: 逐题诊断 + 构建结果 ==========
    details = []
    scores = []
    enriched_evals = []
    diagnoses = []
    enriched_evals_map = {}

    for i, (ans, q) in enumerate(answer_map):
        raw = eval_results[i] if i < len(eval_results) else None
        if isinstance(raw, Exception):
            result_dict = {
                "correct": False, "score": 0, "error_type": "评判异常",
                "explanation": f"评判出错：{str(raw)[:100]}", "error_tags": q.get("tags", []),
            }
        else:
            result_dict = raw or {"correct": False, "score": 0, "error_type": "未知",
                                  "explanation": "无评判结果", "error_tags": []}

        correct = result_dict.get("correct", False)
        score = result_dict.get("score", 0)
        scores.append(score)

        details.append({
            "questionId": ans.question_id,
            "correct": correct,
            "errorType": result_dict.get("error_type"),
            "explanation": result_dict.get("explanation", ""),
        })

        q_tags = q.get("tags", [])
        q_sections = q.get("sections", [])

        enriched_evals.append({
            "correct": correct,
            "error_tags": result_dict.get("error_tags", []),
            "question": {
                "content": q["content"],
                "tags": q_tags,
                "sections": q_sections,
            },
        })

        # 供 persist 使用：含完整信息
        enriched_evals_map[ans.question_id] = {
            "correct": correct,
            "score": score,
            "error_type": result_dict.get("error_type"),
            "error_tags": result_dict.get("error_tags", []),
            "explanation": result_dict.get("explanation", ""),
            "answer_text": ans.user_answer,
            "question": q,
        }

        # ---- 能力诊断 ----
        # 评判服务不可用时，跳过诊断（避免将系统故障误判为用户答错）
        is_eval_unavailable = result_dict.get("error_type") in ("评判失败", "评判异常")

        kps_for_q = question_kps.get(str(q.get("id")), [])
        eval_with_answer = {**result_dict, "user_answer": ans.user_answer}

        diag_result = diagnosis_service.diagnose(
            question=q,
            evaluation=eval_with_answer,
            knowledge_points=kps_for_q,
            common_mistakes=q.get("common_mistakes"),
        )
        diag_result["_eval_unavailable"] = is_eval_unavailable
        diagnoses.append({
            "questionId": ans.question_id,
            **diag_result,
        })

    # ========== Step 5: 聚合 errorTags（向后兼容） ==========
    # file_path 优先使用从练习会话反查得到的 derived_file_path
    error_tags = aggregate_error_tags(enriched_evals, derived_file_path)

    # ========== Step 7: 生成 summary ==========
    avg_score = sum(scores) / len(scores) if scores else 0
    wrong_count = sum(1 for e in enriched_evals if not e["correct"])

    if wrong_count == 0:
        summary = "全部回答正确，基础扎实！"
    elif wrong_count == 1:
        summary = f"基本掌握，{len(scores)} 题中有 1 题需要加强。"
    else:
        summary = f"整体掌握了基本概念，但 {wrong_count} 道题存在理解不到位，建议重点复习相关知识点。"

    if error_tags:
        top_tags = [et["tag"] for et in error_tags[:3]]
        summary += f" 薄弱知识点：{'、'.join(top_tags)}。"

    evaluation_result = EvaluationResult(
        score=round(avg_score, 1),
        summary=summary,
        details=[DetailItem(**d) for d in details],
        errorTags=[
            ErrorTag(
                tag=et.get("tag"),
                count=et.get("count", 0),
                sections=et.get("sections") or [],
            )
            for et in error_tags
        ],
    )

    return evaluation_result, diagnoses, enriched_evals_map


# ---- M3.1 + M4.4 拆分函数 4：持久化学习档案（短事务，只 flush）----

async def persist_learning_record(
    session,
    user_id: str,
    evaluation: EvaluationResult,
    diagnosis_drafts: List[dict],
    enriched_evals_map: dict,
    req: SubmitRequest,
    practice_session_obj: Optional[PracticeSession],
    submission_id: str,
    request_hash: str,
) -> LearningRecord:
    """在已开启的事务内写入 TestSession / TestAnswer / Diagnosis / UserMastery /
    MasteryEvent / ReviewTask / 更新 PracticeSession。

    只 flush，不 commit（由 session.begin() 上下文管理）。
    返回：LearningRecord（纯数据 DTO，从已 flush 的 ORM 对象重新序列化）。
    """
    mastery_service = get_mastery_service()

    # 6.1 创建测试会话
    test_session = TestSession(
        user_id=user_id,
        title=f"Test-{datetime.utcnow().strftime('%Y%m%d-%H%M')}",
        mode=req.mode or "learn",
        total_questions=len(req.answers),
        completed_questions=len(req.answers),
        score=evaluation.score,
        status="completed",
        completed_at=datetime.utcnow(),
        client_submission_id=submission_id,
        request_hash=request_hash,
        evaluation_snapshot=evaluation.model_dump(),
    )
    session.add(test_session)
    await session.flush()
    session_id = str(test_session.id)

    # 6.1.1 若关联了练习会话，标记为已完成并回写得分
    if practice_session_obj is not None:
        ps_result = await session.execute(
            select(PracticeSession).where(
                PracticeSession.id == req.practice_session_id,
                PracticeSession.user_id == user_id,
            )
        )
        ps_obj = ps_result.scalar_one_or_none()
        if ps_obj:
            ps_obj.status = "completed"
            ps_obj.score = evaluation.score
            ps_obj.completed_at = datetime.utcnow()

    # 6.2 保存每道题的作答记录
    answer_records = {}
    for ans in req.answers:
        ev = enriched_evals_map.get(ans.question_id, {})
        answer_record = TestAnswer(
            session_id=test_session.id,
            question_id=ans.question_id,
            answer_text=ans.user_answer,
            is_correct=ev.get("correct", False),
            score=ev.get("score", 0),
            error_type=ev.get("error_type"),
            feedback=ev.get("explanation", ""),
            error_tags=ev.get("error_tags", []),
        )
        session.add(answer_record)
        answer_records[ans.question_id] = answer_record

    await session.flush()

    # 6.3 保存诊断记录，并建立 question_id -> diagnosis_id 映射
    diagnosis_ids = {}
    for diag in diagnosis_drafts:
        qid = diag.get("questionId")
        answer_record = answer_records.get(qid)
        answer_id = str(answer_record.id) if answer_record else None

        diag_record = Diagnosis(
            answer_id=answer_id,
            question_id=qid,
            error_category=diag.get("error_category"),
            error_conclusion=diag.get("error_conclusion"),
            knowledge_point_ids=diag.get("knowledge_point_ids"),
            evidence_chunk_ids=diag.get("evidence_chunk_ids"),
            mastery_delta=diag.get("mastery_delta"),
            review_suggestions=diag.get("review_suggestions"),
        )
        session.add(diag_record)
        await session.flush()
        diagnosis_ids[qid] = str(diag_record.id)

    await session.flush()

    # 6.4 更新用户掌握度（逐题逐知识点，不是整场聚合）
    mastery_updates = {}
    for diag in diagnosis_drafts:
        qid = diag.get("questionId")
        answer_record = answer_records.get(qid)
        if not answer_record:
            continue

        mastery_delta = diag.get("mastery_delta", {})
        if not mastery_delta:
            continue

        # 评判服务不可用时，不更新掌握度（避免误判为答错）
        if diag.get("_eval_unavailable"):
            logger.warning(f"[test/submit] skipping mastery update for qid={qid}: evaluator unavailable")
            continue

        is_correct = answer_record.is_correct
        error_category = diag.get("error_category")
        error_pattern_id = diag.get("error_pattern_id")

        per_q_updates = await mastery_service.apply_mastery_delta(
            db=session,
            user_id=user_id,
            mastery_delta=mastery_delta,
            is_correct=is_correct,
            answer_id=str(answer_record.id),
            question_id=qid,
            error_category=error_category,
            error_pattern_id=error_pattern_id,
        )

        for kp_id, update in per_q_updates.items():
            mastery_updates[kp_id] = update

    # 6.5 生成复习任务
    all_weak_kp_ids = set()
    for diag in diagnosis_drafts:
        for kp_id in diag.get("weak_kp_ids", []):
            all_weak_kp_ids.add(str(kp_id))

    evidence_map = {}
    if all_weak_kp_ids:
        evidence_map = await mastery_service.get_evidence_chunks_for_kps(
            db=session,
            kp_ids=list(all_weak_kp_ids),
            limit_per_kp=3,
        )

    review_tasks = []
    for diag in diagnosis_drafts:
        if diag.get("error_category") and not diag.get("_eval_unavailable"):
            question_id = diag.get("questionId")
            diagnosis_id = diagnosis_ids.get(question_id)

            # 将 evidence_chunks 信息传入 diagnosis
            diag_evidence = {}
            for kp_id in diag.get("weak_kp_ids", []):
                chunks = evidence_map.get(str(kp_id), [])
                if chunks:
                    diag_evidence[str(kp_id)] = chunks
            if diag_evidence:
                diag["evidence_chunks"] = diag_evidence

            tasks = await mastery_service.create_review_tasks_from_diagnosis(
                db=session,
                user_id=user_id,
                diagnosis=diag,
                diagnosis_id=diagnosis_id,
                question_id=question_id,
                evidence_map=evidence_map,
            )
            review_tasks.extend(tasks)

    # 6.6 获取薄弱知识点
    weak_points = await mastery_service.get_weak_points(
        db=session,
        user_id=user_id,
        limit=5,
    )

    # 构建 LearningRecord（从已 flush 的 ORM 对象重新序列化）
    learning_record = LearningRecord(
        sessionId=session_id,
        diagnoses=list(diagnosis_drafts),
        masteryUpdates=mastery_updates,
        reviewTasks=review_tasks,
        weakPoints=weak_points,
    )

    # 回填 learning_record_snapshot（所有表 flush 后）
    test_session.learning_record_snapshot = learning_record.model_dump()
    await session.flush()

    logger.info(f"[test/submit] persisted session={session_id}")
    return learning_record


# ---- 响应构建函数 ----

def build_committed_response(submission_id, evaluation, learning_record):
    return {
        "submissionId": submission_id,
        "commitStatus": "committed",
        "retryable": False,
        "message": "学习记录已保存",
        "evaluation": evaluation.model_dump() if isinstance(evaluation, EvaluationResult) else evaluation,
        "learningRecord": learning_record.model_dump() if isinstance(learning_record, LearningRecord) else learning_record,
    }


def build_not_committed_response(submission_id, evaluation, msg=None):
    return {
        "submissionId": submission_id,
        "commitStatus": "not_committed",
        "retryable": True,
        "message": msg or "本次答案已完成即时评判，但学习记录未保存。请重新提交后再查看学习计划。",
        "evaluation": evaluation.model_dump() if isinstance(evaluation, EvaluationResult) else evaluation,
        "learningRecord": None,
    }


def build_outcome_unknown_response(submission_id, evaluation):
    return {
        "submissionId": submission_id,
        "commitStatus": "outcome_unknown",
        "retryable": False,
        "message": "提交结果暂时无法确认，请点击“查询提交状态”确认学习记录是否已保存。",
        "evaluation": evaluation.model_dump() if isinstance(evaluation, EvaluationResult) else evaluation,
        "learningRecord": None,
    }


# ---- Routes ----

@router.post("/submit")
async def submit_test(
    req: SubmitRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    提交测试答案，返回完整学习闭环结果（四态提交协议）。

    四态：
    - committed        : 学习档案已成功持久化
    - not_committed    : 评判完成但持久化失败（可重试）
    - outcome_unknown  : 持久化阶段连接异常，无法确认是否已提交
    - tracking_disabled: （仅 demo 路由使用）

    支持幂等：前端生成 submission_id，重复提交同内容直接回放快照，
    内容不一致返回 409。
    """
    submission_id = req.submission_id or str(uuid.uuid4())
    request_hash = compute_request_hash(req)

    # Step A: 加载题目 + 严格校验（失败抛 404/422/503，不返回 evaluation）
    questions, ps_obj, derived_file_path = await load_submission_questions(req, current_user)

    # Step B: 幂等检查（评判之前，避免重复消耗 LLM）
    if req.submission_id:
        async with async_session_factory() as check_session:
            existing = await check_idempotency(check_session, current_user.user_id, submission_id, request_hash)
            if existing is not None:
                eval_snap, lr_snap = existing
                return build_committed_response(submission_id, eval_snap, lr_snap)

    # Step C: 评判（事务外，纯计算）
    evaluation, diagnosis_drafts, enriched_evals_map = await evaluate_submission(
        questions,
        [(a, questions[a.question_id]) for a in req.answers if a.question_id in questions],
        derived_file_path,
    )

    # Step D: 持久化（短事务）
    try:
        learning_record = None
        async with async_session_factory() as session:
            try:
                async with session.begin():
                    learning_record = await persist_learning_record(
                        session, current_user.user_id, evaluation, diagnosis_drafts,
                        enriched_evals_map, req, ps_obj, submission_id, request_hash,
                    )
            except HTTPException:
                raise
            except IntegrityError as exc:
                raise ConcurrentSubmissionError() from exc
            except (OperationalError, InterfaceError) as exc:
                raise CommitUnknownError(str(exc)) from exc
            except Exception as exc:
                raise RetryablePersistenceError(str(exc)) from exc

        return build_committed_response(submission_id, evaluation, learning_record)

    except ConcurrentSubmissionError:
        # 并发重复提交：回查已存在的记录，命中则回放快照
        async with async_session_factory() as query_session:
            record = await check_idempotency(query_session, current_user.user_id, submission_id, request_hash)
            if record is not None:
                return build_committed_response(submission_id, record[0], record[1])
        return JSONResponse(status_code=503, content=build_not_committed_response(submission_id, evaluation))

    except CommitUnknownError as exc:
        logger.error(f"[test/submit] commit unknown: {exc}", exc_info=True)
        return JSONResponse(status_code=503, content=build_outcome_unknown_response(submission_id, evaluation))

    except RetryablePersistenceError as exc:
        logger.error(f"[test/submit] persist failed: {exc}", exc_info=True)
        return JSONResponse(status_code=503, content=build_not_committed_response(submission_id, evaluation, str(exc)))


@router.get("/submissions/{submission_id}")
async def get_submission_status(
    submission_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """查询提交状态，用于 outcome_unknown 恢复与刷新后对账。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(TestSession).where(
                TestSession.user_id == current_user.user_id,
                TestSession.client_submission_id == submission_id,
            )
        )
        existing = result.scalar_one_or_none()
        if not existing:
            return {
                "submissionId": submission_id,
                "found": False,
                "commitStatus": "not_committed",
                "evaluation": None,
                "learningRecord": None,
            }
        return {
            "submissionId": submission_id,
            "found": True,
            "commitStatus": "committed",
            "evaluation": existing.evaluation_snapshot,
            "learningRecord": existing.learning_record_snapshot,
        }


@router.get("/sessions")
async def list_sessions(current_user: CurrentUser = Depends(get_current_user)):
    """获取当前用户的测试会话列表"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TestSession)
                .where(TestSession.user_id == current_user.user_id)
                .order_by(TestSession.started_at.desc())
                .limit(20)
            )
            sessions = result.scalars().all()
            return [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "mode": s.mode,
                    "total_questions": s.total_questions,
                    "completed_questions": s.completed_questions,
                    "score": s.score,
                    "status": s.status,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in sessions
            ]
    except Exception as e:
        logger.warning(f"[test/sessions] DB error: {e}")
        return [
            {
                "id": "7d0c831e-d845-45d7-a69c-473791e14a45",
                "title": "Python 面试模拟 #1",
                "mode": "learn",
                "total_questions": 5,
                "completed_questions": 2,
                "score": None,
                "status": "in_progress",
                "started_at": "2026-06-18T10:00:00",
                "completed_at": None,
            }
        ]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """获取单个测试会话详情"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TestSession).where(
                    TestSession.id == session_id,
                    TestSession.user_id == current_user.user_id,
                )
            )
            s = result.scalar_one_or_none()
            if s:
                return {
                    "id": str(s.id),
                    "title": s.title,
                    "mode": s.mode,
                    "total_questions": s.total_questions,
                    "completed_questions": s.completed_questions,
                    "score": s.score,
                    "status": s.status,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
    except Exception as e:
        logger.warning(f"[test/session] DB error: {e}")
    return {"id": session_id, "message": "stub"}


@router.get("/sessions/{session_id}/answers")
async def list_answers(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """获取会话的所有作答记录（含诊断）"""
    try:
        async with async_session_factory() as session:
            # 用户隔离：通过 TestSession.user_id 校验会话归属
            ts_result = await session.execute(
                select(TestSession).where(
                    TestSession.id == session_id,
                    TestSession.user_id == current_user.user_id,
                )
            )
            if not ts_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="会话不存在或无权访问")

            result = await session.execute(
                select(TestAnswer)
                .where(TestAnswer.session_id == session_id)
                .order_by(TestAnswer.created_at.asc())
            )
            answers = result.scalars().all()
            return [
                {
                    "id": str(a.id),
                    "question_id": str(a.question_id),
                    "answer_text": a.answer_text,
                    "is_correct": a.is_correct,
                    "score": a.score,
                    "error_type": a.error_type,
                    "feedback": a.feedback,
                    "error_tags": a.error_tags,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in answers
            ]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[test/answers] DB error: {e}")
    return []
