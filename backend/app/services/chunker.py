"""
Markdown 切片器

核心约束：每个 chunk 的 metadata.headers 必须与前端 SmartReader 的
currentHeaders 生成逻辑完全一致 —— 按 h1→h2→h3 层级截断的小写字符串数组。

SmartReader 的层级追踪规则（见 src/components/Reader/SmartReader.jsx L121-134）：
- 遇到 h1：清空全部，设为 [h1_text.lower()]
- 遇到 h2：保留 h1，替换 h2，即 [h1, h2_text.lower()]
- 遇到 h3：保留 h1+h2，替换 h3，即 [h1, h2, h3_text.lower()]

切片策略：
- 按 logic section（标题 + 正文）划分
- 在同一 h2 下合并到 chunk_size
- h2 边界强制分片，保证 headers 语义正确
- 保留 chunk_overlap 重叠
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    text: str
    metadata: dict
    # metadata 包含:
    #   file_path: str        # 如 "/docs/cs/os-memory.md"
    #   headers: List[str]    # 如 ["操作系统内存管理", "页面置换算法"]
    #   line_start: int
    #   line_end: int


def _is_header_line(line: str) -> Optional[tuple]:
    """判断一行是否为 Markdown 标题，返回 (level, text) 或 None"""
    m = re.match(r'^(#{1,6})\s+(.+)$', line)
    if m:
        level = len(m.group(1))
        text = m.group(2).strip()
        return (level, text)
    return None


def _is_code_fence(line: str) -> Optional[str]:
    """判断是否为代码围栏起止行"""
    m = re.match(r'^```(\w*)\s*$', line)
    if m:
        return m.group(1) or ""
    return None


def chunk_markdown(
    file_path: str,
    content: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> List[Chunk]:
    """
    将 Markdown 文本切片，每个 chunk 保留完整的 headers 层级信息。
    """
    lines = content.split('\n')
    lines_with_idx = list(enumerate(lines, start=1))

    # ---- 第一步：解析为 sections ----
    sections: List[dict] = []
    current_headers: List[str] = []
    current_text_lines: List[str] = []
    current_line_start: int = 1
    in_code_block: bool = False

    for line_num, line in lines_with_idx:
        fence_lang = _is_code_fence(line)
        if fence_lang is not None:
            in_code_block = not in_code_block
            current_text_lines.append(line)
            continue
        if in_code_block:
            current_text_lines.append(line)
            continue

        header = _is_header_line(line)
        if header:
            level, text = header

            # 保存前一个 section
            if current_text_lines:
                sections.append({
                    "headers": list(current_headers),
                    "text": '\n'.join(current_text_lines),
                    "line_start": current_line_start,
                    "line_end": line_num - 1,
                })

            # 更新 headers — 完全复刻 SmartReader 逻辑（小写）
            h_text = text.lower()
            if level == 1:
                current_headers = [h_text]
            elif level == 2:
                prev = current_headers if current_headers else []
                current_headers = prev[:1] + [h_text]
            else:
                prev = current_headers if current_headers else []
                current_headers = prev[:2] + [h_text]

            current_text_lines = [line]
            current_line_start = line_num
            continue

        # 普通行
        current_text_lines.append(line)

    # 最后一个 section
    if current_text_lines:
        sections.append({
            "headers": list(current_headers),
            "text": '\n'.join(current_text_lines),
            "line_start": current_line_start,
            "line_end": len(lines),
        })

    # ---- 第二步：合并 section 成 chunk ----
    # 规则:
    #   1. h2 变化 → 强制分片
    #   2. 同一 h2 下，超过 chunk_size → 在 section 边界分片
    #   3. 保留 overlap
    chunks: List[Chunk] = []
    buffer_sections: List[dict] = []  # [{headers, text, line_start, line_end}]

    def _h2_of(headers: List[str]) -> str:
        return headers[1] if len(headers) >= 2 else headers[0] if headers else ""

    def _flush_buffer():
        nonlocal buffer_sections
        if not buffer_sections:
            return
        first = buffer_sections[0]
        last = buffer_sections[-1]
        chunk_text = '\n\n'.join(s["text"] for s in buffer_sections)
        chunks.append(Chunk(
            text=chunk_text,
            metadata={
                "file_path": file_path,
                "headers": first["headers"],       # 首个 section 的 headers
                "line_start": first["line_start"],
                "line_end": last["line_end"],
            }
        ))
        buffer_sections = []

    def _buffer_char_count() -> int:
        return sum(len(s["text"]) for s in buffer_sections) + max(0, len(buffer_sections) - 1) * 2

    for i, sec in enumerate(sections):
        # 标题行 section 如果很短且是首个（只有标题无正文），跳过独立成 chunk
        if len(sec["text"].split('\n')) == 1 and sec["text"].startswith('#'):
            sec_is_pure_header = True
        else:
            sec_is_pure_header = False

        if not buffer_sections:
            buffer_sections.append(sec)
            continue

        current_h2 = _h2_of(buffer_sections[0]["headers"])
        next_h2 = _h2_of(sec["headers"])

        # 规则1：h2 变化 → 强制分片
        h2_changed = current_h2 and next_h2 and current_h2 != next_h2

        # 规则2：超过 chunk_size
        would_exceed = _buffer_char_count() + len(sec["text"]) + 2 > chunk_size

        if h2_changed or would_exceed:
            _flush_buffer()

            # 处理 overlap：从上一个 section 尾部提取
            if chunk_overlap > 0 and chunks:
                prev_sec = buffer_sections[-1] if buffer_sections else sections[i-1]
                prev_text = prev_sec["text"]
                if len(prev_text) > chunk_overlap:
                    overlap_text = "..." + prev_text[-(chunk_overlap-3):]
                    sec_text_adjusted = overlap_text + "\n\n" + sec["text"]
                else:
                    sec_text_adjusted = sec["text"]
            else:
                sec_text_adjusted = sec["text"]

            # 替换 sec 的文字（用于 overlap）
            sec_copy = dict(sec)
            sec_copy["text"] = sec_text_adjusted
            buffer_sections = [sec_copy]
        else:
            buffer_sections.append(sec)

    _flush_buffer()

    return chunks


def chunk_parsed_document(
    parsed,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> List[Chunk]:
    """对解析后的文档进行切片。

    代码文件：按 ## 结构标题边界切片，确保每个类/函数独立成块
    文档文件（md/txt/pdf/docx/pptx）：沿用 chunk_markdown 逻辑
    """
    from app.services.parsers import is_code_file

    file_path = parsed.source_path or parsed.filename

    if is_code_file(parsed.file_type):
        return _chunk_code_by_structure(
            content=parsed.content,
            file_path=file_path,
        )
    else:
        return chunk_markdown(
            file_path=file_path,
            content=parsed.content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def _chunk_code_by_structure(content: str, file_path: str) -> List[Chunk]:
    """代码文件按 ## 结构标题边界切片，每块一个类/函数，不按字符数硬切"""
    lines = content.split("\n")
    chunks: List[Chunk] = []
    current_lines: List[str] = []
    current_headers: List[str] = []
    current_start: int = 1

    for line_num, line in enumerate(lines, start=1):
        header = _is_header_line(line)
        if header:
            level, text = header

            # 保存前一块
            if current_lines:
                chunk_text = "\n".join(current_lines)
                chunks.append(Chunk(
                    text=chunk_text,
                    metadata={
                        "file_path": file_path,
                        "headers": list(current_headers),
                        "line_start": current_start,
                        "line_end": line_num - 1,
                    }
                ))
                current_lines = []

            # 更新 headers（小写，与 SmartReader 一致）
            h_text = text.lower()
            if level == 1:
                current_headers = [h_text]
            elif level == 2:
                prev = current_headers if current_headers else []
                current_headers = prev[:1] + [h_text]
            else:
                prev = current_headers if current_headers else []
                current_headers = prev[:2] + [h_text]

            current_start = line_num

        current_lines.append(line)

    # 最后一块
    if current_lines:
        chunk_text = "\n".join(current_lines)
        chunks.append(Chunk(
            text=chunk_text,
            metadata={
                "file_path": file_path,
                "headers": list(current_headers),
                "line_start": current_start,
                "line_end": len(lines),
            }
        ))

    return chunks
