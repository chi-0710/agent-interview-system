"""
单题评判逻辑

拼 prompt → 调用 LLM → 解析 JSON → 重试容错
"""
import json
import logging
import re
from typing import Optional

from app.services.llm import chat as llm_chat

logger = logging.getLogger(__name__)

EVALUATION_SYSTEM_PROMPT = """你是一个技术面试评判官。你的唯一任务是返回 JSON，不返回任何其他内容（不要加 markdown 代码块标记，不要加解释文字）。

返回格式（严格 JSON）：
{
  "correct": true/false,
  "score": 0-100,
  "error_type": "概念混淆 | 遗漏要点 | 完全错误 | null",
  "explanation": "一句话说明对错原因",
  "error_tags": ["对应的知识点tag", "另一个tag"]
}

规则：
1. score：完全正确给 90-100，有瑕疵给 60-89，严重错误给 0-59
2. error_type：错了才填，正确填 null
3. explanation：必须用中文，控制在 50 字以内
4. error_tags：答错时必须给出相关知识点标签（通常是题目涉及的关键知识点），正确时给空数组 []
5. 如果你返回的不是纯 JSON，会造成系统崩溃，请务必只返回 JSON"""


def _parse_json_response(text: str) -> Optional[dict]:
    """尝试从 LLM 返回中解析 JSON"""
    if not text:
        return None

    # 直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 移除 markdown 代码块
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试提取 { } 块（支持嵌套和多行）
    # 使用贪婪匹配找最外层花括号
    for pattern in [
        r'\{[^{}]*\{(?:[^{}]|\{[^{}]*\})*\}[^{}]*\}',  # 嵌套一层
        r'\{[^{}]*\}',                                    # 无嵌套
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    # 手动提取花括号内容（找最大范围）
    start = text.find('{')
    if start >= 0:
        # 从后往前找匹配的 }
        end = text.rfind('}')
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    # 最后尝试：逐行匹配 key
    result = {}
    for key in ["correct", "score", "error_type", "explanation", "error_tags"]:
        if key == "error_tags":
            # 数组需要特殊处理
            pattern = rf'"{key}"\s*:\s*(\[[^\]]*\])'
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    result[key] = json.loads(match.group(1))
                except json.JSONDecodeError:
                    result[key] = []
        else:
            pattern = rf'"{key}"\s*:\s*(.+?)(?:,\s*"|\n|$)'
            match = re.search(pattern, text, re.DOTALL)
            if match:
                val = match.group(1).strip().rstrip(',').strip('"').strip("'")
                if key == "correct":
                    result[key] = val.lower() == "true"
                elif key == "score":
                    try:
                        result[key] = float(val)
                    except ValueError:
                        result[key] = 0
                elif "null" in val.lower() and key == "error_type":
                    result[key] = None
                else:
                    result[key] = val

    if "correct" in result:
        return result
    return None


async def evaluate_answer(
    question: str,
    answer: str,
    user_answer: str,
    max_retries: int = 2,
) -> dict:
    """
    评判单道题的答案。

    Args:
        question: 题目内容
        answer: 标准答案
        user_answer: 用户回答
        max_retries: JSON 解析失败时的重试次数

    Returns:
        {
            "correct": bool,
            "score": float,
            "error_type": Optional[str],
            "explanation": str,
            "error_tags": list[str]
        }
    """
    user_prompt = f"""题目：{question}

标准答案要点：{answer}

用户回答：{user_answer}

请按 JSON 格式返回评判结果。"""

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = await llm_chat(
                messages=[
                    {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # 低温度保证格式稳定
                max_tokens=500,
            )

            result = _parse_json_response(response)
            if result and "correct" in result:
                # 规范化字段
                result.setdefault("score", 0)
                result.setdefault("error_type", None)
                result.setdefault("explanation", "")
                result.setdefault("error_tags", [])
                if result["correct"]:
                    result["error_type"] = None
                    result["error_tags"] = []
                return result

            last_error = f"parse_failed: {response[:100]}"
            logger.warning(f"[evaluator] attempt {attempt+1} parse failed: {response[:150]}")

            if attempt < max_retries:
                # 重试时加强提示
                user_prompt = f"""{user_prompt}

⚠️ 上一次返回不是合法 JSON，请这次只返回 JSON，不要加 markdown 标记。"""

        except Exception as e:
            last_error = str(e)
            logger.error(f"[evaluator] attempt {attempt+1} error: {e}")
            if attempt >= max_retries:
                break

    # 全部重试失败，返回兜底结果
    logger.error(f"[evaluator] all retries failed: {last_error}")
    return {
        "correct": False,
        "score": 0,
        "error_type": "评判失败",
        "explanation": f"AI 评判异常（{last_error[:80]}），请人工复核",
        "error_tags": ["评判异常"],
    }
