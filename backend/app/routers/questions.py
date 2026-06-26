"""题目管理路由

- GET  /api/questions           → 题目列表
- GET  /api/questions?file=xxx  → 按文件筛选题目
- POST /api/questions           → 创建题目
"""
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select, or_
import logging

from app.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("")
async def list_questions(
    file: str = Query(None, description="文档路径，如 /docs/cs/os-memory.md"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    获取题目列表。可选按 file_path 过滤。

    GET /api/questions?file=/docs/cs/os-memory.md
    """
    try:
        from app.database import async_session_factory
        from app.models import Question, Document

        async with async_session_factory() as session:
            if file:
                # 先查 document（用户隔离：只匹配自己的或共享的文档）
                doc_result = await session.execute(
                    select(Document).where(
                        Document.file_path == file,
                        or_(
                            Document.owner_id == current_user.user_id,
                            Document.owner_id == None,
                            Document.owner_id == "__shared__",
                        ),
                    )
                )
                doc = doc_result.scalar_one_or_none()
                if doc:
                    result = await session.execute(
                        select(Question).where(Question.document_id == doc.id)
                    )
                    questions = result.scalars().all()
                else:
                    questions = []
            else:
                # 用户隔离：只返回归属于当前用户文档的题目，以及无文档关联的共享题目
                user_doc_ids = select(Document.id).where(Document.owner_id == current_user.user_id)
                result = await session.execute(
                    select(Question).where(
                        or_(Question.document_id.in_(user_doc_ids), Question.document_id == None)
                    )
                )
                questions = result.scalars().all()

            return [
                {
                    "id": str(q.id),
                    "type": q.type or "text",
                    "question": q.content,
                    "options": q.options,
                    "answer": q.expected_answer,
                    "tags": q.tags or [],
                    "sections": q.sections or [],
                    "difficulty": q.difficulty,
                    "category": q.category,
                }
                for q in questions
            ]
    except Exception as e:
        # 回退：内置题库（无 PG 也能演示）
        logger = logging.getLogger(__name__)
        logger.warning(f"[questions] DB不可用，使用内置题库: {e}")
        if file == "/docs/cs/os-memory.md":
            return [
                {
                    "id": "q-os-1",
                    "type": "single",
                    "question": "以下哪种页面置换算法不会出现 Belady 异常？",
                    "options": ["FIFO", "LRU", "Clock", "OPT"],
                    "answer": "LRU。LRU 和 OPT（最优置换）都属于栈算法（Stack Algorithm），满足包含属性，增加物理页框数不会导致缺页异常增加。FIFO 是典型会出现 Belady 异常的算法。",
                    "tags": ["页面置换", "Belady异常"],
                    "sections": ["操作系统内存管理", "页面置换算法"],
                    "difficulty": "medium",
                    "category": "页面置换算法",
                },
                {
                    "id": "q-os-2",
                    "type": "text",
                    "question": "TLB 的作用是什么？它与 CPU Cache 的区别在哪里？",
                    "answer": "TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的翻译，避免每次地址翻译都需要访问多级页表。它缓存的是 VPN→PFN 的映射关系。而 CPU Cache 缓存的是指令和数据的实际内容。两者在层次结构上互补：TLB 命中后，CPU 才能知道物理地址去访问 Cache。",
                    "tags": ["TLB", "虚拟内存", "MMU"],
                    "sections": ["操作系统内存管理", "TLB 与缓存"],
                    "difficulty": "medium",
                    "category": "TLB 与缓存",
                },
                {
                    "id": "q-os-3",
                    "type": "code",
                    "question": "补全 Clock 算法的核心逻辑：当指针扫过一个访问位为 1 的页面时，应当如何处理？",
                    "answer": "将该页面的访问位 ref_bit 清零，指针前移。Clock 算法通过\"给第二次机会\"的方式近似 LRU：被访问过的页面暂时保留，遇到 ref_bit=0 的页面才替换出去。",
                    "tags": ["页面置换", "Clock算法"],
                    "sections": ["操作系统内存管理", "页面置换算法"],
                    "difficulty": "hard",
                    "category": "页面置换算法",
                },
            ]
        elif file == "/docs/frontend/react-fiber.md":
            return [
                {
                    "id": "q-react-1",
                    "type": "single",
                    "question": "React Fiber 架构中，两棵 Fiber 树通过哪个字段互相引用，实现无缝切换？",
                    "options": ["return", "sibling", "alternate", "child"],
                    "answer": "alternate。alternate 指针在 Current Tree 和 Work-in-Progress Tree 之间建立双向引用，提交更新时两棵树角色互换。",
                    "tags": ["Fiber", "双缓冲"],
                    "sections": ["react fiber 架构深度解析", "双缓冲机制"],
                    "difficulty": "medium",
                    "category": "Fiber 节点结构",
                },
                {
                    "id": "q-react-2",
                    "type": "text",
                    "question": "为什么 React 要从 Stack Reconciler 迁移到 Fiber Reconciler？解决了什么问题？",
                    "answer": "Stack Reconciler 是同步递归的，一旦开始就无法中断，导致大型应用渲染时主线程被长时间阻塞，表现为掉帧和输入延迟。Fiber Reconciler 将渲染切分为可中断的小单元（Fiber 节点），通过协作式调度在浏览器空闲时间内完成，从而保证帧率稳定。核心收益：可中断渲染、优先级调度、时间切片。",
                    "tags": ["Fiber", "调度"],
                    "sections": ["react fiber 架构深度解析", "调度优先级"],
                    "difficulty": "hard",
                    "category": "调度优先级",
                },
            ]
        # 默认回退到少量题目
        return [
            {
                "id": "q-fallback-1",
                "type": "text",
                "question": "请用你自己的话简述当前文档的核心思想。",
                "answer": "核心思想是将复杂系统拆解为可管理的子模块，通过清晰的数据结构和调度算法保证性能与可维护性。",
                "tags": ["概念理解"],
                "sections": [],
                "difficulty": "easy",
                "category": "概念理解",
            },
        ]


@router.get("/{question_id}")
async def get_question(question_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """获取单个题目"""
    try:
        from app.database import async_session_factory
        from app.models import Question, Document

        async with async_session_factory() as session:
            # 用户隔离：题目关联的文档须为当前用户所有，或为共享题目（document_id 为空）
            result = await session.execute(
                select(Question).where(
                    Question.id == question_id,
                    or_(
                        Question.document_id == None,
                        Question.document_id.in_(
                            select(Document.id).where(Document.owner_id == current_user.user_id)
                        ),
                    ),
                )
            )
            q = result.scalar_one_or_none()
            if q:
                return {
                    "id": str(q.id),
                    "type": q.type or "text",
                    "question": q.content,
                    "options": q.options,
                    "answer": q.expected_answer,
                    "tags": q.tags or [],
                    "sections": q.sections or [],
                    "difficulty": q.difficulty,
                    "category": q.category,
                }
    except Exception:
        pass
    return {"id": question_id, "message": "stub"}


@router.post("")
async def create_question():
    """创建题目（stub）"""
    return {"message": "请使用 scripts/seed_questions.py 写入题目"}
