"""
种子数据入库脚本（完整知识体系版）

注入内容：
1. 知识点树（KnowledgePoint）
2. 知识点关系（KnowledgeRelation）
3. 文档 + 题目（原有内容增强）
4. 题目-知识点关联（QuestionKnowledgeLink）
5. 常见错误映射（common_mistakes）

用法:
    python scripts/seed_questions.py
    python scripts/seed_questions.py --file /docs/cs/os-memory.md
"""
import os
import sys
import asyncio
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def kp_id_to_uuid(kp_id: str) -> uuid.UUID:
    """将字符串知识点 ID 转换为稳定的 UUID（基于命名空间）"""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"agent-interview-system.kp.{kp_id}")


def rel_id_to_uuid(rel_source: str, rel_target: str, rel_type: str) -> uuid.UUID:
    """将关系信息转换为稳定的 UUID"""
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"agent-interview-system.rel.{rel_source}.{rel_target}.{rel_type}")


# ============== 知识点树 ==============
# 操作系统 → 内存管理 → 页面置换 / TLB / 虚拟内存
# 前端 → React → Fiber架构 → 双缓冲 / 调度 / 时间切片

SEED_KNOWLEDGE_POINTS = [
    # ---- 操作系统 ----
    {
        "id": "kp-os-root",
        "name": "操作系统",
        "level": 1,
        "path": "操作系统",
        "category": "计算机基础",
        "importance": 9,
        "children": [
            {
                "id": "kp-os-memory",
                "name": "内存管理",
                "level": 2,
                "path": "操作系统/内存管理",
                "category": "计算机基础",
                "importance": 9,
                "children": [
                    {
                        "id": "kp-os-tlb",
                        "name": "TLB 与地址转换",
                        "level": 3,
                        "path": "操作系统/内存管理/TLB 与地址转换",
                        "category": "计算机基础",
                        "importance": 8,
                        "description": "TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的翻译",
                    },
                    {
                        "id": "kp-os-page-replacement",
                        "name": "页面置换算法",
                        "level": 3,
                        "path": "操作系统/内存管理/页面置换算法",
                        "category": "计算机基础",
                        "importance": 8,
                        "description": "当内存不足时，选择哪个页面换出的策略，包括 FIFO、LRU、Clock、OPT 等",
                    },
                    {
                        "id": "kp-os-belady",
                        "name": "Belady 异常",
                        "level": 3,
                        "path": "操作系统/内存管理/Belady 异常",
                        "category": "计算机基础",
                        "importance": 6,
                        "description": "增加物理页框数反而导致缺页率上升的异常现象，FIFO 算法会出现",
                    },
                    {
                        "id": "kp-os-virtual-memory",
                        "name": "虚拟内存",
                        "level": 3,
                        "path": "操作系统/内存管理/虚拟内存",
                        "category": "计算机基础",
                        "importance": 9,
                        "description": "通过页表将虚拟地址映射到物理地址，为每个进程提供独立的地址空间",
                    },
                    {
                        "id": "kp-os-clock",
                        "name": "Clock 算法",
                        "level": 3,
                        "path": "操作系统/内存管理/Clock 算法",
                        "category": "计算机基础",
                        "importance": 7,
                        "description": "近似 LRU 的页面置换算法，通过循环扫描和访问位实现",
                    },
                    {
                        "id": "kp-os-cpu-cache",
                        "name": "CPU Cache",
                        "level": 3,
                        "path": "操作系统/内存管理/CPU Cache",
                        "category": "计算机基础",
                        "importance": 8,
                        "description": "CPU 与主存之间的高速缓存，存储指令和数据",
                    },
                ],
            },
        ],
    },
    # ---- 前端 / React ----
    {
        "id": "kp-fe-root",
        "name": "前端开发",
        "level": 1,
        "path": "前端开发",
        "category": "前端",
        "importance": 9,
        "children": [
            {
                "id": "kp-react-root",
                "name": "React",
                "level": 2,
                "path": "前端开发/React",
                "category": "前端",
                "importance": 9,
                "children": [
                    {
                        "id": "kp-fiber-arch",
                        "name": "Fiber 架构",
                        "level": 3,
                        "path": "前端开发/React/Fiber 架构",
                        "category": "前端",
                        "importance": 8,
                        "description": "React 16 引入的新协调引擎，将渲染工作拆分为可中断的小单元",
                    },
                    {
                        "id": "kp-fiber-double-buffer",
                        "name": "双缓冲机制",
                        "level": 3,
                        "path": "前端开发/React/Fiber 架构/双缓冲机制",
                        "category": "前端",
                        "importance": 7,
                        "description": "Current Tree 与 Work-in-Progress Tree 两棵树交替工作",
                    },
                    {
                        "id": "kp-fiber-scheduling",
                        "name": "调度优先级",
                        "level": 3,
                        "path": "前端开发/React/Fiber 架构/调度优先级",
                        "category": "前端",
                        "importance": 8,
                        "description": "根据任务优先级决定执行顺序的机制",
                    },
                    {
                        "id": "kp-fiber-time-slicing",
                        "name": "时间切片",
                        "level": 3,
                        "path": "前端开发/React/Fiber 架构/时间切片",
                        "category": "前端",
                        "importance": 8,
                        "description": "将长任务切分为多个小片，在浏览器空闲时间执行",
                    },
                ],
            },
        ],
    },
]

# ============== 知识点关系 ==============
SEED_KNOWLEDGE_RELATIONS = [
    # 易混淆关系
    {"source": "kp-os-tlb", "target": "kp-os-cpu-cache", "type": "confused_with", "strength": 0.9},
    # 前置关系
    {"source": "kp-os-page-replacement", "target": "kp-os-virtual-memory", "type": "prerequisite", "strength": 1.0},
    {"source": "kp-os-belady", "target": "kp-os-page-replacement", "type": "prerequisite", "strength": 0.8},
    {"source": "kp-os-clock", "target": "kp-os-page-replacement", "type": "prerequisite", "strength": 1.0},
    {"source": "kp-fiber-double-buffer", "target": "kp-fiber-arch", "type": "prerequisite", "strength": 1.0},
    {"source": "kp-fiber-time-slicing", "target": "kp-fiber-scheduling", "type": "prerequisite", "strength": 0.9},
]

# ============== 题目 + 知识点关联 + 常见错误 ==============
# common_mistakes 新格式：
# {
#     "id": "错误模式唯一ID",
#     "error_type": "concept_confusion | concept_missing | ...",
#     "cue_terms": ["用户答案中出现的错误关键词"],
#     "missing_terms": ["用户答案中缺失的正确关键词"],
#     "target_kp_ids": ["kp-os-tlb", ...],
#     "diagnostic_template": "诊断模板，可包含 {kp} 占位符"
# }
SEED_QUESTIONS = [
    # ---- os-memory.md ----
    {
        "file_path": "kb://default/cs/os-memory.md",
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
                "knowledge_links": [
                    {"kp_id": "kp-os-page-replacement", "role": "primary", "weight": 1.0},
                    {"kp_id": "kp-os-belady", "role": "primary", "weight": 0.9},
                    {"kp_id": "kp-os-virtual-memory", "role": "secondary", "weight": 0.3},
                ],
                "common_mistakes": [
                    {
                        "id": "belady-concept-confusion-fifo-lru",
                        "error_type": "concept_confusion",
                        "cue_terms": ["fifo", "先进先出"],
                        "missing_terms": ["lru", "最近最少使用", "栈算法"],
                        "target_kp_ids": ["kp-os-page-replacement", "kp-os-belady"],
                        "diagnostic_template": "混淆了 FIFO 和 LRU 的特性，FIFO 会出现 Belady 异常而 LRU 不会",
                    },
                    {
                        "id": "belady-missing-concept",
                        "error_type": "concept_missing",
                        "cue_terms": ["不会", "不知道"],
                        "missing_terms": ["belady", "异常", "增加页框", "缺页率"],
                        "target_kp_ids": ["kp-os-belady"],
                        "diagnostic_template": "不理解 Belady 异常的概念：增加物理页框数反而导致缺页率上升",
                    },
                ],
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "type": "text",
                "content": "TLB 的作用是什么？它与 CPU Cache 的区别在哪里？",
                "expected_answer": "TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的翻译，避免每次地址翻译都需要访问多级页表。它缓存的是 VPN→PFN 的映射关系。而 CPU Cache 缓存的是指令和数据的实际内容。两者在层次结构上互补：TLB 命中后，CPU 才能知道物理地址去访问 Cache。",
                "options": None,
                "tags": ["TLB", "虚拟内存", "MMU"],
                "sections": ["操作系统内存管理", "TLB 与缓存"],
                "difficulty": "medium",
                "category": "TLB 与缓存",
                "knowledge_links": [
                    {"kp_id": "kp-os-tlb", "role": "primary", "weight": 1.0},
                    {"kp_id": "kp-os-cpu-cache", "role": "distractor", "weight": 0.8},
                    {"kp_id": "kp-os-virtual-memory", "role": "secondary", "weight": 0.5},
                ],
                "common_mistakes": [
                    {
                        "id": "tlb-cache-confusion",
                        "error_type": "concept_confusion",
                        "cue_terms": ["缓存", "数据", "内容", "指令"],
                        "missing_terms": ["地址翻译", "vpn", "pfn", "mmu", "映射"],
                        "target_kp_ids": ["kp-os-tlb", "kp-os-cpu-cache"],
                        "diagnostic_template": "混淆了 TLB 和 CPU Cache 的作用：TLB 缓存的是地址映射关系，而非数据内容",
                    },
                    {
                        "id": "tlb-missing-concept",
                        "error_type": "concept_missing",
                        "cue_terms": ["加速", "缓存"],
                        "missing_terms": ["虚拟地址", "物理地址", "页表", "地址翻译"],
                        "target_kp_ids": ["kp-os-tlb"],
                        "diagnostic_template": "知道 TLB 是缓存，但不清楚它缓存的是虚拟地址到物理地址的映射关系",
                    },
                    {
                        "id": "tlb-incomplete-expression",
                        "error_type": "expression_problem",
                        "cue_terms": [],
                        "missing_terms": ["层次结构", "互补", "mmu"],
                        "target_kp_ids": ["kp-os-tlb"],
                        "diagnostic_template": "理解了 TLB 的基本作用，但未清晰描述与 CPU Cache 的层次互补关系",
                    },
                ],
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "type": "code",
                "content": "补全 Clock 算法的核心逻辑：当指针扫过一个访问位为 1 的页面时，应当如何处理？",
                "expected_answer": "将该页面的访问位 ref_bit 清零，指针前移。Clock 算法通过'给第二次机会'的方式近似 LRU：被访问过的页面暂时保留，遇到 ref_bit=0 的页面才替换出去。",
                "options": None,
                "tags": ["页面置换", "Clock算法"],
                "sections": ["操作系统内存管理", "页面置换算法"],
                "difficulty": "hard",
                "category": "页面置换算法",
                "knowledge_links": [
                    {"kp_id": "kp-os-clock", "role": "primary", "weight": 1.0},
                    {"kp_id": "kp-os-page-replacement", "role": "secondary", "weight": 0.6},
                ],
                "common_mistakes": [
                    {
                        "id": "clock-logic-error",
                        "error_type": "coding_error",
                        "cue_terms": ["替换", "换出", "移除"],
                        "missing_terms": ["访问位", "ref_bit", "清零", "第二次机会"],
                        "target_kp_ids": ["kp-os-clock"],
                        "diagnostic_template": "Clock 算法核心逻辑错误：遇到 ref_bit=1 的页面时应清除访问位并继续扫描，而非直接替换",
                    },
                    {
                        "id": "clock-application-error",
                        "error_type": "application_error",
                        "cue_terms": ["原理", "概念"],
                        "missing_terms": ["循环扫描", "近似lru", "指针"],
                        "target_kp_ids": ["kp-os-clock"],
                        "diagnostic_template": "理解 Clock 算法的大致原理，但无法正确实现核心逻辑",
                    },
                ],
            },
        ],
    },
    # ---- react-fiber.md ----
    {
        "file_path": "kb://default/frontend/react-fiber.md",
        "questions": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440004",
                "type": "single",
                "content": "React Fiber 架构中，两棵 Fiber 树通过哪个字段互相引用，实现无缝切换？",
                "options": ["return", "sibling", "alternate", "child"],
                "expected_answer": "alternate。alternate 指针在 Current Tree 和 Work-in-Progress Tree 之间建立双向引用，提交更新时两棵树角色互换。",
                "tags": ["Fiber", "双缓冲"],
                "sections": ["react fiber 架构深度解析", "双缓冲机制"],
                "difficulty": "medium",
                "category": "Fiber 节点结构",
                "knowledge_links": [
                    {"kp_id": "kp-fiber-double-buffer", "role": "primary", "weight": 1.0},
                    {"kp_id": "kp-fiber-arch", "role": "secondary", "weight": 0.5},
                ],
                "common_mistakes": [
                    {
                        "id": "fiber-alternate-confusion",
                        "error_type": "concept_confusion",
                        "cue_terms": ["return", "sibling", "child", "父节点", "子节点"],
                        "missing_terms": ["alternate", "双缓冲", "current", "work"],
                        "target_kp_ids": ["kp-fiber-double-buffer"],
                        "diagnostic_template": "混淆了 Fiber 节点的 alternate 字段与其他遍历字段（return/sibling/child）",
                    },
                ],
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440005",
                "type": "text",
                "content": "为什么 React 要从 Stack Reconciler 迁移到 Fiber Reconciler？解决了什么问题？",
                "expected_answer": "Stack Reconciler 是同步递归的，一旦开始就无法中断，导致大型应用渲染时主线程被长时间阻塞，表现为掉帧和输入延迟。Fiber Reconciler 将渲染切分为可中断的小单元（Fiber 节点），通过协作式调度在浏览器空闲时间内完成，从而保证帧率稳定。核心收益：可中断渲染、优先级调度、时间切片。",
                "options": None,
                "tags": ["Fiber", "调度"],
                "sections": ["react fiber 架构深度解析", "调度优先级"],
                "difficulty": "hard",
                "category": "调度优先级",
                "knowledge_links": [
                    {"kp_id": "kp-fiber-scheduling", "role": "primary", "weight": 1.0},
                    {"kp_id": "kp-fiber-time-slicing", "role": "primary", "weight": 0.9},
                    {"kp_id": "kp-fiber-arch", "role": "secondary", "weight": 0.5},
                ],
                "common_mistakes": [
                    {
                        "id": "fiber-stack-reconciler-missing",
                        "error_type": "concept_missing",
                        "cue_terms": ["fiber", "新", "升级"],
                        "missing_terms": ["stack", "递归", "同步", "阻塞", "无法中断"],
                        "target_kp_ids": ["kp-fiber-arch"],
                        "diagnostic_template": "不了解 Stack Reconciler 的核心问题：同步递归导致无法中断，长任务阻塞主线程",
                    },
                    {
                        "id": "fiber-incomplete-expression",
                        "error_type": "expression_problem",
                        "cue_terms": ["可中断", "调度"],
                        "missing_terms": ["时间切片", "优先级", "协作式", "空闲时间"],
                        "target_kp_ids": ["kp-fiber-scheduling", "kp-fiber-time-slicing"],
                        "diagnostic_template": "知道 Fiber 的可中断渲染，但遗漏了时间切片和优先级调度这两个关键机制",
                    },
                    {
                        "id": "fiber-reasoning-gap",
                        "error_type": "reasoning_gap",
                        "cue_terms": ["更好", "改进"],
                        "missing_terms": ["掉帧", "输入延迟", "帧率", "主线程"],
                        "target_kp_ids": ["kp-fiber-scheduling"],
                        "diagnostic_template": "知道 Fiber Reconciler 比 Stack Reconciler 更好，但说不清具体解决了什么问题（掉帧、输入延迟）",
                    },
                ],
            },
        ],
    },
]


async def seed_knowledge_points(session):
    """递归创建知识点树"""
    from app.models import KnowledgePoint
    from sqlalchemy import select

    created = 0
    updated = 0

    async def _create_recursive(kp_data, parent_id=None):
        nonlocal created, updated
        kp_id_str = kp_data["id"]
        kp_uuid = kp_id_to_uuid(kp_id_str)
        parent_uuid = kp_id_to_uuid(parent_id) if parent_id else None

        result = await session.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_uuid)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = kp_data["name"]
            existing.level = kp_data["level"]
            existing.path = kp_data["path"]
            existing.category = kp_data.get("category")
            existing.importance = kp_data.get("importance", 5)
            existing.description = kp_data.get("description")
            existing.parent_id = parent_uuid
            updated += 1
        else:
            kp = KnowledgePoint(
                id=kp_uuid,
                name=kp_data["name"],
                level=kp_data["level"],
                path=kp_data["path"],
                category=kp_data.get("category"),
                importance=kp_data.get("importance", 5),
                description=kp_data.get("description"),
                parent_id=parent_uuid,
            )
            session.add(kp)
            created += 1

        # 递归处理子节点
        for child in kp_data.get("children", []):
            await _create_recursive(child, parent_id=kp_id_str)

    for root in SEED_KNOWLEDGE_POINTS:
        await _create_recursive(root)

    await session.flush()
    return created, updated


async def seed_knowledge_relations(session):
    """创建知识点关系"""
    from app.models import KnowledgeRelation
    from sqlalchemy import select

    created = 0
    for rel in SEED_KNOWLEDGE_RELATIONS:
        source_uuid = kp_id_to_uuid(rel["source"])
        target_uuid = kp_id_to_uuid(rel["target"])
        result = await session.execute(
            select(KnowledgeRelation).where(
                KnowledgeRelation.source_id == source_uuid,
                KnowledgeRelation.target_id == target_uuid,
                KnowledgeRelation.relation_type == rel["type"],
            )
        )
        existing = result.scalar_one_or_none()
        if not existing:
            kr = KnowledgeRelation(
                id=rel_id_to_uuid(rel["source"], rel["target"], rel["type"]),
                source_id=source_uuid,
                target_id=target_uuid,
                relation_type=rel["type"],
                strength=rel.get("strength", 1.0),
            )
            session.add(kr)
            created += 1

    await session.flush()
    return created


async def seed_questions_and_links(session):
    """创建题目 + 题目-知识点关联"""
    from app.models import Question, Document, QuestionKnowledgeLink
    from sqlalchemy import select

    created_q = 0
    updated_q = 0
    created_links = 0

    for doc_seed in SEED_QUESTIONS:
        file_path = doc_seed["file_path"]

        # 查找或创建 document
        result = await session.execute(
            select(Document).where(Document.file_path == file_path)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            title = os.path.basename(file_path).replace(".md", "")
            title_map = {
                "kb://default/cs/os-memory.md": "操作系统内存管理",
                "kb://default/frontend/react-fiber.md": "React Fiber 架构深度解析",
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
            qid = q_seed["id"]
            result = await session.execute(
                select(Question).where(Question.id == qid)
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
                existing.common_mistakes = q_seed.get("common_mistakes")
                updated_q += 1
            else:
                q = Question(
                    id=qid,
                    document_id=doc.id,
                    content=q_seed["content"],
                    expected_answer=q_seed["expected_answer"],
                    type=q_seed["type"],
                    options=q_seed["options"],
                    tags=q_seed["tags"],
                    sections=q_seed["sections"],
                    difficulty=q_seed["difficulty"],
                    category=q_seed["category"],
                    common_mistakes=q_seed.get("common_mistakes"),
                )
                session.add(q)
                created_q += 1

            # 创建知识点关联
            for link in q_seed.get("knowledge_links", []):
                kp_uuid = kp_id_to_uuid(link["kp_id"])
                result = await session.execute(
                    select(QuestionKnowledgeLink).where(
                        QuestionKnowledgeLink.question_id == qid,
                        QuestionKnowledgeLink.knowledge_point_id == kp_uuid,
                    )
                )
                if not result.scalar_one_or_none():
                    qkl = QuestionKnowledgeLink(
                        question_id=qid,
                        knowledge_point_id=kp_uuid,
                        role=link.get("role", "primary"),
                        weight=link.get("weight", 1.0),
                    )
                    session.add(qkl)
                    created_links += 1

    await session.flush()
    return created_q, updated_q, created_links


async def seed(db_url: str = None):
    """写入完整种子数据"""
    from app.database import async_session_factory

    async with async_session_factory() as session:
        print("[seed] === Seeding Knowledge Points ===")
        kp_created, kp_updated = await seed_knowledge_points(session)
        print(f"[seed] knowledge points: {kp_created} created, {kp_updated} updated")

        print("[seed] === Seeding Knowledge Relations ===")
        rel_created = await seed_knowledge_relations(session)
        print(f"[seed] knowledge relations: {rel_created} created")

        print("[seed] === Seeding Questions & Links ===")
        q_created, q_updated, links_created = await seed_questions_and_links(session)
        print(f"[seed] questions: {q_created} created, {q_updated} updated")
        print(f"[seed] question-knowledge links: {links_created} created")

        await session.commit()

    print("\n[seed] all done!")
    return {
        "knowledge_points": (kp_created, kp_updated),
        "relations": rel_created,
        "questions": (q_created, q_updated),
        "links": links_created,
    }


async def main():
    try:
        await seed()
    except Exception as e:
        print(f"[seed] error (expected if no PostgreSQL): {e}")
        print("[seed] skipping DB write, seed data is defined in code")


if __name__ == "__main__":
    asyncio.run(main())
