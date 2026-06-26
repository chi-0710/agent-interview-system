"""统一内容解析层

将 PDF、Office、代码、Markdown/TXT 等格式统一转换为
标准 ParsedDocument，供 ingestion 和 chunker 使用。
"""
from app.services.parsers.base import ParsedDocument, ParseResult
from app.services.parsers.pdf_parser import parse_pdf
from app.services.parsers.office_parser import parse_docx, parse_pptx, convert_legacy_office
from app.services.parsers.code_parser import parse_code_file
from app.services.parsers.storage import save_upload_file, ensure_kb_upload_dir


def detect_file_type(filename: str) -> str:
    """根据文件名推断文件类型"""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_map = {
        "md": "md", "markdown": "md", "txt": "txt",
        "pdf": "pdf",
        "docx": "docx", "doc": "doc",
        "pptx": "pptx", "ppt": "ppt",
        "py": "py", "js": "js", "jsx": "jsx",
        "ts": "ts", "tsx": "tsx",
        "java": "java", "go": "go", "c": "c", "h": "h",
        "cpp": "cpp", "cs": "cs",
        "sql": "sql",
        "json": "json", "yaml": "yaml", "yml": "yml",
        "html": "html", "css": "css", "sh": "sh",
    }
    return ext_map.get(ext, "unknown")


def is_code_file(file_type: str) -> bool:
    """判断是否为代码文件"""
    code_types = {
        "py", "js", "jsx", "ts", "tsx",
        "java", "go", "c", "h", "cpp",
        "cs", "sql", "sh",
        "json", "yaml", "yml",
        "html", "css",
    }
    return file_type in code_types


async def parse_file(
    local_path: str,
    filename: str,
    file_type: str | None = None,
) -> ParseResult:
    """统一文件解析入口

    Args:
        local_path: 文件在磁盘上的路径
        filename: 原始文件名（含扩展名）
        file_type: 文件类型，如 'pdf', 'docx', 'py' 等。自动检测如果未提供。
    """
    ft = file_type or detect_file_type(filename)
    warnings: list[str] = []

    if ft in ("md", "txt"):
        from app.services.parsers.storage import read_text_file
        content = read_text_file(local_path)
        from pathlib import Path
        title = Path(filename).stem
        doc = ParsedDocument(
            filename=filename,
            title=title,
            file_type=ft,
            content=content,
            source_path=local_path,
            metadata={"source_type": "upload"},
        )
        return ParseResult(document=doc, warnings=warnings)

    if ft == "pdf":
        parsed = parse_pdf(local_path, filename)
        return ParseResult(document=parsed, warnings=warnings)

    if ft == "docx":
        parsed = parse_docx(local_path, filename)
        return ParseResult(document=parsed, warnings=warnings)

    if ft == "pptx":
        parsed = parse_pptx(local_path, filename)
        return ParseResult(document=parsed, warnings=warnings)

    if ft in ("doc", "ppt"):
        try:
            new_path = convert_legacy_office(local_path)
            new_ft = "docx" if ft == "doc" else "pptx"
            parsed = await parse_file(str(new_path), filename.replace(f".{ft}", f".{new_ft}"), new_ft)
            warnings.append(f"已将 {ft.upper()} 转换为 {new_ft.upper()} 后解析")
            return parsed
        except Exception as e:
            return ParseResult(
                document=ParsedDocument(
                    filename=filename,
                    title=filename,
                    file_type=ft,
                    content=f"[解析失败: 无法转换旧版 Office 格式 {ft.upper()} — {e}]",
                    source_path=local_path,
                    metadata={"parse_error": str(e)},
                ),
                warnings=[f"旧版 Office 转换失败: {e}"],
            )

    if is_code_file(ft):
        parsed = parse_code_file(local_path, filename, ft)
        return ParseResult(document=parsed, warnings=warnings)

    # 未知类型：尝试按文本读取
    try:
        from app.services.parsers.storage import read_text_file
        content = read_text_file(local_path)
        from pathlib import Path
        title = Path(filename).stem
        doc = ParsedDocument(
            filename=filename,
            title=title,
            file_type=ft,
            content=content,
            source_path=local_path,
            metadata={"source_type": "upload", "fallback": True},
        )
        warnings.append(f"尝试按文本读取未知类型 .{ft}")
        return ParseResult(document=doc, warnings=warnings)
    except Exception as e:
        return ParseResult(
            document=ParsedDocument(
                filename=filename,
                title=filename,
                file_type=ft,
                content=f"[无法解析的文件类型: .{ft}]",
                source_path=local_path,
                metadata={"parse_error": str(e)},
            ),
            warnings=[f"不支持的文件类型 .{ft}: {e}"],
        )