"""
文档入库主逻辑

流程：
1. 扫描 docs/ 目录，收集所有 .md 文件
2. 对每个文件调用 chunker 切片
3. 写入 PostgreSQL（documents + document_chunks 表）
4. 建立 chunk 与 knowledge_point 的关联
5. 向量化并写入 ChromaDB
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
    """异步写入 PostgreSQL：Document + DocumentChunk + ChunkKnowledgeLink"""
    from app.models import Document, DocumentChunk, ChunkKnowledgeLink, KnowledgePoint
    from sqlalchemy import select

    # 查询所有知识点，用于匹配
    kp_result = await db_session.execute(select(KnowledgePoint))
    all_kps = kp_result.scalars().all()

    # 按文件分组
    files_map = {}  # vpath -> {"title": "", "content": "", "chunks": []}
    for c, vpath, title, content in chunks_data:
        if vpath not in files_map:
            files_map[vpath] = {"title": title, "content": content, "chunks": []}
        files_map[vpath]["chunks"].append(c)

    for vpath, info in files_map.items():
        # 检查 Document 是否已存在
        result = await db_session.execute(
            select(Document).where(Document.file_path == vpath)
        )
        doc = result.scalar_one_or_none()

        if doc:
            doc.title = info["title"]
            doc.content = info["content"]
            # 删除旧的 chunk
            from sqlalchemy import delete
            await db_session.execute(
                delete(ChunkKnowledgeLink).where(
                    ChunkKnowledgeLink.chunk_id.in_(
                        select(DocumentChunk.id).where(DocumentChunk.document_id == doc.id)
                    )
                )
            )
            await db_session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
        else:
            doc = Document(
                title=info["title"],
                content=info["content"],
                file_type="md",
                file_path=vpath,
            )
            db_session.add(doc)
            await db_session.flush()

        # 写入 DocumentChunk
        chunk_records = []
        for idx, chunk in enumerate(info["chunks"]):
            headers = chunk.metadata.get("headers", [])
            section_path = " / ".join(headers) if headers else None
            chunk_rec = DocumentChunk(
                document_id=doc.id,
                content=chunk.text,
                chunk_index=idx,
                headers=headers,
                section_path=section_path,
                start_line=chunk.metadata.get("line_start"),
                end_line=chunk.metadata.get("line_end"),
                extra_metadata=chunk.metadata,
            )
            db_session.add(chunk_rec)
            chunk_records.append(chunk_rec)

        await db_session.flush()

        # 建立 ChunkKnowledgeLink（基于关键词匹配）
        for chunk_rec in chunk_records:
            text_lower = chunk_rec.content.lower()
            headers_lower = " ".join(chunk_rec.headers or []).lower()
            combined = text_lower + " " + headers_lower

            for kp in all_kps:
                relevance = 0.0
                # 用知识点名称匹配
                kp_name = kp.name.lower()
                if kp_name and len(kp_name) >= 2:
                    count = combined.count(kp_name)
                    if count > 0:
                        relevance += min(count * 0.3, 0.6)
                # 用路径中的关键词匹配
                if kp.path:
                    for part in kp.path.split("/"):
                        part = part.strip().lower()
                        if part and part != kp_name and len(part) >= 2 and part in combined:
                            relevance += 0.2
                # 用描述匹配
                if kp.description and kp.description.lower() in combined:
                    relevance += 0.1

                if relevance >= 0.3:
                    link = ChunkKnowledgeLink(
                        chunk_id=chunk_rec.id,
                        knowledge_point_id=kp.id,
                        relevance=min(relevance, 1.0),
                    )
                    db_session.add(link)

    await db_session.commit()
    print(f"[ingestion] PostgreSQL 写入 {len(files_map)} 篇文档 + chunks + 关联")


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
