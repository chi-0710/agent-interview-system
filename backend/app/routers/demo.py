"""演示路由

仅用于无 DB 环境的快速验证与未来"试做一道题"的营销页。
不访问数据库,不持久化任何学习档案。

- POST /api/demo/test/submit → 仅规则评判,返回 tracking_disabled
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])


# ---- Models(与正式接口保持结构一致,但独立定义,避免耦合)----

class AnswerItem(BaseModel):
    question_id: str
    user_answer: str

    @field_validator("question_id")
    @classmethod
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("question_id 不能为空")
        return v.strip()


class DemoSubmitRequest(BaseModel):
    answers: List[AnswerItem] = []
    mode: Optional[str] = "learn"

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


# ---- 内置题库(从原 test.py 搬迁)----

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
    """规则判题:在没有 LLM 时使用关键词匹配打分。"""
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

    # 单选题:匹配 options 中的正确答案关键词
    if q_type == "single":
        first_word = user.split()[0] if user.split() else user
        expected_tokens = expected.split("。")[0].lower()
        if first_word in expected_tokens or any(tok in user for tok in expected_tokens.split()[:3]):
            correct = True
            score = 95
            explanation = "选项正确,关键词匹配到位。"
        else:
            score = 30
            error_tags = question.get("tags", [])
            explanation = f"答错了。要点:{expected.split('。')[0]}。"

    # 简答题:关键词覆盖度
    elif q_type in ("text", "code"):
        keywords = []
        for tag in question.get("tags", []):
            keywords.append(tag.lower())
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
            explanation = f"答对了 {coverage*100:.0f}% 的要点(命中 {hit}/{len(keywords)} 个关键词)。"
        else:
            score = int(coverage * 80)
            error_tags = question.get("tags", [])
            explanation = f"只命中了 {hit}/{len(keywords)} 个关键概念,建议回到对应章节复习。"

    return {
        "correct": correct,
        "score": score,
        "error_type": (None if correct else "概念混淆"),
        "explanation": explanation,
        "error_tags": ([] if correct else error_tags),
    }


@router.post("/test/submit")
async def demo_submit_test(
    req: DemoSubmitRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """演示模式提交:仅规则评判,不访问 DB,不持久化。

    返回 commitStatus: "tracking_disabled",learningRecord: null。
    """
    # 仅使用内置题库
    questions = {qid: IN_MEMORY_QUESTIONS.get(qid) for qid in [a.question_id for a in req.answers]}
    questions = {k: v for k, v in questions.items() if v}

    if not questions:
        # 演示模式下找不到题目也返回 tracking_disabled,不抛 404(避免演示链路依赖 DB)
        return {
            "submissionId": str(uuid.uuid4()),
            "commitStatus": "tracking_disabled",
            "retryable": False,
            "message": "演示模式未找到对应题目,不保存学习档案。",
            "evaluation": {
                "score": 0,
                "summary": "演示模式未找到对应题目。",
                "details": [],
                "errorTags": [],
            },
            "learningRecord": None,
        }

    # 规则评判
    answer_map = [(ans, questions[ans.question_id]) for ans in req.answers if ans.question_id in questions]
    eval_results = [_score_by_rules(q, ans.user_answer) for (ans, q) in answer_map]

    # 构建即时评判结果
    details = []
    scores = []
    error_tag_map = {}
    for i, (ans, q) in enumerate(answer_map):
        result_dict = eval_results[i]
        correct = result_dict.get("correct", False)
        score = result_dict.get("score", 0)
        scores.append(score)

        details.append({
            "questionId": ans.question_id,
            "correct": correct,
            "errorType": result_dict.get("error_type"),
            "explanation": result_dict.get("explanation", ""),
        })

        if not correct:
            for tag in result_dict.get("error_tags", []):
                if tag not in error_tag_map:
                    error_tag_map[tag] = {"tag": tag, "count": 0, "sections": q.get("sections", [])}
                error_tag_map[tag]["count"] += 1

    avg_score = sum(scores) / len(scores) if scores else 0
    wrong_count = sum(1 for s in scores if s < 60)

    if wrong_count == 0:
        summary = "全部回答正确,基础扎实!"
    elif wrong_count == 1:
        summary = f"基本掌握,{len(scores)} 题中有 1 题需要加强。"
    else:
        summary = f"整体掌握了基本概念,但 {wrong_count} 道题存在理解不到位,建议重点复习相关知识点。"

    return {
        "submissionId": str(uuid.uuid4()),
        "commitStatus": "tracking_disabled",
        "retryable": False,
        "message": "演示练习,不保存学习档案。",
        "evaluation": {
            "score": round(avg_score, 1),
            "summary": summary,
            "details": details,
            "errorTags": list(error_tag_map.values()),
        },
        "learningRecord": None,
    }
