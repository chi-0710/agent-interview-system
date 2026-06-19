"""
一次性入库脚本

用法:
    python scripts/ingest.py --path docs/
    python scripts/ingest.py --path docs/ --no-clear
    python scripts/ingest.py --path docs/ --chunk-size 1000 --overlap 200
"""
import os
import sys
import argparse
import asyncio

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ingestion import ingest_docs_async
from app.database import async_session_factory


async def main():
    parser = argparse.ArgumentParser(description="Markdown 文档入库脚本")
    parser.add_argument(
        "--path",
        default="docs/",
        help="Markdown 文档目录路径（默认: docs/）",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="不清空现有向量库",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="同时写入 PostgreSQL（需要数据库连接）",
    )
    args = parser.parse_args()

    # 计算 docs 目录的绝对路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, args.path.lstrip("/\\"))
    if not os.path.isdir(docs_dir):
        print(f"错误: 目录不存在 {docs_dir}")
        sys.exit(1)

    print(f"📂 文档目录: {docs_dir}")
    print(f"🧹 清空现有数据: {not args.no_clear}")
    print(f"💾 写入数据库: {args.db}")
    print()

    db_session = None
    if args.db:
        async with async_session_factory() as session:
            result = await ingest_docs_async(
                docs_dir=docs_dir,
                db_session=session,
                clear_existing=not args.no_clear,
            )
    else:
        # 不连数据库，只写向量库
        result = await ingest_docs_async(
            docs_dir=docs_dir,
            db_session=None,
            clear_existing=not args.no_clear,
        )

    print()
    print("=" * 50)
    print(f"✅ 入库完成！")
    print(f"   文件数: {result['total_files']}")
    print(f"   Chunk 总数: {result['total_chunks']}")
    for f in result["files"]:
        print(f"   - {f['path']} ({f['chunks']} chunks)")


if __name__ == "__main__":
    asyncio.run(main())
