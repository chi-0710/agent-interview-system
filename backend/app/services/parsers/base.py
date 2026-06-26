"""解析层基础数据模型"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedDocument:
    """统一解析结果：所有格式最终转成标准 Markdown"""
    filename: str
    title: str
    file_type: str  # pdf, docx, pptx, md, py, js, ...
    content: str
    source_path: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    """解析结果封装"""
    document: ParsedDocument
    warnings: list[str] = field(default_factory=list)