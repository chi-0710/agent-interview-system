"""
LLM 客户端封装

统一接口：支持 OpenAI-compatible API 的 stream / 非 stream 调用。
"""
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )
    return _client


async def stream_chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[str]:
    """
    LLM 流式对话，逐 token 返回内容。

    Args:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: 模型名，默认从配置读取
        temperature: 温度
        max_tokens: 最大 token 数

    Yields:
        str: 每个 delta chunk 的文本内容
    """
    client = _get_client()
    stream = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    非流式对话，返回完整响应。
    """
    client = _get_client()
    response = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        stream=False,
    )
    return response.choices[0].message.content or ""
