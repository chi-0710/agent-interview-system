"""预置文档自动入库脚本（幂等）

容器启动时执行，将 backend/docs 下的预置 Markdown 文档写入 PostgreSQL，
让 DB 成为默认知识库的唯一数据源（不再依赖文件系统回退显示）。

特性：
- 按 file_path 去重，重复执行安全（已存在则更新内容与切片）
- 预置文档作为共享文档，owner_id = "__shared__"（路由过滤时一并放行）
- knowledge_base_id = NULL，归属默认知识库
- 同时写入 DocumentChunk 与向量库，保证检索可用

用法:
    python scripts/seed_docs.py
"""
import os
import sys
import asyncio
import glob

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import async_session_factory
from app.models import Document, DocumentChunk, ChunkKnowledgeLink
from app.services.ingestion import (
    _scan_md_files,
    _abs_to_vpath,
    _read_file,
    _extract_title,
)
from app.services.chunker import chunk_markdown
from app.services.vector_store import add_chunks

# 共享预置文档的 owner_id 标识（路由过滤时与 None 一并放行）
SHARED_OWNER_ID = "__shared__"


async def seed_docs():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    if not os.path.isdir(docs_dir):
        print("[seed_docs] docs 目录不存在，跳过")
        return

    md_files = _scan_md_files(docs_dir)
    if not md_files:
        print("[seed_docs] docs 目录无 Markdown 文件，跳过")
        return

    print(f"[seed_docs] 发现 {len(md_files)} 个预置文档，开始入库...")

    async with async_session_factory() as session:
        new_doc_count = 0
        updated_doc_count = 0
        total_chunks = 0
        all_new_chunks = []

        for abs_path in md_files:
            vpath = _abs_to_vpath(abs_path, docs_dir)
            content = _read_file(abs_path)
            if not content or not content.strip():
                print(f"[seed_docs] 跳过空文件: {vpath}")
                continue
            title = _extract_title(content, abs_path)

            # 按 file_path 去重：已存在则更新，不存在则新建
            result = await session.execute(
                select(Document).where(Document.file_path == vpath)
            )
            doc = result.scalar_one_or_none()

            if doc:
                doc.title = title
                doc.content = content
                doc.file_type = "md"
                # 清理旧 chunk（向量库中的旧 chunk 由前端检索时按 metadata 过滤，这里只清 DB）
                from sqlalchemy import delete
                await session.execute(
                    delete(ChunkKnowledgeLink).where(
                        ChunkKnowledgeLink.chunk_id.in_(
                            select(DocumentChunk.id).where(DocumentChunk.document_id == doc.id)
                        )
                    )
                )
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                )
                updated_doc_count += 1
            else:
                doc = Document(
                    title=title,
                    content=content,
                    file_type="md",
                    file_path=vpath,
                    knowledge_base_id=None,
                    owner_id=SHARED_OWNER_ID,
                    source_type="upload",
                    parse_status="ready",
                )
                session.add(doc)
                await session.flush()
                new_doc_count += 1

            # 写入 DocumentChunk
            chunks = chunk_markdown(
                file_path=vpath,
                content=content,
                chunk_size=800,
                chunk_overlap=150,
            )
            for idx, c in enumerate(chunks):
                headers = c.metadata.get("headers", []) if c.metadata else []
                chunk_row = DocumentChunk(
                    document_id=doc.id,
                    content=c.text,
                    chunk_index=idx,
                    headers=headers,
                    section_path=" > ".join(headers) if headers else None,
                )
                session.add(chunk_row)
                all_new_chunks.append(c)
                total_chunks += 1

            print(f"[seed_docs] {os.path.basename(abs_path)} → {len(chunks)} chunks")

        await session.commit()

        # 向量库写入（仅写入本次产生的 chunk，避免重复）
        if all_new_chunks:
            try:
                n_added = add_chunks(all_new_chunks)
                print(f"[seed_docs] 向量库写入 {n_added} 条记录")
            except Exception as e:
                print(f"[seed_docs] 向量库写入失败（不影响 DB 入库）: {e}")

    print(f"[seed_docs] 完成：新增 {new_doc_count} 篇，更新 {updated_doc_count} 篇，共 {total_chunks} 个切片")


if __name__ == "__main__":
    asyncio.run(seed_docs())
