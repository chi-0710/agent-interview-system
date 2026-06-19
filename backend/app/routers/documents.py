"""文档管理路由

- GET  /api/documents              → 文件树结构
- GET  /api/documents/content      → 原始 Markdown 全文
- POST /api/documents/import       → 导入文件夹
- POST /api/documents/upload       → 上传单文件
"""
import os
import glob
import shutil
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.database import get_db
from app.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

# ---- 工具函数 ----
def _locate_markdown(path: str) -> str:
    """将虚拟路径（如 /docs/cs/os-memory.md）解析为磁盘绝对路径。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    rel_path = path.lstrip("/")
    return os.path.join(base_dir, rel_path)

# ---- 文件树配置 ----
# 与前端 mockFileTree 保持一致的结构定义
FILE_TREE_CONFIG = {
    "cs-basics": {
        "id": "cs-basics",
        "title": "计算机基础",
        "type": "folder",
        "children": {},
    },
    "frontend": {
        "id": "frontend",
        "title": "前端工程",
        "type": "folder",
        "children": {},
    },
    "ml": {
        "id": "ml",
        "title": "机器学习",
        "type": "folder",
        "children": {},
    },
}

# 文件夹映射：文件名前缀 → 文件夹 id
FILE_TO_FOLDER = {
    "os-memory": "cs-basics",
    "os-process": "cs-basics",
    "ds-hashmap": "cs-basics",
    "react-fiber": "frontend",
    "js-eventloop": "frontend",
    "css-layout": "frontend",
    "attention": "ml",
}

# 文件标题映射
FILE_TITLES = {
    "os-memory": "操作系统 - 内存管理",
    "os-process": "操作系统 - 进程与线程",
    "ds-hashmap": "数据结构 - HashMap 原理",
    "react-fiber": "React - Fiber 架构",
    "js-eventloop": "JavaScript - 事件循环",
    "css-layout": "CSS - 布局与 BFC",
    "attention": "Attention 机制详解",
}


def _build_file_tree(db_documents: list[Document]) -> list[dict]:
    """根据数据库中的文档构建文件树"""

    # 初始化文件夹结构
    folders = {}
    for key, cfg in FILE_TREE_CONFIG.items():
        folders[key] = {**cfg, "children": {}}

    # 填充文件
    for doc in db_documents:
        vpath = doc.file_path  # 如 "/docs/cs/os-memory.md"
        if not vpath:
            continue

        # 从路径提取文件名（不含扩展名）
        basename = os.path.splitext(os.path.basename(vpath))[0]  # "os-memory"
        folder_key = FILE_TO_FOLDER.get(basename)
        if not folder_key:
            # 从路径推断文件夹
            parts = vpath.replace("\\", "/").strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "docs":
                folder_key = parts[1]  # "cs", "frontend", "ml"

        if folder_key not in folders:
            folders[folder_key] = {
                "id": folder_key,
                "title": folder_key,
                "type": "folder",
                "children": {},
            }

        file_node = {
            "id": basename,
            "title": FILE_TITLES.get(basename, doc.title),
            "path": vpath,
            "type": "file",
            "status": "none",
        }
        folders[folder_key]["children"][basename] = file_node

    # 转成数组并按字母序排列
    result = []
    for folder_key in sorted(folders.keys()):
        folder = folders[folder_key]
        children = sorted(folder["children"].values(), key=lambda x: x["id"])
        if not children:
            continue
        result.append({
            "id": folder["id"],
            "title": folder["title"],
            "type": "folder",
            "children": children,
        })

    return result


# 备用：从文件系统构建文件树（无需数据库）
def _build_file_tree_from_fs(docs_dir: str) -> list[dict]:
    """从 docs/ 目录扫描构建文件树"""
    folders = {}
    for key, cfg in FILE_TREE_CONFIG.items():
        folders[key] = {**cfg, "children": {}}

    md_files = glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)
    for abs_path in sorted(md_files):
        rel = os.path.relpath(abs_path, docs_dir).replace("\\", "/")
        vpath = f"/docs/{rel}"

        basename = os.path.splitext(os.path.basename(rel))[0]
        folder_key = FILE_TO_FOLDER.get(basename)

        # 从路径推断文件夹
        parts = rel.split("/")
        if not folder_key and len(parts) >= 1:
            folder_key = parts[0]  # "cs", "frontend", "ml"

        if folder_key not in folders:
            folders[folder_key] = {
                "id": folder_key,
                "title": folder_key,
                "type": "folder",
                "children": {},
            }

        # 读取文档提取标题
        title = FILE_TITLES.get(basename, basename)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if first_line.startswith("# ") and not first_line.startswith("## "):
                title = first_line[2:].strip()
        except Exception:
            pass

        folders[folder_key]["children"][basename] = {
            "id": basename,
            "title": title,
            "path": vpath,
            "type": "file",
            "status": "none",
        }

    result = []
    for folder_key in sorted(folders.keys()):
        folder = folders[folder_key]
        children = sorted(folder["children"].values(), key=lambda x: x["id"])
        if not children:
            continue
        result.append({
            "id": folder["id"],
            "title": folder["title"],
            "type": "folder",
            "children": children,
        })

    return result


@router.get("")
async def list_documents():
    """获取文件树（优先从 PostgreSQL，回退到文件系统）"""
    try:
        from app.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(select(Document))
            docs = result.scalars().all()
            if docs:
                return _build_file_tree(list(docs))
    except Exception:
        pass

    # 回退：从文件系统扫描
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    docs_dir = os.path.join(base_dir, "docs")
    if os.path.isdir(docs_dir):
        return _build_file_tree_from_fs(docs_dir)

    # 最终回退：硬编码
    return _build_file_tree_from_fs("")


@router.get("/content")
async def get_document_content(path: str = Query(..., description="文档虚拟路径，如 /docs/cs/os-memory.md")):
    """获取文档完整 Markdown 内容"""
    # 优先从数据库读取
    try:
        from app.database import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(
                select(Document).where(Document.file_path == path)
            )
            doc = result.scalar_one_or_none()
            if doc:
                return {
                    "path": doc.file_path,
                    "title": doc.title,
                    "content": doc.content,
                    "file_type": doc.file_type,
                }
    except Exception:
        pass

    # 回退：从文件系统读取
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # path 格式: /docs/cs/os-memory.md → docs/cs/os-memory.md
    rel_path = path.lstrip("/")
    abs_path = os.path.join(base_dir, rel_path)

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"文档不存在: {path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题
    title = os.path.splitext(os.path.basename(path))[0]
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            break

    return {
        "path": path,
        "title": title,
        "content": content,
        "file_type": "md",
    }


@router.get("/{document_id}")
async def get_document(document_id: str):
    """获取单个文档详情（stub，保留兼容）"""
    return {"id": document_id, "message": "使用 GET /api/documents/content?path=xxx 获取内容"}


@router.post("")
async def create_document():
    """创建文档（stub）"""
    return {"message": "请使用 scripts/ingest.py 入库文档"}
