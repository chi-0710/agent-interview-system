"""代码文件解析器

按语言结构切片：文件级描述 → 类 → 函数/方法
输出为标准 Markdown，保留代码围栏，供 chunker 处理。
"""
import ast
import re
from pathlib import Path
from typing import List

from app.services.parsers.base import ParsedDocument


# ---- 结构提取器 ----

def _extract_python_structure(content: str) -> List[dict]:
    """用 Python ast 提取模块、类、函数/方法结构"""
    tree = ast.parse(content)
    sections: List[dict] = []

    # 模块文档字符串
    if ast.get_docstring(tree):
        sections.append({
            "type": "module_docstring",
            "name": "模块说明",
            "start_line": 1,
            "end_line": 0,
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            sections.append({
                "type": "class",
                "name": node.name,
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "docstring": doc,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent = getattr(node, "parent", None)
            parent_name = parent.name if isinstance(parent, ast.ClassDef) else ""
            doc = ast.get_docstring(node)
            sections.append({
                "type": "method" if parent_name else "function",
                "name": node.name,
                "parent": parent_name,
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "docstring": doc,
            })
        elif isinstance(node, ast.Module):
            for child in ast.iter_child_nodes(node):
                child.parent = node
                for grandchild in ast.iter_child_nodes(child):
                    grandchild.parent = child

    return sections


def _extract_generic_structure(content: str, language: str) -> List[dict]:
    """通用结构提取（非 Python）：基于正则的关键结构识别"""
    sections: List[dict] = []
    lines = content.split("\n")

    # 不同的语言的函数/类模式
    patterns = {
        "js": [r"^(export\s+)?(async\s+)?function\s+(\w+)", r"^(export\s+)?class\s+(\w+)", r"^(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?=>"],
        "jsx": [r"^(export\s+)?(async\s+)?function\s+(\w+)", r"^(export\s+)?class\s+(\w+)", r"^(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?=>", r"^(export\s+)?default\s+(function|class)\s+(\w+)"],
        "ts": [r"^(export\s+)?(async\s+)?function\s+(\w+)", r"^(export\s+)?class\s+(\w+)", r"^(export\s+)?interface\s+(\w+)", r"^(export\s+)?type\s+(\w+)\s*="],
        "tsx": [r"^(export\s+)?(async\s+)?function\s+(\w+)", r"^(export\s+)?class\s+(\w+)", r"^(export\s+)?interface\s+(\w+)", r"^(export\s+)?const\s+(\w+)\s*="],
        "java": [r"^(public|private|protected)?\s*(static\s+)?class\s+(\w+)", r"^(public|private|protected)?\s*(static\s+)?(\w+\s+)?(\w+)\s*\([^)]*\)\s*\{"],
        "go": [r"^func\s+(\w+)", r"^type\s+(\w+)\s+struct", r"^type\s+(\w+)\s+interface"],
        "cpp": [r"^class\s+(\w+)", r"^(\w+\s+)?(\w+)\s*\([^)]*\)\s*(const\s*)?(\{|override|final|;)"],
        "c": [r"^(static\s+)?(\w+\s+)+(\w+)\s*\([^)]*\)\s*\{"],
        "cs": [r"^(public|private|protected|internal)?\s*(static\s+)?class\s+(\w+)", r"^(public|private|protected|internal)?\s*(static\s+)?(\w+\s+)?(\w+)\s*\([^)]*\)\s*\{"],
        "sql": [r"^CREATE\s+(TABLE|VIEW|INDEX|PROCEDURE|FUNCTION|TRIGGER)\s+(\w+)", r"^SELECT\s", r"^ALTER\s"],
        "sh": [r"^function\s+(\w+)", r"^(\w+)\s*\(\)\s*\{"],
    }

    pats = patterns.get(language, [r"^(function|class)\s+(\w+)"])

    for i, line in enumerate(lines, start=1):
        for pat in pats:
            m = re.match(pat, line.strip())
            if m:
                name = m.group(min(m.lastindex, 3))
                sections.append({
                    "type": "symbol",
                    "name": name or f"symbol_{i}",
                    "start_line": i,
                    "end_line": i,
                })
                break

    return sections


def parse_code_file(path: str, filename: str, file_type: str) -> ParsedDocument:
    """解析代码文件 → Markdown（按结构组织）"""
    from app.services.parsers.storage import read_text_file

    content = read_text_file(path)
    language_map = {
        "py": "python", "js": "javascript", "jsx": "javascript",
        "ts": "typescript", "tsx": "typescript",
        "java": "java", "go": "go", "c": "c", "h": "c",
        "cpp": "cpp", "cs": "csharp",
        "sql": "sql", "sh": "bash",
        "json": "json", "yaml": "yaml", "yml": "yaml",
        "html": "html", "css": "css",
    }
    lang = language_map.get(file_type, file_type)

    # 提取结构
    if file_type == "py":
        try:
            sections = _extract_python_structure(content)
        except SyntaxError:
            sections = []
    else:
        sections = _extract_generic_structure(content, file_type)

    # 组装为 Markdown
    lines = content.split("\n")
    title = Path(filename).stem
    md_lines = [f"# {filename}", f"", f"Language: {lang}", ""]

    if sections:
        for sec in sections:
            sec_type = sec.get("type", "")
            sec_name = sec.get("name", "")
            parent = sec.get("parent", "")

            if sec_type == "module_docstring":
                md_lines.append(f"## 📦 模块说明")
            elif sec_type == "class":
                md_lines.append(f"## 📋 Class: {sec_name}")
            elif sec_type in ("function",):
                md_lines.append(f"### 🔧 Function: {sec_name}")
            elif sec_type == "method":
                md_lines.append(f"### 🔧 Method: {parent}.{sec_name}")
            else:
                md_lines.append(f"### {sec_name}")

            doc = sec.get("docstring")
            if doc:
                md_lines.append(f"> {doc}")
            md_lines.append("")

            # 提取对应源码
            start = sec.get("start_line", 0) - 1
            end = sec.get("end_line", 0)
            if start >= 0 and end > start:
                src_lines = lines[max(0, start):min(end, len(lines))]
                md_lines.append(f"```{lang}")
                md_lines.extend(src_lines)
                md_lines.append("```")
                md_lines.append("")
    else:
        # 无结构信息：直接按文本文件处理
        md_lines.append(f"```{lang}")
        md_lines.extend(lines)
        md_lines.append("```")

    content_md = "\n".join(md_lines)

    return ParsedDocument(
        filename=filename,
        title=title,
        file_type=file_type,
        content=content_md,
        source_path=path,
        metadata={
            "source_type": "code",
            "language": lang,
            "symbol_count": len(sections),
        },
    )