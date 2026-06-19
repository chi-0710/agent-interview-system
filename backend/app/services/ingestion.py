"""
文档入库主逻辑

流程：
1. 扫描 docs/ 目录，收集所有 .md 文件
2. 对每个文件调用 chunker 切片
3. 写入 PostgreSQL（documents 表）
4. 向量化并写入 ChromaDB
"""
import os
import glob
import uuid
from typing import List, Optional

from app.services.chunker import chunk_markdown, Chunk
from app.services.vector_store import add_chunks, delete_by_file


def _scan_md_files(docs_dir: str) -> List[str]:
    """扫描目录下所有 .md 文件，返回绝对路径列表"""
    md_files = []
    pattern = os.path.join(docs_dir, "**", "*.md")
    for f in sorted(glob.glob(pattern, recursive=True)):
        md_files.append(f)
    return md_files


def _abs_to_vpath(abs_path: str, docs_dir: str) -> str:
    """将绝对路径转为虚拟路径，如 /docs/cs/os-memory.md"""
    rel = os.path.relpath(abs_path, docs_dir)
    rel = rel.replace("\\", "/")
    return f"/docs/{rel}"


def _read_file(file_path: str) -> str:
    """读取文件内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_title(content: str, file_path: str) -> str:
    """提取文档标题：优先用第一个 h1，否则用文件名"""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return os.path.splitext(os.path.basename(file_path))[0]


def ingest_docs(
    docs_dir: str,
    db_session=None,
    clear_existing: bool = True,
) -> dict:
    """
    主入库流程。

    Args:
        docs_dir: Markdown 文档目录绝对路径
        db_session: SQLAlchemy async session（可选，传 None 则跳过 DB 写入）
        clear_existing: 是否清空现有向量库

    Returns:
        {"total_files": int, "total_chunks": int, "files": [...]}
    """
    if clear_existing:
        from app.services.vector_store import clear_collection
        clear_collection()
        print("[ingestion] 已清空向量库")

    md_files = _scan_md_files(docs_dir)
    print(f"[ingestion] 发现 {len(md_files)} 个 Markdown 文件")

    result = {
        "total_files": len(md_files),
        "total_chunks": 0,
        "files": [],
    }

    all_chunks: List[tuple] = []  # [(chunk, vpath, title, content), ...]

    for abs_path in md_files:
        vpath = _abs_to_vpath(abs_path, docs_dir)
        content = _read_file(abs_path)
        title = _extract_title(content, abs_path)

        # 切片
        chunks = chunk_markdown(
            file_path=vpath,
            content=content,
            chunk_size=800,
            chunk_overlap=150,
        )

        print(f"[ingestion] {os.path.basename(abs_path)} → {len(chunks)} chunks")

        result["files"].append({
            "path": vpath,
            "title": title,
            "chunks": len(chunks),
        })

        for c in chunks:
            all_chunks.append((c, vpath, title, content))

        result["total_chunks"] += len(chunks)

    # 写入向量库
    if all_chunks:
        chunks_only = [c[0] for c in all_chunks]
        n_added = add_chunks(chunks_only)
        print(f"[ingestion] 向量库写入 {n_added} 条记录")

    # 写入 PostgreSQL（如果提供了 session）
    if db_session is not None:
        _write_to_db_sync(all_chunks, db_session)

    return result


async def _write_to_db(chunks_data: list, db_session):
    """异步写入 PostgreSQL"""
    from app.models import Document
    from sqlalchemy import select

    # 按文件去重
    seen = set()
    for c, vpath, title, content in chunks_data:
        if vpath in seen:
            continue
        seen.add(vpath)

        # 检查是否已存在
        result = await db_session.execute(
            select(Document).where(Document.file_path == vpath)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = title
            existing.content = content
        else:
            doc = Document(
                title=title,
                content=content,
                file_type="md",
                file_path=vpath,
            )
            db_session.add(doc)

    await db_session.commit()
    print(f"[ingestion] PostgreSQL 写入 {len(seen)} 条文档记录")


def _write_to_db_sync(chunks_data: list, db_session):
    """同步写入 PostgreSQL（给非 async 环境使用）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已运行的事件循环中
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                _write_to_db(chunks_data, db_session), loop
            )
            future.result(timeout=30)
        else:
            loop.run_until_complete(_write_to_db(chunks_data, db_session))
    except RuntimeError:
        asyncio.run(_write_to_db(chunks_data, db_session))


async def ingest_docs_async(
    docs_dir: str,
    db_session=None,
    clear_existing: bool = True,
) -> dict:
    """异步版入库流程"""
    if clear_existing:
        from app.services.vector_store import clear_collection
        clear_collection()
        print("[ingestion] 已清空向量库")

    md_files = _scan_md_files(docs_dir)
    print(f"[ingestion] 发现 {len(md_files)} 个 Markdown 文件")

    result = {
        "total_files": len(md_files),
        "total_chunks": 0,
        "files": [],
    }

    all_chunks_data = []

    for abs_path in md_files:
        vpath = _abs_to_vpath(abs_path, docs_dir)
        content = _read_file(abs_path)
        title = _extract_title(content, abs_path)

        chunks = chunk_markdown(
            file_path=vpath,
            content=content,
            chunk_size=800,
            chunk_overlap=150,
        )

        print(f"[ingestion] {os.path.basename(abs_path)} → {len(chunks)} chunks")

        result["files"].append({
            "path": vpath,
            "title": title,
            "chunks": len(chunks),
        })

        for c in chunks:
            all_chunks_data.append((c, vpath, title, content))

        result["total_chunks"] += len(chunks)

    # 写入向量库
    if all_chunks_data:
        chunks_only = [c[0] for c in all_chunks_data]
        n_added = add_chunks(chunks_only)
        print(f"[ingestion] 向量库写入 {n_added} 条记录")

    # 写入 PostgreSQL
    if db_session is not None:
        await _write_to_db(all_chunks_data, db_session)

    return result
