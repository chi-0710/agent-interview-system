"""
AI 题目生成服务

功能：
1. 基于知识点/文档生成题目（选择题/简答题/代码题）
2. 选择题评估（纯规则，0 token）
3. 简答题/代码题评估（复用 evaluator.py）
"""
import logging
import json
from typing import List, Optional
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Question, KnowledgePoint, QuestionKnowledgeLink, DocumentChunk, ChunkKnowledgeLink
from app.services.structured_output import structured_chat
from app.services.evaluator import evaluate_answer, evaluate_code_answer

logger = logging.getLogger(__name__)


# ============== Pydantic 输出模型 ==============

class GeneratedQuestion(BaseModel):
    """AI 生成的单道题目"""
    content: str                           # 题目内容
    options: list[str]                     # 4个选项（选择题用）
    correct_option: int                    # 正确答案索引 (0-3)
    explanation: str                       # 正确答案详细解释
    option_explanations: list[str]         # 每个选项的解释
    difficulty: str = "medium"             # easy/medium/hard
    tags: list[str] = []                   # 知识点标签


class QuestionGenerationResult(BaseModel):
    """题目生成结果"""
    questions: list[GeneratedQuestion]     # 生成的题目列表


# ============== Prompt 模板 ==============

CHOICE_PROMPT_TEMPLATE = """你是一位资深技术面试官。请根据以下知识点和文档内容，生成 {count} 道{difficulty}难度的选择题。

要求：
1. 题目内容要具体，考察核心概念理解，不要泛泛而问
2. 提供 4 个选项（A/B/C/D），只有一个是正确答案
3. 干扰项要"似是而非"，考察常见误区，不要明显错误
4. 标准答案要给出选项字母 + 详细解释
5. 每个选项都要有简短说明（为什么对/为什么错）
6. 难度为 {difficulty}

知识点信息：
{kp_info}

关联文档片段：
{doc_chunks}

请严格按照以下 JSON 格式输出（不要输出其他内容）：
{{
  "questions": [
    {{
      "content": "题目内容",
      "options": ["选项A", "选项B", "选项C", "选项D"],
      "correct_option": 0,
      "explanation": "正确答案的详细解释",
      "option_explanations": ["A为什么对/错", "B为什么对/错", "C为什么对/错", "D为什么对/错"],
      "difficulty": "{difficulty}",
      "tags": ["相关知识点名称"]
    }}
  ]
}}
"""

TEXT_PROMPT_TEMPLATE = """你是一位资深技术面试官。请根据以下知识点和文档内容，生成 {count} 道{difficulty}难度的简答题。

要求：
1. 题目内容要具体，考察深度理解和分析能力
2. 标准答案要包含关键得分点和逻辑结构
3. 评分标准（rubric）要结构化：列出关键得分点和对应权重（总和为 1.0）
4. 常见错误模式要列出 2-3 种典型错误及其错误类型

知识点信息：
{kp_info}

关联文档片段：
{doc_chunks}

请严格按照以下 JSON 格式输出（不要输出其他内容）：
{{
  "questions": [
    {{
      "content": "题目内容",
      "expected_answer": "标准答案",
      "rubric": {{
        "key_points": [
          {{"point": "得分点描述", "weight": 0.3}}
        ]
      }},
      "common_mistakes": [
        {{
          "error_type": "concept_confusion",
          "description": "典型错误描述",
          "knowledge_point_ids": ["相关知识点ID"]
        }}
      ],
      "difficulty": "{difficulty}",
      "tags": ["相关知识点名称"]
    }}
  ]
}}
"""

CODE_PROMPT_TEMPLATE = """你是一位资深技术面试官。请根据以下知识点和文档内容，生成 {count} 道{difficulty}难度的代码题。

要求：
1. 题目要描述清晰的编程任务和需求
2. 提供函数签名或接口定义
3. 给出参考实现（可选）
4. 列出测试用例或验证条件
5. 常见错误模式要列出典型 bug

知识点信息：
{kp_info}

关联文档片段：
{doc_chunks}

请严格按照以下 JSON 格式输出（不要输出其他内容）：
{{
  "questions": [
    {{
      "content": "题目内容（包含函数签名和需求描述）",
      "expected_answer": "参考实现代码",
      "test_cases": [
        {{"input": "测试输入", "expected_output": "期望输出"}}
      ],
      "common_mistakes": [
        {{
          "error_type": "coding_error",
          "description": "典型 bug 描述",
          "knowledge_point_ids": ["相关知识点ID"]
        }}
      ],
      "difficulty": "{difficulty}",
      "tags": ["相关知识点名称"]
    }}
  ]
}}
"""


class QuestionGenerator:
    """题目生成器"""

    async def generate_questions(
        self,
        db: AsyncSession,
        user_id: str,
        source_type: str,
        source_id: str,
        question_type: str = "single",
        difficulty: str = "medium",
        count: int = 5,
    ) -> dict:
        """
        生成题目并写入数据库。

        Args:
            db: 数据库会话
            user_id: 用户 ID
            source_type: 来源类型 (knowledge_point | document | knowledge_base)
            source_id: 来源 ID
            question_type: 题型 (single | text | code)
            difficulty: 难度 (easy | medium | hard)
            count: 生成数量

        Returns:
            生成的题目列表和元信息
        """
        # 1. 加载上下文
        kp_info, doc_chunks = await self._load_context(db, source_type, source_id)

        # 2. 选择 Prompt 模板
        if question_type == "single":
            prompt_template = CHOICE_PROMPT_TEMPLATE
            output_model = QuestionGenerationResult
        elif question_type == "text":
            prompt_template = TEXT_PROMPT_TEMPLATE
            output_model = QuestionGenerationResult
        elif question_type == "code":
            prompt_template = CODE_PROMPT_TEMPLATE
            output_model = QuestionGenerationResult
        else:
            raise ValueError(f"不支持的题型: {question_type}")

        # 3. 构建 Prompt
        prompt = prompt_template.format(
            count=count,
            difficulty=difficulty,
            kp_info=kp_info,
            doc_chunks=doc_chunks,
        )

        # 4. 调用 LLM 生成
        try:
            result = await structured_chat(prompt, output_model)
        except Exception as e:
            logger.error(f"[question_generator] LLM generation failed: {e}", exc_info=True)
            raise ValueError(f"题目生成失败: {e}")

        if not result or not result.questions:
            raise ValueError("未生成任何题目，请重试")

        # 5. 写入数据库
        created_questions = []
        for q in result.questions:
            question = await self._save_question(
                db=db,
                user_id=user_id,
                question_data=q,
                question_type=question_type,
                source_type=source_type,
                source_id=source_id,
            )
            created_questions.append(question)

        return {
            "questions": created_questions,
            "count": len(created_questions),
            "source_type": source_type,
            "source_id": source_id,
            "message": f"已生成 {len(created_questions)} 道{question_type}题目并保存到题库",
        }

    async def _load_context(
        self,
        db: AsyncSession,
        source_type: str,
        source_id: str,
    ) -> tuple[str, str]:
        """
        根据来源类型加载上下文信息。

        Returns:
            (kp_info: str, doc_chunks: str)
        """
        kp_info = ""
        doc_chunks = ""

        if source_type == "knowledge_point":
            # 加载知识点信息
            kp_result = await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.id == source_id)
            )
            kp = kp_result.scalar_one_or_none()
            if kp:
                kp_info = f"名称: {kp.name}\n路径: {kp.path}\n描述: {kp.description or '无'}"

                # 加载关联文档片段（通过 knowledge_point_id）
                link_result = await db.execute(
                    select(ChunkKnowledgeLink.chunk_id).where(
                        ChunkKnowledgeLink.knowledge_point_id == source_id
                    ).limit(5)
                )
                chunk_ids = [row[0] for row in link_result.all()]
                if chunk_ids:
                    from app.models import DocumentChunk
                    chunks_result = await db.execute(
                        select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
                    )
                    chunks = chunks_result.scalars().all()
                    doc_chunks = "\n\n".join([
                        f"--- 片段 {i+1} ---\n{c.content[:500]}"
                        for i, c in enumerate(chunks)
                    ])

        elif source_type == "document":
            # 加载文档信息
            from app.models import Document, DocumentChunk
            doc_result = await db.execute(
                select(Document).where(Document.id == source_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                kp_info = f"文档标题: {doc.title}\n分类: {doc.category or '无'}"

                # 加载文档前几个 chunk
                chunks_result = await db.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.document_id == source_id
                    ).limit(5)
                )
                chunks = chunks_result.scalars().all()
                doc_chunks = "\n\n".join([
                    f"--- 片段 {i+1} ---\n{c.content[:500]}"
                    for i, c in enumerate(chunks)
                ])

        elif source_type == "knowledge_base":
            # 加载知识库信息
            from app.models import KnowledgeBase, Document, DocumentChunk
            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == source_id)
            )
            kb = kb_result.scalar_one_or_none()
            if kb:
                kp_info = f"知识库名称: {kb.name}\n描述: {kb.description or '无'}"

                # 加载知识库下文档的前几个 chunk
                docs_result = await db.execute(
                    select(Document.id).where(Document.knowledge_base_id == source_id).limit(3)
                )
                doc_ids = [row[0] for row in docs_result.all()]
                if doc_ids:
                    chunks_result = await db.execute(
                        select(DocumentChunk).where(
                            DocumentChunk.document_id.in_(doc_ids)
                        ).limit(10)
                    )
                    chunks = chunks_result.scalars().all()
                    doc_chunks = "\n\n".join([
                        f"--- 片段 {i+1} ---\n{c.content[:500]}"
                        for i, c in enumerate(chunks)
                    ])

        if not kp_info:
            raise ValueError(f"未找到来源: {source_type} / {source_id}")

        return kp_info, doc_chunks

    async def _save_question(
        self,
        db: AsyncSession,
        user_id: str,
        question_data: GeneratedQuestion,
        question_type: str,
        source_type: str,
        source_id: str,
    ) -> dict:
        """将生成的题目写入数据库"""
        question_id = str(uuid4())
        now = datetime.utcnow()

        # 根据题型构建 Question 对象
        question_kwargs = {
            "id": question_id,
            "content": question_data.content,
            "type": question_type,
            "difficulty": question_data.difficulty,
            "tags": question_data.tags,
            "owner_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        if question_type == "single":
            question_kwargs.update({
                "options": question_data.options,
                "correct_option": question_data.correct_option,
                "option_explanations": question_data.option_explanations,
                "expected_answer": question_data.explanation,
            })
        elif question_type == "text":
            question_kwargs.update({
                "expected_answer": getattr(question_data, "expected_answer", ""),
                "rubric": getattr(question_data, "rubric", None),
                "common_mistakes": getattr(question_data, "common_mistakes", None),
            })
        elif question_type == "code":
            question_kwargs.update({
                "expected_answer": getattr(question_data, "expected_answer", ""),
                "common_mistakes": getattr(question_data, "common_mistakes", None),
            })

        question = Question(**question_kwargs)
        db.add(question)
        await db.flush()

        # 关联知识点（如果有）
        if question_data.tags:
            await self._link_knowledge_points(db, question_id, question_data.tags)

        return {
            "id": question_id,
            "content": question_data.content,
            "type": question_type,
            "difficulty": question_data.difficulty,
            "options": question_data.options if question_type == "single" else None,
            "tags": question_data.tags,
        }

    async def _link_knowledge_points(
        self,
        db: AsyncSession,
        question_id: str,
        tags: List[str],
    ):
        """根据标签名称匹配并关联知识点"""
        # 尝试按名称匹配知识点
        result = await db.execute(
            select(KnowledgePoint.id).where(KnowledgePoint.name.in_(tags))
        )
        kp_ids = [row[0] for row in result.all()]

        for kp_id in kp_ids:
            link = QuestionKnowledgeLink(
                question_id=question_id,
                knowledge_point_id=kp_id,
            )
            db.add(link)

    def evaluate_single_choice(
        self,
        question: dict,
        user_answer: str,
    ) -> dict:
        """
        选择题评估：纯规则判断，不调用 LLM。

        Args:
            question: 题目字典，包含 correct_option、options、explanation 等
            user_answer: 用户回答（"A"/"B"/"C"/"D" 或 "0"/"1"/"2"/"3"）

        Returns:
            评估结果
        """
        # 解析用户选项
        user_option = _parse_option_index(user_answer)
        if user_option is None:
            raise ValueError(f"无效的选项: {user_answer}，请输入 A/B/C/D 或 0/1/2/3")

        correct_option = question.get("correct_option")
        if correct_option is None:
            raise ValueError("题目缺少 correct_option 字段")

        correct = user_option == correct_option

        return {
            "correct": correct,
            "score": 100 if correct else 0,
            "error_type": None if correct else "concept_confusion",
            "explanation": question.get("explanation", ""),
            "option_explanations": question.get("option_explanations", []),
            "error_tags": question.get("tags", []),
        }


def _parse_option_index(user_answer: str) -> Optional[int]:
    """将用户回答解析为选项索引 (0-3)"""
    answer = user_answer.strip().upper()

    # 字母形式
    if answer in ("A", "B", "C", "D"):
        return ord(answer) - ord("A")

    # 数字形式
    if answer in ("0", "1", "2", "3"):
        return int(answer)

    return None


def get_question_generator() -> QuestionGenerator:
    """获取题目生成器单例"""
    return QuestionGenerator()
