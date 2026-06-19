"""
错题标签聚合

从多道题的评判结果中聚合 errorTags 数组，
格式对齐前端 setErrorTags 的消费结构。
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def aggregate_error_tags(
    evaluations: List[dict],
    file_path: str,
) -> List[dict]:
    """
    从评判结果列表聚合 errorTags。

    Args:
        evaluations: [{ "correct": bool, "error_tags": [str, ...], "question": { content, tags, sections } }, ...]
        file_path: 当前文档路径

    Returns:
        [{ "tag": "页面置换", "count": 3, "sections": ["操作系统 - 内存管理", "页面置换算法"] }, ...]
    """
    tag_counts: dict[str, int] = {}       # tag → count
    tag_sections: dict[str, List[str]] = {}  # tag → sections (headers)

    for eval_item in evaluations:
        if eval_item.get("correct"):
            continue

        question = eval_item.get("question", {})
        q_tags = question.get("tags") or []
        q_sections = question.get("sections") or []
        eval_tags = eval_item.get("error_tags") or []

        # 合并：题目 tags + LLM 返回的 error_tags
        all_tags = list(set(q_tags + eval_tags))

        for tag in all_tags:
            if not tag:
                continue
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # 如果还没 sections，使用题目预置的 sections
            if tag not in tag_sections and q_sections:
                tag_sections[tag] = q_sections

    # 对没有 sections 的 tag，尝试从向量库搜索获取
    for tag in list(tag_sections.keys()):
        if not tag_sections[tag]:
            del tag_sections[tag]

    for tag in list(tag_counts.keys()):
        if tag not in tag_sections:
            try:
                from app.services.vector_store import similarity_search
                results = similarity_search(tag, top_k=1)
                if results:
                    headers = results[0]["metadata"].get("headers", [])
                    if headers:
                        tag_sections[tag] = headers
                        logger.info(f"[error_tags] resolved '{tag}' → sections={headers}")
                    else:
                        tag_sections[tag] = [tag]
                else:
                    tag_sections[tag] = [tag]
            except Exception as e:
                logger.warning(f"[error_tags] search failed for '{tag}': {e}")
                tag_sections[tag] = [tag]

    # 构建返回数组
    result = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        result.append({
            "tag": tag,
            "count": count,
            "sections": tag_sections.get(tag, [tag]),
        })

    return result
