"""
题目种子数据入库脚本

将前端 mockQuestions 中的题目写入 PostgreSQL questions 表。

用法:
    python scripts/seed_questions.py
    python scripts/seed_questions.py --file /docs/cs/os-memory.md
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 种子数据（来源：前端 mockData.js mockQuestions）
SEED_QUESTIONS = [
    # ---- os-memory.md ----
    {
        "file_path": "/docs/cs/os-memory.md",
        "questions": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "type": "single",
                "content": "以下哪种页面置换算法不会出现 Belady 异常？",
                "options": ["FIFO", "LRU", "Clock", "OPT"],
                "expected_answer": "LRU。LRU 和 OPT 都属于栈算法（Stack Algorithm），满足包含属性，不会出现 Belady 异常。FIFO 是最典型的会出现 Belady 异常的算法。",
                "tags": ["页面置换", "Belady异常"],
                "sections": ["操作系统内存管理", "页面置换算法"],
                "difficulty": "medium",
                "category": "页面置换算法",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "type": "text",
                "content": "进程切换时，x86 架构写入哪个寄存器会触发 TLB flush？",
                "expected_answer": "CR3 寄存器。写入 CR3 会使得所有 TLB 条目被刷新（除非启用 PCID）。这是因为 CR3 存储了页表基址，进程切换时必须更新它。",
                "options": None,
                "tags": ["TLB", "x86架构"],
                "sections": ["操作系统内存管理", "tlb 与缓存"],
                "difficulty": "medium",
                "category": "TLB 与缓存",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "type": "code",
                "content": "补全以下 Clock 页面置换算法的核心循环逻辑：",
                "expected_answer": "ref_bit[pointer] = 0。当 ref_bit 为 1 时，给予第二次机会：清除访问位并移动指针。遇到 ref_bit=0 时则换出该页面。",
                "options": None,
                "tags": ["页面置换", "Clock算法"],
                "sections": ["操作系统内存管理", "页面置换算法"],
                "difficulty": "hard",
                "category": "页面置换算法",
            },
        ],
    },
    # ---- react-fiber.md ----
    {
        "file_path": "/docs/frontend/react-fiber.md",
        "questions": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440004",
                "type": "single",
                "content": "React Fiber 架构中，两棵 Fiber 树通过哪个字段互相引用？",
                "options": ["return", "sibling", "alternate", "child"],
                "expected_answer": "alternate。React 维护两棵 Fiber 树（Current 和 Work-in-Progress），通过 alternate 指针互相引用，完成更新后角色互换。",
                "tags": ["Fiber", "双缓冲"],
                "sections": ["react fiber 架构深度解析", "双缓冲机制"],
                "difficulty": "medium",
                "category": "Fiber 节点结构",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440005",
                "type": "text",
                "content": "为什么 Fiber 架构被称为"协作式调度"？它与抢占式调度有什么区别？",
                "expected_answer": "Fiber 采用协作式调度，每个工作单元完成后主动检查是否需要让出主线程（yield），而不是被外部强制中断。抢占式调度由操作系统强制切换，不依赖任务主动释放。React 选择协作式是因为它能更好地控制渲染的一致性，避免在关键渲染步骤被中断。",
                "options": None,
                "tags": ["Fiber", "调度"],
                "sections": ["react fiber 架构深度解析", "时间切片 (time slicing)"],
                "difficulty": "hard",
                "category": "时间切片",
            },
        ],
    },
]


async def seed(db_url: str = None):
    """写入种子数据"""
    from app.database import async_session_factory
    from app.models import Question, Document
    from sqlalchemy import select

    created = 0
    updated = 0

    async with async_session_factory() as session:
        for doc_seed in SEED_QUESTIONS:
            file_path = doc_seed["file_path"]

            # 查找或创建 document
            result = await session.execute(
                select(Document).where(Document.file_path == file_path)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                title = os.path.basename(file_path).replace(".md", "")
                # 尝试从已知列表取标题
                title_map = {
                    "/docs/cs/os-memory.md": "操作系统内存管理",
                    "/docs/frontend/react-fiber.md": "React Fiber 架构深度解析",
                }
                title = title_map.get(file_path, title)

                doc = Document(
                    title=title,
                    content="",
                    file_type="md",
                    file_path=file_path,
                )
                session.add(doc)
                await session.flush()
                print(f"[seed] created document: {file_path}")

            for q_seed in doc_seed["questions"]:
                # 检查是否已存在
                result = await session.execute(
                    select(Question).where(Question.id == q_seed["id"])
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.content = q_seed["content"]
                    existing.expected_answer = q_seed["expected_answer"]
                    existing.type = q_seed["type"]
                    existing.options = q_seed["options"]
                    existing.tags = q_seed["tags"]
                    existing.sections = q_seed["sections"]
                    existing.difficulty = q_seed["difficulty"]
                    existing.category = q_seed["category"]
                    existing.document_id = doc.id
                    updated += 1
                else:
                    q = Question(
                        id=q_seed["id"],
                        document_id=doc.id,
                        content=q_seed["content"],
                        expected_answer=q_seed["expected_answer"],
                        type=q_seed["type"],
                        options=q_seed["options"],
                        tags=q_seed["tags"],
                        sections=q_seed["sections"],
                        difficulty=q_seed["difficulty"],
                        category=q_seed["category"],
                    )
                    session.add(q)
                    created += 1

        await session.commit()

    print(f"\n[seed] done: {created} created, {updated} updated")
    return created, updated


async def main():
    try:
        await seed()
    except Exception as e:
        print(f"[seed] error (expected if no PostgreSQL): {e}")
        print("[seed] skipping DB write, seed data is defined in code")


if __name__ == "__main__":
    asyncio.run(main())
