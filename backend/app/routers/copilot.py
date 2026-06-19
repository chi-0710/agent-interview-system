"""AI Copilot 路由

提供 SSE 流式接口：
- POST /api/copilot/explain  → 划线伴读解释
- POST /api/copilot/chat     → 自由对话（保留兼容，复用同一个模式）
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.services.copilot import explain_stream, chat_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


# ---- Request/Response Models ----

class ExplainRequest(BaseModel):
    selected_text: str
    file_path: str
    headers: list[str] = []

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
async def explain(request: ExplainRequest):
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
            from app.services.llm import llm_client
            if not llm_client.is_available():
                raise RuntimeError("LLM unavailable")
            tried_main = True
            async for token in explain_stream(
                selected_text=request.selected_text,
                file_path=request.file_path,
                headers=request.headers,
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
async def copilot_chat(request: ChatRequest):
    """
    自由对话（SSE 流式）

    请求体：
        {"message": "什么是 Belady 异常？", "file_path": "/docs/cs/os-memory.md"}
    """

    async def event_generator():
        try:
            async for token in chat_stream(
                user_message=request.message,
                file_path=request.file_path,
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


# ---- 保留旧 stub（兼容） ----

@router.post("/generate-questions")
async def generate_questions():
    """AI 生成题目（stub）"""
    return {
        "questions": [
            {
                "content": "[待 LLM 接入] 请简述你对 AI Agent 的理解",
                "difficulty": "medium",
                "category": "AI/LLM",
            }
        ],
        "message": "此接口将在后续接入 LLM 后可用",
    }


@router.post("/evaluate-answer")
async def evaluate_answer():
    """AI 评估回答（stub）"""
    return {
        "score": 0.0,
        "feedback": "此接口将在后续接入 LLM 后可用",
    }
