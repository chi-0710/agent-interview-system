"""文件存储管理：上传文件的持久化、哈希、读取"""
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import UploadFile


def get_upload_dir(knowledge_base_id: str) -> Path:
    """获取知识库上传文件存储目录"""
    from app.config import settings
    base = Path(settings.get_uploads_dir()) / knowledge_base_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def ensure_kb_upload_dir(knowledge_base_id: str) -> Path:
    """确保知识库上传目录存在并返回路径"""
    return get_upload_dir(knowledge_base_id)


async def save_upload_file(
    upload_file: UploadFile,
    knowledge_base_id: str,
    job_id: str | None = None,
) -> Path:
    """将上传文件保存到磁盘，返回绝对路径

    目录结构: {UPLOADS_DIR}/{knowledge_base_id}/{job_id}/{uuid}_{filename}
    """
    upload_dir = get_upload_dir(knowledge_base_id)
    if job_id:
        upload_dir = upload_dir / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名，避免冲突
    filename = upload_file.filename or "unknown"
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    dest = upload_dir / unique_name

    content = await upload_file.read()
    dest.write_bytes(content)

    return dest.resolve()


def compute_file_hash(content: bytes) -> str:
    """计算文件内容的 SHA-256 哈希"""
    return hashlib.sha256(content).hexdigest()


def read_text_file(path: str | Path, encoding: str = "utf-8") -> str:
    """读取文本文件（带 UTF-8/GBK fallback）"""
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="gbk") as f:
            return f.read()


def read_binary_file(path: str | Path) -> bytes:
    """读取二进制文件"""
    with open(path, "rb") as f:
        return f.read()