"""
错题标签聚合

改造目标：评判与渲染解耦，实现确定性映射。

核心变化：
1. LLM 只负责评判对错和错因，不再生成 error_tags（避免幻觉）
2. 错题关联的知识点和 sections 直接从题目预置数据读取
3. 输出中新增 chunk_ids 列表，前端可通过 DOM 精准定位高亮
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def _resolve_chunk_ids_from_sections(
    sections: List[str],
    file_path: str,
) -> List[str]:
    """
    根据 sections（header 路径）从向量库反查对应的 chunk_ids。
    返回精准的 chunk_id 列表，供前端做确定性 DOM 高亮。
    """
    try:
        from app.services.vector_store import get_collection
        collection = get_collection()
        # 用 file_path 过滤，扫描同文件的所有 chunks，匹配 headers
        # ChromaDB 的 where 过滤支持 metadata 匹配
        results = collection.get(
            where={"file_path": file_path},
            include=["metadatas"]
        )
        chunk_ids = []
        if results.get("ids"):
            for i, chunk_id in enumerate(results["ids"]):
                meta = results.get("metadatas", [])[i] if results.get("metadatas") else {}
                headers_str = meta.get("headers", "")
                headers = headers_str.split("|") if headers_str else []
                # 检查 sections 是否为 headers 的子序列
                if _is_subsequence([s.lower() for s in sections], [h.lower() for h in headers]):
                    chunk_ids.append(chunk_id)
        return chunk_ids
    except Exception as e:
        logger.warning(f"[error_tags] resolve chunk_ids failed: {e}")
        return []


def _is_subsequence(arr_a: List[str], arr_b: List[str]) -> bool:
    """判断 arr_a 是否为 arr_b 的子序列"""
    j = 0
    for i in range(len(arr_b)):
        if j < len(arr_a) and arr_b[i] == arr_a[j]:
            j += 1
    return j == len(arr_a)


def aggregate_error_tags(
    evaluations: List[dict],
    file_path: str,
    resolve_chunk_ids: bool = True,
) -> List[dict]:
    """
    从评判结果列表聚合 errorTags。

    策略升级：
    - 错题标签直接使用题目预置的 tags（确定性，无幻觉）
    - sections 直接使用题目预置的 sections（确定性）
    - 可选：从向量库反查 chunk_ids，供前端做精准 DOM 高亮

    Args:
        evaluations: [{ "correct": bool, "question": { content, tags, sections } }, ...]
        file_path: 当前文档路径
        resolve_chunk_ids: 是否解析 chunk_ids（需要向量库可用）

    Returns:
        [{
            "tag": "页面置换",
            "count": 3,
            "sections": ["操作系统内存管理", "页面置换算法"],
            "chunk_ids": ["uuid-1", "uuid-2"]
        }, ...]
    """
    tag_counts: dict[str, int] = {}
    tag_sections: dict[str, List[str]] = {}
    tag_chunk_ids: dict[str, List[str]] = {}

    for eval_item in evaluations:
        if eval_item.get("correct"):
            continue

        question = eval_item.get("question", {})
        q_tags = question.get("tags") or []
        q_sections = question.get("sections") or []

        # 只使用题目预置的 tags，不再依赖 LLM 生成的 error_tags
        for tag in q_tags:
            if not tag:
                continue
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # 使用题目预置的 sections
            if tag not in tag_sections and q_sections:
                tag_sections[tag] = q_sections

    # 解析 chunk_ids（按需启用）
    if resolve_chunk_ids:
        for tag in tag_counts:
            sections = tag_sections.get(tag, [])
            if sections:
                chunk_ids = _resolve_chunk_ids_from_sections(sections, file_path)
                if chunk_ids:
                    tag_chunk_ids[tag] = chunk_ids
                    logger.info(f"[error_tags] tag '{tag}' → {len(chunk_ids)} chunks")

    # 对没有 sections 的 tag，用 tag 本身作为 fallback
    for tag in tag_counts:
        if tag not in tag_sections:
            tag_sections[tag] = [tag]

    # 构建返回数组
    result = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        item = {
            "tag": tag,
            "count": count,
            "sections": tag_sections.get(tag, [tag]),
        }
        if tag in tag_chunk_ids:
            item["chunk_ids"] = tag_chunk_ids[tag]
        result.append(item)

    return result
