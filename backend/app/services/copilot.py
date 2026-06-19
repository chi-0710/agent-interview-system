"""
伴读业务逻辑层

1. 用 selected_text 做向量相似搜索，取 top_k 个 chunks
2. 过滤：只取 file_path 与请求一致的 chunks
3. 拼 prompt → 调用 LLM stream
"""
import logging
from typing import AsyncIterator, List

from app.services.llm import stream_chat

logger = logging.getLogger(__name__)


def _retrieve_context(
    selected_text: str,
    file_path: str,
    top_k: int = 3,
) -> List[dict]:
    """
    检索相关上下文 chunks。

    1. 语义搜索取 top_k
    2. 按 file_path 过滤
    3. 如果过滤后不够 top_k，补齐（放宽 file_path 限制）
    """
    from app.services.vector_store import similarity_search
    results = similarity_search(selected_text, top_k=top_k * 2)

    # 按 file_path 过滤
    same_file = [r for r in results if r["metadata"].get("file_path") == file_path]

    # 如果同文件结果不足，用原始结果补齐
    if len(same_file) < top_k:
        other = [r for r in results if r not in same_file]
        same_file += other[: top_k - len(same_file)]

    # 按 distance 排序，取 top_k
    same_file.sort(key=lambda r: r.get("distance", 999))
    chosen = same_file[:top_k]

    logger.info(
        f"[copilot] retrieve: query='{selected_text[:50]}...', "
        f"same_file={len([r for r in results if r['metadata'].get('file_path') == file_path])}, "
        f"chosen={len(chosen)}, "
        f"headers={[r['metadata'].get('headers','') for r in chosen]}"
    )

    return chosen


def _build_explain_prompt(
    selected_text: str,
    chunks: List[dict],
    headers: List[str] = None,
) -> tuple[str, list[dict]]:
    """
    构建解释 prompt。

    Returns:
        (system_prompt, messages)
    """
    # 拼接上下文
    context_parts = []
    for i, chunk in enumerate(chunks):
        chunk_headers = chunk["metadata"].get("headers", [])
        header_str = " > ".join(chunk_headers) if chunk_headers else "文档片段"
        context_parts.append(f"--- 资料片段 {i+1}（{header_str}）---\n{chunk['text']}")

    context_text = "\n\n".join(context_parts)

    header_hint = ""
    if headers and len(headers) > 0:
        header_hint = f"（用户当前阅读位置：{' > '.join(headers)}）\n"

    system_prompt = (
        "你是一个专业的面试备考助手。你的任务是基于下面提供的学习资料，"
        "为用户解释选中的术语或概念。\n\n"
        "要求：\n"
        "1. 结合上下文说明该概念的含义和要点\n"
        "2. 指出面试中可能的考察角度\n"
        "3. 如果资料中有相关代码或示例，请加以分析\n"
        "4. 回答应当简洁、结构化，控制在 300 字以内\n"
        "5. 只能基于提供的资料回答，不要编造资料中没有的内容\n\n"
        "=== 学习资料 ===\n"
        f"{context_text}"
    )

    user_prompt = f"{header_hint}请解释「{selected_text}」，结合上下文说明其含义和面试考察点。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    return messages


async def explain_stream(
    selected_text: str,
    file_path: str,
    headers: List[str] = None,
    top_k: int = 3,
) -> AsyncIterator[str]:
    """
    流式解释选中文字。

    Args:
        selected_text: 用户选中的文本
        file_path: 当前文档路径
        headers: 当前阅读位置的标题层级
        top_k: 检索的 chunk 数量

    Yields:
        str: 逐 token 文本
    """
    if not selected_text or not selected_text.strip():
        yield "请选中有效的文字内容。"
        return

    # 1. 检索
    chunks = _retrieve_context(selected_text, file_path, top_k=top_k)

    # 2. 拼 prompt
    messages = _build_explain_prompt(selected_text, chunks, headers)

    # 3. 调用 LLM stream
    async for token in stream_chat(messages):
        yield token


async def chat_stream(
    user_message: str,
    file_path: str = None,
    top_k: int = 3,
) -> AsyncIterator[str]:
    """
    自由对话（用户在 CopilotPanel 输入框中的提问）。

    Args:
        user_message: 用户输入
        file_path: 当前文档路径（用于检索上下文）
        top_k: 检索的 chunk 数量
    """
    if not user_message or not user_message.strip():
        yield "请输入有效的问题。"
        return

    # 检索相关上下文
    chunks = []
    if file_path:
        chunks = _retrieve_context(user_message, file_path, top_k=top_k)

    # 拼上下文
    context_text = ""
    if chunks:
        parts = []
        for i, chunk in enumerate(chunks):
            chunk_headers = chunk["metadata"].get("headers", [])
            header_str = " > ".join(chunk_headers) if chunk_headers else "片段"
            parts.append(f"--- {header_str} ---\n{chunk['text']}")
        context_text = "\n\n".join(parts)

    system_prompt = (
        "你是面试备考助手，基于提供的学习资料回答用户问题。\n"
        "如果资料不足以回答问题，如实说明。\n"
        "回答应简洁、结构化，控制在 300 字以内。\n\n"
    )
    if context_text:
        system_prompt += f"=== 学习资料 ===\n{context_text}"
    else:
        system_prompt += "（当前没有可用的学习资料）"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async for token in stream_chat(messages):
        yield token
