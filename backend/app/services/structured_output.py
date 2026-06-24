"""
LLM 结构化输出稳健性中间件

核心能力：
1. 强制 response_format 为 json_object（API 层约束）
2. Pydantic 模型强校验（后端层约束）
3. 校验失败自动重试，附带错误提示让模型自我修正

用法：
    from app.services.structured_output import structured_chat
    result = await structured_chat(
        messages=messages,
        output_model=MyPydanticModel,
        max_retries=2,
    )
"""
import json
import logging
from typing import Type, TypeVar, Optional

from pydantic import BaseModel, ValidationError

from app.services.llm import chat as llm_chat

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def structured_chat(
    messages: list[dict],
    output_model: Type[T],
    max_retries: int = 2,
    temperature: float = 0.3,
    max_tokens: int = 500,
) -> T:
    """
    结构化输出：强制 LLM 返回符合 Pydantic 模型的 JSON。

    策略：
    1. 首次请求：带上 response_format=json_object + Pydantic schema 描述
    2. 若 Pydantic 校验失败：附带错误信息重试，让模型自我修正
    3. 全部重试失败：抛出 ValidationError

    Args:
        messages: 对话消息列表
        output_model: 期望的输出模型（Pydantic BaseModel 子类）
        max_retries: 校验失败时的重试次数
        temperature: 温度
        max_tokens: 最大 token 数

    Returns:
        output_model 的实例
    """
    # 生成 JSON Schema 描述
    schema_desc = _format_schema_description(output_model)

    # 构建 system prompt（追加 schema 约束）
    system_msg_found = False
    enhanced_messages = []
    for msg in messages:
        if msg.get("role") == "system" and not system_msg_found:
            enhanced_content = msg["content"] + f"\n\n输出格式约束（必须严格遵守）：\n{schema_desc}"
            enhanced_messages.append({"role": "system", "content": enhanced_content})
            system_msg_found = True
        else:
            enhanced_messages.append(msg)

    if not system_msg_found:
        enhanced_messages.insert(
            0,
            {
                "role": "system",
                "content": f"你必须返回 JSON 格式的响应。输出格式约束：\n{schema_desc}",
            },
        )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            # 调用 LLM，强制 JSON 模式
            response = await llm_chat(
                messages=enhanced_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

            # 解析 JSON
            try:
                data = json.loads(response.strip())
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 解析失败: {str(e)}")

            # Pydantic 强校验
            result = output_model.model_validate(data)
            logger.info(f"[structured_output] attempt {attempt+1} success")
            return result

        except (ValidationError, ValueError) as e:
            last_error = e
            logger.warning(f"[structured_output] attempt {attempt+1} failed: {e}")

            if attempt < max_retries:
                # 构造重试消息：附上错误让模型修正
                error_hint = _build_retry_hint(e, output_model)
                enhanced_messages.append(
                    {"role": "assistant", "content": response if 'response' in locals() else ""}
                )
                enhanced_messages.append(
                    {"role": "user", "content": f"上一次输出不符合格式要求，错误信息：{error_hint}\n请重新输出正确的 JSON。"}
                )
            else:
                break

    # 全部重试失败
    logger.error(f"[structured_output] all retries failed: {last_error}")
    raise last_error


def _format_schema_description(model: Type[BaseModel]) -> str:
    """将 Pydantic 模型的 schema 格式化为易读的约束描述"""
    schema = model.model_json_schema()
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    lines = ["你必须返回一个 JSON 对象，包含以下字段："]
    for field_name, field_info in properties.items():
        field_type = field_info.get("type", "any")
        is_required = field_name in required
        description = field_info.get("description", "")
        req_mark = "（必填）" if is_required else "（可选）"
        desc_line = f"  - {field_name}: {field_type} {req_mark}"
        if description:
            desc_line += f" - {description}"
        lines.append(desc_line)

    lines.append("\n示例：")
    example = {}
    for field_name, field_info in properties.items():
        field_type = field_info.get("type", "string")
        if field_type == "string":
            example[field_name] = "string_value"
        elif field_type == "number":
            example[field_name] = 0
        elif field_type == "integer":
            example[field_name] = 0
        elif field_type == "boolean":
            example[field_name] = False
        elif field_type == "array":
            example[field_name] = []
        elif field_type == "object":
            example[field_name] = {}
        else:
            example[field_name] = None
    lines.append(json.dumps(example, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def _build_retry_hint(error: Exception, model: Type[BaseModel]) -> str:
    """构建重试提示，告诉模型哪里错了"""
    if isinstance(error, ValidationError):
        errors = []
        for err in error.errors():
            loc = ".".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", "")
            errors.append(f"字段 '{loc}': {msg}")
        return "；".join(errors)
    return str(error)