"""PDF 解析器

依赖：PyMuPDF (pymupdf)
"""
from pathlib import Path

from app.services.parsers.base import ParsedDocument


def parse_pdf(path: str, filename: str) -> ParsedDocument:
    """将 PDF 按页抽取文本并转换为 Markdown"""
    import pymupdf

    pdf = pymupdf.open(path)
    pages = []

    for page_no, page in enumerate(pdf, start=1):
        text = page.get_text("text", sort=True).strip()
        if text:
            pages.append(f"## Page {page_no}\n\n{text}")

    title = Path(filename).stem
    content = f"# {title}\n\n" + "\n\n".join(pages)

    metadata = {
        "source_type": "pdf",
        "page_count": len(pdf),
    }
    pdf.close()

    return ParsedDocument(
        filename=filename,
        title=title,
        file_type="pdf",
        content=content,
        source_path=path,
        metadata=metadata,
    )