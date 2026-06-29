"""AI Copilot 路由

提供 SSE 流式接口：
- POST /api/copilot/explain  → 划线伴读解释
- POST /api/copilot/chat     → 自由对话（保留兼容，复用同一个模式）
- POST /api/copilot/generate-questions  → AI 生成题目
- POST /api/copilot/evaluate-answer     → AI 评估回答（自动选择评估策略）
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.dependencies import CurrentUser, get_current_user
from app.services.copilot import explain_stream, chat_stream
from app.database import async_session_factory
from app.services.question_generator import get_question_generator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


# ---- Request/Response Models ----

class ExplainRequest(BaseModel):
    selected_text: str
    file_path: str
    knowledge_base_id: Optional[str] = None
    headers: list[str] = []
    block_context: Optional[str] = None  # 新增：前端提取的完整段落上下文
    session_id: Optional[str] = None  # 会话 ID，用于多轮对话记忆

    @field_validator("selected_text")
    @classmethod
    def selected_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("selected_text 不能为空")
        return v.strip()

    @field_validator("file_path")
    @classmethod
    def file_path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("file_path 不能为空")
        return v.strip()


class ChatRequest(BaseModel):
    message: str
    file_path: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    session_id: Optional[str] = None  # 新增：会话 ID，用于记忆管理

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message 不能为空")
        return v.strip()


# ---- SSE Helper ----

async def _sse_event(event_type: str, content: str = ""):
    """生成一个 SSE 事件帧"""
    data = json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
    return f"data: {data}\n\n"


# ---- Routes ----

@router.post("/explain")
async def explain(request: ExplainRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    划线伴读解释（SSE 流式）

    策略：
    - 优先走 ChromaDB + LLM 完整链路
    - 失败时自动降级到本地关键词匹配 + 模板化解释
    """

    async def fallback_explain_stream(selected_text, file_path, headers):
        """本地降级解释：基于知识库文件做 TF-IDF 关键词匹配，生成模板化解释。"""
        # 读取文件内容
        full_text = ""
        file_path_on_disk = None
        try:
            from app.routers.documents import _locate_markdown
            file_path_on_disk = _locate_markdown(file_path)
            with open(file_path_on_disk, "r", encoding="utf-8") as f:
                full_text = f.read()
        except Exception:
            full_text = ""

        # 从 selected_text 提取关键词
        import re
        def tokens(s: str):
            return [t for t in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", s or "") if len(t) >= 2]

        sel_tokens = tokens(selected_text)
        header_tokens = []
        for h in headers or []:
            header_tokens.extend(tokens(h))
        all_tokens = list(dict.fromkeys(sel_tokens + header_tokens))

        # 在文档中找包含最多关键词的段落
        paragraphs = []
        if full_text:
            for p in re.split(r"\n\s*\n", full_text):
                p = p.strip()
                if 10 < len(p) < 500:
                    hit = sum(1 for t in all_tokens if t and t in p)
                    if hit > 0:
                        paragraphs.append((hit, p))
            paragraphs.sort(key=lambda x: x[0], reverse=True)
        top_paragraphs = paragraphs[:1]

        # 生成解释（按 token 流式 yield 假装"流式"）
        intro = f"【划线伴读 · 本地检索模式】你在「{file_path}」中选择了：「{selected_text[:40]}…」"
        if top_paragraphs:
            body = f"\n\n在对应章节，文档是这样描述的：\n\n{top_paragraphs[0][1]}"
        else:
            body = f"\n\n当前文档未找到精确匹配段落。建议结合上下文（{', '.join(headers[-2:]) if headers else '整章'}）理解。"
        note = "\n\n📘 提示：若需更深入的解释，可在后端配置 LLM API Key 启用 AI 生成。"
        full = intro + body + note

        # 按字符/词块流式输出（模拟 80ms/块，让前端有流式感）
        import asyncio
        for i in range(0, len(full), 16):
            await asyncio.sleep(0.04)
            yield full[i:i+16]

    async def event_generator():
        # 先尝试正常链路
        tried_main = False
        try:
            # 检查 chromadb 是否可用（lazy import 会失败 → 立即降级）
            from app.services.copilot import explain_stream
            # 确认 LLM 可用
            from app.services.llm import is_available
            if not is_available():
                raise RuntimeError("LLM unavailable")
            tried_main = True
            async for token in explain_stream(
                selected_text=request.selected_text,
                file_path=request.file_path,
                headers=request.headers,
                block_context=request.block_context,
                knowledge_base_id=request.knowledge_base_id,
                session_id=request.session_id,
                user_id=current_user.user_id,
            ):
                yield await _sse_event("chunk", token)
            yield await _sse_event("done")
        except Exception as e:
            # 降级
            if tried_main:
                logger.warning(f"[copilot/explain] 主链路失败，降级到本地检索: {e}")
            else:
                logger.warning(f"[copilot/explain] chromadb/LLM 不可用，降级到本地检索: {e}")
            try:
                async for token in fallback_explain_stream(
                    request.selected_text,
                    request.file_path,
                    request.headers,
                ):
                    yield await _sse_event("chunk", token)
                yield await _sse_event("done")
            except Exception as e2:
                logger.exception(f"[copilot/explain] fallback error: {e2}")
                yield await _sse_event("error", f"解释出错：{str(e2)}")
                yield await _sse_event("done")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def copilot_chat(request: ChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    自由对话（SSE 流式）

    请求体：
        {"message": "什么是 Belady 异常？", "file_path": "/docs/cs/os-memory.md", "session_id": "可选"}
    """

    async def event_generator():
        try:
            async for token in chat_stream(
                user_message=request.message,
                file_path=request.file_path,
                session_id=request.session_id,
                knowledge_base_id=request.knowledge_base_id,
                user_id=current_user.user_id,
            ):
                yield await _sse_event("chunk", token)
            yield await _sse_event("done")
        except Exception as e:
            logger.exception(f"[copilot/chat] error: {e}")
            yield await _sse_event("error", f"对话出错：{str(e)}")
            yield await _sse_event("done")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- 会话管理 ----

class CreateSessionRequest(BaseModel):
    file_path: Optional[str] = None


@router.post("/session")
async def create_session(req: CreateSessionRequest = None, current_user: CurrentUser = Depends(get_current_user)):
    """创建新会话，返回 session_id"""
    from app.services.session_manager import get_session_manager
    mgr = get_session_manager()
    file_path = req.file_path if req else None
    session_id = mgr.create_session(file_path=file_path, user_id=current_user.user_id)
    return {"session_id": session_id}


@router.get("/session/{session_id}")
async def get_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """获取会话状态和历史消息"""
    from app.services.session_manager import get_session_manager
    mgr = get_session_manager()
    session = mgr.get_session(session_id, user_id=current_user.user_id)
    if not session:
        return {"error": "session not found"}
    return {
        "session_id": session.session_id,
        "file_path": session.file_path,
        "messages": [m.to_dict() for m in session.messages],
        "summary": session.summary,
        "message_count": len(session.messages),
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """删除会话"""
    from app.services.session_manager import get_session_manager
    mgr = get_session_manager()
    ok = mgr.delete_session(session_id, user_id=current_user.user_id)
    return {"deleted": ok}


@router.post("/session/{session_id}/clear")
async def clear_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """清空会话消息"""
    from app.services.session_manager import get_session_manager
    mgr = get_session_manager()
    ok = mgr.clear_session(session_id, user_id=current_user.user_id)
    return {"cleared": ok}


# ---- AI 出题与评估 ----

class GenerateQuestionsRequest(BaseModel):
    source_type: str = "document"               # knowledge_point | document | knowledge_base
    source_id: Optional[str] = None             # 当传 file_path 时可为空
    file_path: Optional[str] = None             # 新增：前端按文档路径生成时使用
    question_type: str = "single"               # single | text | code
    difficulty: str = "medium"
    count: int = 5


class EvaluateAnswerRequest(BaseModel):
    question_id: str
    user_answer: str


@router.post("/generate-questions")
async def generate_questions(
    req: GenerateQuestionsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """AI 生成题目并写入数据库。

    支持两种来源指定方式：
    1. 直接传 source_id（knowledge_point/document/knowledge_base 的 UUID）
    2. 传 file_path（仅 document 场景），由后端反查 document_id（带用户隔离）

    二者至少传一个；file_path 优先。
    """
    try:
        # 参数校验：file_path 与 source_id 至少一个
        if not req.file_path and not req.source_id:
            raise HTTPException(status_code=422, detail="file_path 或 source_id 至少传一个")

        source_type = req.source_type
        source_id = req.source_id

        # file_path 优先：反查 document_id（带用户隔离）
        if req.file_path:
            from sqlalchemy import select, or_
            from app.models import Document
            async with async_session_factory() as session:
                doc_result = await session.execute(
                    select(Document).where(
                        Document.file_path == req.file_path,
                        or_(
                            Document.owner_id == current_user.user_id,
                            Document.owner_id == "__shared__",
                        ),
                    )
                )
                doc = doc_result.scalar_one_or_none()
                if not doc:
                    raise HTTPException(status_code=404, detail=f"未找到文档: {req.file_path}")
                source_type = "document"
                source_id = str(doc.id)

        # 调用生成器
        generator = get_question_generator()
        async with async_session_factory() as session:
            result = await generator.generate_questions(
                db=session,
                user_id=current_user.user_id,
                source_type=source_type,
                source_id=source_id,
                question_type=req.question_type,
                difficulty=req.difficulty,
                count=req.count,
            )
            await session.commit()
            return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[copilot/generate-questions] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate-answer")
async def evaluate_answer(
    req: EvaluateAnswerRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    统一评估接口，根据题型自动选择评估策略。

    - 选择题 → 规则判断（0 token）
    - 简答题 → LLM 评判
    - 代码题 → 沙盒执行 + LLM 错因
    """
    try:
        from app.models import Question
        from sqlalchemy import select
        from app.services.evaluator import evaluate_answer as llm_evaluate_answer, evaluate_code_answer

        generator = get_question_generator()

        async with async_session_factory() as session:
            # 1. 加载题目
            q_result = await session.execute(
                select(Question).where(Question.id == req.question_id)
            )
            question = q_result.scalar_one_or_none()
            if not question:
                raise HTTPException(status_code=404, detail="题目不存在")

            # 2. 根据题型选择评估策略
            if question.type == "single":
                # 选择题：纯规则评估（0 token）
                question_dict = {
                    "content": question.content,
                    "options": question.options,
                    "correct_option": question.correct_option,
                    "explanation": question.expected_answer,
                    "option_explanations": question.option_explanations or [],
                    "tags": question.tags or [],
                }
                result = generator.evaluate_single_choice(question_dict, req.user_answer)

            elif question.type == "code":
                # 代码题：沙盒执行 + LLM 错因
                result = await evaluate_code_answer(
                    question_id=req.question_id,
                    user_answer=req.user_answer,
                )

            else:
                # 简答题：LLM 评判
                result = await llm_evaluate_answer(
                    question_id=req.question_id,
                    user_answer=req.user_answer,
                )

            return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[copilot/evaluate-answer] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
