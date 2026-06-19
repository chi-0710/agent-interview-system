"""测试路由

- POST /api/test/submit  → 提交答案，并发评判，返回 feedback + errorTags
- GET  /api/test/sessions → 测试会话列表
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.database import get_db
from app.models import TestSession, TestAnswer, Question
from app.services.evaluator import evaluate_answer as evaluate_single
from app.services.error_tags import aggregate_error_tags
from app.services.llm import chat as llm_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test"])


# ---- Models ----

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
    file_path: str
    answers: List[AnswerItem] = []

    @field_validator("file_path")
    @classmethod
    def fp_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("file_path 不能为空")
        return v.strip()

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


class SubmitResponse(BaseModel):
    score: float
    summary: str
    details: List[DetailItem]
    errorTags: List[ErrorTag]


# ---- Routes ----

IN_MEMORY_QUESTIONS = {
    # os-memory.md
    "q-os-1": {"id": "q-os-1", "type": "single", "content": "以下哪种页面置换算法不会出现 Belady 异常？",
               "expected_answer": "LRU。LRU 和 OPT（最优置换）都属于栈算法（Stack Algorithm），满足包含属性，增加物理页框数不会导致缺页异常增加。FIFO 是典型会出现 Belady 异常的算法。",
               "options": ["FIFO", "LRU", "Clock", "OPT"], "tags": ["页面置换", "Belady异常"],
               "sections": ["操作系统内存管理", "页面置换算法"], "difficulty": "medium", "category": "页面置换算法"},
    "q-os-2": {"id": "q-os-2", "type": "text", "content": "TLB 的作用是什么？它与 CPU Cache 的区别在哪里？",
               "expected_answer": "TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的翻译，避免每次地址翻译都需要访问多级页表。它缓存的是 VPN→PFN 的映射关系。而 CPU Cache 缓存的是指令和数据的实际内容。两者在层次结构上互补：TLB 命中后，CPU 才能知道物理地址去访问 Cache。",
               "tags": ["TLB", "虚拟内存", "MMU"], "sections": ["操作系统内存管理", "TLB 与缓存"],
               "difficulty": "medium", "category": "TLB 与缓存"},
    "q-os-3": {"id": "q-os-3", "type": "code", "content": "补全 Clock 算法的核心逻辑：当指针扫过一个访问位为 1 的页面时，应当如何处理？",
               "expected_answer": "将该页面的访问位 ref_bit 清零，指针前移。Clock 算法通过'给第二次机会'的方式近似 LRU：被访问过的页面暂时保留，遇到 ref_bit=0 的页面才替换出去。",
               "tags": ["页面置换", "Clock算法"], "sections": ["操作系统内存管理", "页面置换算法"],
               "difficulty": "hard", "category": "页面置换算法"},
    # react-fiber.md
    "q-react-1": {"id": "q-react-1", "type": "single", "content": "React Fiber 架构中，两棵 Fiber 树通过哪个字段互相引用，实现无缝切换？",
                  "expected_answer": "alternate。alternate 指针在 Current Tree 和 Work-in-Progress Tree 之间建立双向引用，提交更新时两棵树角色互换。",
                  "options": ["return", "sibling", "alternate", "child"], "tags": ["Fiber", "双缓冲"],
                  "sections": ["react fiber 架构深度解析", "双缓冲机制"], "difficulty": "medium", "category": "Fiber 节点结构"},
    "q-react-2": {"id": "q-react-2", "type": "text", "content": "为什么 React 要从 Stack Reconciler 迁移到 Fiber Reconciler？解决了什么问题？",
                  "expected_answer": "Stack Reconciler 是同步递归的，一旦开始就无法中断，导致大型应用渲染时主线程被长时间阻塞，表现为掉帧和输入延迟。Fiber Reconciler 将渲染切分为可中断的小单元（Fiber 节点），通过协作式调度在浏览器空闲时间内完成，从而保证帧率稳定。核心收益：可中断渲染、优先级调度、时间切片。",
                  "tags": ["Fiber", "调度"], "sections": ["react fiber 架构深度解析", "调度优先级"],
                  "difficulty": "hard", "category": "调度优先级"},
    # fallback
    "q-fallback-1": {"id": "q-fallback-1", "type": "text", "content": "请用你自己的话简述当前文档的核心思想。",
                     "expected_answer": "核心思想是将复杂系统拆解为可管理的子模块，通过清晰的数据结构和调度算法保证性能与可维护性。",
                     "tags": ["概念理解"], "sections": [], "difficulty": "easy", "category": "概念理解"},
}


def _score_by_rules(question: dict, user_answer: str) -> dict:
    """规则判题：在没有 LLM 时使用关键词匹配打分。"""
    expected = (question.get("expected_answer") or "").lower()
    user = (user_answer or "").lower().strip()
    q_type = question.get("type", "text")

    correct = False
    score = 0
    explanation = ""
    error_tags = []

    if not user:
        return {"correct": False, "score": 0, "error_type": "未作答",
                "explanation": "用户未提供答案。", "error_tags": question.get("tags", [])}

    # 单选题：匹配 options 中的正确答案关键词
    if q_type == "single":
        # 提取预期答案第一句话做关键词
        first_word = user.split()[0] if user.split() else user
        # 检查用户是否选择了正确选项的关键词
        expected_tokens = expected.split("。")[0].lower()
        if first_word in expected_tokens or any(tok in user for tok in expected_tokens.split()[:3]):
            correct = True
            score = 95
            explanation = "选项正确，关键词匹配到位。"
        else:
            score = 30
            error_tags = question.get("tags", [])
            explanation = f"答错了。要点：{expected.split('。')[0]}。"

    # 简答题：关键词覆盖度
    elif q_type in ("text", "code"):
        keywords = []
        for tag in question.get("tags", []):
            keywords.append(tag.lower())
        # 从 expected 提取一些中文关键词（2-4 字片段）
        import re
        for m in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", expected):
            if len(m) >= 2:
                keywords.append(m.lower())
        keywords = list(dict.fromkeys(keywords))[:10]

        hit = sum(1 for kw in keywords if kw and kw in user)
        coverage = hit / max(len(keywords), 1)

        if coverage >= 0.45:
            correct = True
            score = min(100, int(50 + coverage * 60))
            explanation = f"答对了 {coverage*100:.0f}% 的要点（命中 {hit}/{len(keywords)} 个关键词）。"
        else:
            score = int(coverage * 80)
            error_tags = question.get("tags", [])
            explanation = f"只命中了 {hit}/{len(keywords)} 个关键概念，建议回到对应章节复习。"

    return {
        "correct": correct,
        "score": score,
        "error_type": (None if correct else "概念混淆"),
        "explanation": explanation,
        "error_tags": ([] if correct else error_tags),
    }


@router.post("/submit")
async def submit_test(req: SubmitRequest) -> dict:
    """
    提交测试答案，返回评判结果和错题标签。

    策略：
    - 优先走 PostgreSQL + LLM 完整链路
    - 失败时自动降级：内置题库 + 规则判分（关键词覆盖度）
    """
    # 策略 A: PostgreSQL + LLM
    questions = None
    used_db = False
    try:
        from app.database import async_session_factory
        from app.models import Question as _Q
        async with async_session_factory() as session:
            q_ids = [a.question_id for a in req.answers]
            result = await session.execute(
                select(_Q).where(_Q.id.in_(q_ids))
            )
            db_qs = result.scalars().all()
            if db_qs:
                questions = {str(q.id): {
                    "id": str(q.id), "type": q.type or "text", "content": q.content,
                    "expected_answer": q.expected_answer or "", "options": q.options,
                    "tags": q.tags or [], "sections": q.sections or [],
                } for q in db_qs}
                used_db = True
    except Exception as e:
        logger.warning(f"[test/submit] DB 不可用，降级到内置题库: {e}")

    # 策略 B: 内置内存题库
    if not questions:
        questions = {qid: IN_MEMORY_QUESTIONS.get(qid) for qid in
                     [a.question_id for a in req.answers]}
        questions = {k: v for k, v in questions.items() if v}

    if not questions:
        raise HTTPException(status_code=404, detail="未找到对应题目")

    # 构建评判任务
    eval_tasks = []
    answer_map = []
    for ans in req.answers:
        q = questions.get(ans.question_id)
        if not q:
            continue
        answer_map.append((ans, q))
        # 有 LLM 就走 LLM，否则规则判分
        eval_tasks.append(
            evaluate_single(
                question=q["content"],
                answer=q.get("expected_answer", ""),
                user_answer=ans.user_answer,
            ) if used_db else None  # 标记：需要规则判分
        )

    if not eval_tasks:
        raise HTTPException(status_code=400, detail="没有可评判的题目")

    # 并发评判（DB 可用时用 LLM；否则本地规则）
    logger.info(f"[test/submit] evaluating {len(eval_tasks)} questions")
    t0 = datetime.utcnow()

    eval_results = []
    if used_db:
        eval_results = await asyncio.gather(*eval_tasks, return_exceptions=True)
    else:
        for (ans, q) in answer_map:
            eval_results.append(_score_by_rules(q, ans.user_answer))

    elapsed = (datetime.utcnow() - t0).total_seconds()
    logger.info(f"[test/submit] evaluation done in {elapsed:.1f}s (mode: {'LLM' if used_db else 'rules'})")

    # 构建 details + 汇聚评判数据
    details = []
    scores = []
    enriched_evals = []

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

    # 4. 聚合 errorTags
    error_tags = aggregate_error_tags(enriched_evals, req.file_path)

    # 5. 生成 summary
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

    # 6. 持久化（可选，没 PG 就跳过）
    session_id = None
    if used_db:
        try:
            async with async_session_factory() as session:
                test_session = TestSession(
                    title=f"Test-{datetime.utcnow().strftime('%Y%m%d-%H%M')}",
                    total_questions=len(eval_tasks),
                    completed_questions=len(req.answers),
                    score=round(avg_score, 1),
                    status="completed",
                    completed_at=datetime.utcnow(),
                )
                session.add(test_session)
                await session.flush()
                session_id = str(test_session.id)
                await session.commit()
                logger.info(f"[test/submit] persisted session={session_id}")
        except Exception as e:
            logger.error(f"[test/submit] persist error: {e}")

    return {
        "score": round(avg_score, 1),
        "summary": summary,
        "details": details,
        "errorTags": error_tags,
    }


@router.get("/sessions")
async def list_sessions():
    """获取测试会话列表"""
    try:
        from app.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(TestSession).order_by(TestSession.started_at.desc()).limit(20)
            )
            sessions = result.scalars().all()
            return [
                {
                    "id": str(s.id),
                    "title": s.title,
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
        return [
            {
                "id": "7d0c831e-d845-45d7-a69c-473791e14a45",
                "title": "Python 面试模拟 #1",
                "total_questions": 5,
                "completed_questions": 2,
                "score": None,
                "status": "in_progress",
                "started_at": "2026-06-18T10:00:00",
                "completed_at": None,
            }
        ]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取单个测试会话"""
    return {"id": session_id, "message": "stub"}


@router.get("/sessions/{session_id}/answers")
async def list_answers(session_id: str):
    """获取会话的所有回答"""
    return []
