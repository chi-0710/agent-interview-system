"""
文档入库主逻辑

流程：
1. 扫描 docs/ 目录，收集所有 .md 文件
2. 对每个文件调用 chunker 切片
3. 写入 PostgreSQL（documents + document_chunks 表）
4. 建立 chunk 与 knowledge_point 的关联
5. 向量化并写入 ChromaDB

v2: 支持按知识库隔离，支持任意文本内容导入
v3: 支持多格式（PDF/DOCX/PPTX/代码）通过 parsers 层解析
"""
import os
import glob
import uuid
from typing import List, Optional

from app.services.chunker import chunk_markdown, chunk_parsed_document, Chunk
from app.services.vector_store import add_chunks, delete_by_file, delete_by_knowledge_base
from app.services.parsers import parse_file, is_code_file


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


def _format_title_from_filename(filename: str) -> str:
    """从文件名生成友好标题"""
    name = os.path.splitext(filename)[0]
    name = name.replace("_", " ").replace("-", " ")
    return name


def ingest_docs(
    docs_dir: str,
    db_session=None,
    clear_existing: bool = True,
) -> dict:
    """
    主入库流程（全局模式，向后兼容）。

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

    if all_chunks:
        chunks_only = [c[0] for c in all_chunks]
        n_added = add_chunks(chunks_only)
        print(f"[ingestion] 向量库写入 {n_added} 条记录")

    if db_session is not None:
        _write_to_db_sync(all_chunks, db_session)

    return result


async def _write_to_db(chunks_data: list, db_session, knowledge_base_id: Optional[str] = None, owner_id: Optional[str] = None):
    """异步写入 PostgreSQL：Document + DocumentChunk + ChunkKnowledgeLink

    支持两种数据格式：
    - (Chunk, vpath, title, content)  — 旧格式兼容
    - (Chunk, vpath, title, content, ParsedDocument)  — 新格式（v3 多格式）
    """
    from app.models import Document, DocumentChunk, ChunkKnowledgeLink, KnowledgePoint
    from sqlalchemy import select

    kp_result = await db_session.execute(
        select(KnowledgePoint).where(
            KnowledgePoint.knowledge_base_id == knowledge_base_id
        ) if knowledge_base_id else select(KnowledgePoint)
    )
    all_kps = kp_result.scalars().all()

    files_map = {}  # vpath -> {"title": "", "content": "", "chunks": [], "parsed": None}
    for item in chunks_data:
        if len(item) == 5:
            c, vpath, title, content, parsed = item
        else:
            c, vpath, title, content = item
            parsed = None

        if vpath not in files_map:
            files_map[vpath] = {
                "title": title,
                "content": content,
                "chunks": [],
                "parsed": parsed,
            }
        files_map[vpath]["chunks"].append(c)

    for vpath, info in files_map.items():
        parsed = info.get("parsed")

        result = await db_session.execute(
            select(Document).where(Document.file_path == vpath)
        )
        doc = result.scalar_one_or_none()

        if doc:
            doc.title = info["title"]
            doc.content = info["content"]
            if parsed:
                doc.file_type = parsed.file_type
                if parsed.source_path:
                    doc.source_uri = parsed.source_path
                if parsed.metadata:
                    doc.source_metadata = parsed.metadata
            if knowledge_base_id:
                doc.knowledge_base_id = knowledge_base_id
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
            file_type = parsed.file_type if parsed else "md"
            doc = Document(
                title=info["title"],
                content=info["content"],
                file_type=file_type,
                file_path=vpath,
                knowledge_base_id=knowledge_base_id,
                owner_id=owner_id or "default_user",
            )
            if parsed:
                doc.source_type = parsed.metadata.get("source_type", "upload") if parsed.metadata else "upload"
                if parsed.source_path:
                    doc.source_uri = parsed.source_path
                if parsed.metadata:
                    doc.source_metadata = parsed.metadata
                if hasattr(parsed, 'source_uri') and parsed.source_uri:
                    doc.source_uri = parsed.source_uri
            db_session.add(doc)
            await db_session.flush()

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

        for chunk_rec in chunk_records:
            text_lower = chunk_rec.content.lower()
            headers_lower = " ".join(chunk_rec.headers or []).lower()
            combined = text_lower + " " + headers_lower

            for kp in all_kps:
                relevance = 0.0
                kp_name = kp.name.lower()
                if kp_name and len(kp_name) >= 2:
                    count = combined.count(kp_name)
                    if count > 0:
                        relevance += min(count * 0.3, 0.6)
                if kp.path:
                    for part in kp.path.split("/"):
                        part = part.strip().lower()
                        if part and part != kp_name and len(part) >= 2 and part in combined:
                            relevance += 0.2
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
    """异步版入库流程（全局模式）"""
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

    if all_chunks_data:
        chunks_only = [c[0] for c in all_chunks_data]
        n_added = add_chunks(chunks_only)
        print(f"[ingestion] 向量库写入 {n_added} 条记录")

    if db_session is not None:
        await _write_to_db(all_chunks_data, db_session)

    return result


async def ingest_knowledge_base(
    knowledge_base_id: str,
    file_infos: list,
    db_session,
) -> dict:
    """
    按知识库隔离的入库流程（v3: 支持多格式文件）。

    Args:
        knowledge_base_id: 知识库 UUID
        file_infos: [{filename, local_path, extension, file_type}, ...]
        db_session: 数据库会话

    Returns:
        {"total_files": int, "total_chunks": int, "files": [...]}
    """
    from app.models import KnowledgeBase, Document
    from sqlalchemy import select

    kb_result = await db_session.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
    )
    kb_row = kb_result.scalar_one_or_none()
    kb_owner_id = kb_row.owner_id if kb_row else "default_user"

    result = {
        "total_files": len(file_infos),
        "total_chunks": 0,
        "files": [],
    }

    all_chunks_data = []
    documents_created = []

    for fi in file_infos:
        filename = fi["filename"]
        local_path = fi.get("local_path", "")
        file_type = fi.get("file_type", "md")
        vpath = f"/kb/{knowledge_base_id}/{filename}"

        # 通过统一解析层解析文件
        parse_result = await parse_file(
            local_path=local_path,
            filename=filename,
            file_type=file_type,
        )
        parsed = parse_result.document

        title = parsed.title
        content = parsed.content

        # 切片（代码文件按结构切片，文档沿用 chunk_markdown）
        chunks = chunk_parsed_document(
            parsed=parsed,
            chunk_size=800,
            chunk_overlap=150,
        )

        result["files"].append({
            "filename": filename,
            "title": title,
            "chunks": len(chunks),
            "status": "processed",
            "warnings": parse_result.warnings,
        })

        for c in chunks:
            c.metadata["knowledge_base_id"] = str(knowledge_base_id)
            c.metadata["document_filename"] = filename
            c.metadata["file_type"] = parsed.file_type
            all_chunks_data.append((c, vpath, title, content, parsed))

        result["total_chunks"] += len(chunks)
        documents_created.append({
            "title": title,
            "content": content,
            "file_type": parsed.file_type,
            "file_path": vpath,
            "filename": filename,
        })

    if all_chunks_data:
        chunks_only = [c[0] for c in all_chunks_data]
        n_added = add_chunks(chunks_only)
        print(f"[ingestion] 知识库 {knowledge_base_id} 向量库写入 {n_added} 条记录")

    await _write_to_db(all_chunks_data, db_session, knowledge_base_id=knowledge_base_id, owner_id=kb_owner_id)

    kb_result = await db_session.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
    )
    kb = kb_result.scalar_one_or_none()
    if kb:
        kb.document_count = len(file_infos)
        kb.chunk_count = result["total_chunks"]
        kb.status = "ready"
        await db_session.commit()

    return result
