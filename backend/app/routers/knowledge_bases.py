"""知识库管理路由

- POST   /api/knowledge-bases                        → 创建知识库
- GET    /api/knowledge-bases                        → 列出所有知识库
- GET    /api/knowledge-bases/{id}                   → 获取单个知识库
- DELETE /api/knowledge-bases/{id}                   → 删除知识库
- POST   /api/knowledge-bases/{id}/documents         → 上传文件并触发导入
- GET    /api/knowledge-bases/{id}/jobs/{job_id}     → 查询导入进度
- GET    /api/knowledge-bases/{id}/tree              → 获取知识库内文件树
"""
import os
import uuid
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_factory
from app.dependencies import CurrentUser, get_current_user
from app.models import KnowledgeBase, ImportJob, Document
from app.services.parsers import detect_file_type, is_code_file
from app.services.parsers.storage import save_upload_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


class CreateKnowledgeBaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status: str
    document_count: int
    chunk_count: int
    created_at: str
    updated_at: str


def _kb_to_response(kb: KnowledgeBase) -> dict:
    return {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "tags": kb.tags or [],
        "status": kb.status,
        "document_count": kb.document_count or 0,
        "chunk_count": kb.chunk_count or 0,
        "created_at": kb.created_at.isoformat() if kb.created_at else "",
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else "",
    }


@router.post("")
async def create_knowledge_base(
    req: CreateKnowledgeBaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """创建新知识库"""
    kb = KnowledgeBase(
        name=req.name,
        description=req.description,
        tags=req.tags or [],
        owner_id=current_user.user_id,
        status="draft",
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return _kb_to_response(kb)


@router.get("")
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """列出当前用户的知识库"""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.owner_id == current_user.user_id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()

    items = [_kb_to_response(kb) for kb in kbs]

    default_kb = {
        "id": "default",
        "name": "默认知识库",
        "description": "系统预置知识库",
        "tags": [],
        "status": "ready",
        "document_count": 0,
        "chunk_count": 0,
        "created_at": "",
        "updated_at": "",
    }

    try:
        doc_count_result = await db.execute(
            select(func.count(Document.id)).where(Document.knowledge_base_id == None)
        )
        default_kb["document_count"] = doc_count_result.scalar() or 0
    except Exception:
        pass

    return [default_kb] + items


@router.get("/{knowledge_base_id}")
async def get_knowledge_base(
    knowledge_base_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取单个知识库详情"""
    if knowledge_base_id == "default":
        return {
            "id": "default",
            "name": "默认知识库",
            "description": "系统预置知识库",
            "tags": [],
            "status": "ready",
            "document_count": 0,
            "chunk_count": 0,
            "created_at": "",
            "updated_at": "",
        }

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == current_user.user_id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return _kb_to_response(kb)


@router.delete("/{knowledge_base_id}")
async def delete_knowledge_base(
    knowledge_base_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """删除知识库及其所有关联数据"""
    if knowledge_base_id == "default":
        raise HTTPException(status_code=400, detail="不能删除默认知识库")

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == current_user.user_id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    from app.services.vector_store import delete_by_knowledge_base
    delete_by_knowledge_base(knowledge_base_id)

    await db.delete(kb)
    await db.commit()
    return {"message": "知识库已删除", "id": knowledge_base_id}


async def _process_import_job(
    job_id: str,
    knowledge_base_id: str,
    file_infos: list,
    job_file_details: list,
):
    """后台任务：执行实际的文档解析、切片、向量入库"""
    from app.services.ingestion import ingest_knowledge_base

    async with async_session_factory() as session:
        try:
            result_job = await session.execute(
                select(ImportJob).where(ImportJob.id == job_id)
            )
            job = result_job.scalar_one_or_none()
            if not job:
                return

            result_kb = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
            )
            kb = result_kb.scalar_one_or_none()

            job.current_step = "parsing"
            job.progress_percent = 20
            await session.commit()

            ingestion_result = await ingest_knowledge_base(
                knowledge_base_id=knowledge_base_id,
                file_infos=file_infos,
                db_session=session,
            )

            result_map = {}
            for fi in ingestion_result.get("files", []):
                result_map[fi["filename"]] = fi

            for fd in job_file_details:
                fname = fd["filename"]
                if fname in result_map:
                    fd["status"] = "ready"
                    fd["chunks"] = result_map[fname].get("chunks", 0)

            job.status = "completed"
            job.completed_files = len(ingestion_result.get("files", []))
            job.current_step = "done"
            job.progress_percent = 100
            job.file_details = job_file_details
            if kb:
                kb.status = "ready"
            await session.commit()

        except Exception as e:
            logger.exception(f"后台导入任务失败: {e}")
            try:
                async with async_session_factory() as err_session:
                    result_job = await err_session.execute(
                        select(ImportJob).where(ImportJob.id == job_id)
                    )
                    job = result_job.scalar_one_or_none()
                    result_kb = await err_session.execute(
                        select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
                    )
                    kb = result_kb.scalar_one_or_none()
                    if job:
                        job.status = "failed"
                        job.error_message = str(e)
                        job.file_details = job_file_details
                    if kb:
                        kb.status = "failed"
                    await err_session.commit()
            except Exception:
                pass


@router.post("/{knowledge_base_id}/documents")
async def upload_documents(
    knowledge_base_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """上传文件到知识库，立即返回 job_id，后台异步处理导入"""
    if knowledge_base_id == "default":
        raise HTTPException(status_code=400, detail="默认知识库不支持直接上传")

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == current_user.user_id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    job = ImportJob(
        knowledge_base_id=knowledge_base_id,
        status="processing",
        total_files=len(files),
        completed_files=0,
        failed_files=0,
        current_step="uploading",
        progress_percent=0,
        file_details=[],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    kb.status = "uploading"
    await db.commit()

    file_infos = []
    job_file_details = []
    allowed_extensions = {
        ".md", ".markdown", ".txt",
        ".pdf",
        ".docx", ".doc",
        ".pptx", ".ppt",
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".go", ".c", ".h", ".cpp",
        ".cs", ".sql", ".json", ".yaml", ".yml",
        ".html", ".css", ".sh",
    }

    for f in files:
        filename = f.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()

        if ext not in allowed_extensions:
            job_file_details.append({
                "upload_id": str(uuid.uuid4()),
                "filename": filename,
                "status": "skipped",
                "error": f"不支持的文件类型: {ext}",
            })
            continue

        # 保存文件到磁盘，不直接解码二进制内容
        raw_path = await save_upload_file(
            upload_file=f,
            knowledge_base_id=knowledge_base_id,
            job_id=str(job.id),
        )

        file_type = detect_file_type(filename)
        upload_id = str(uuid.uuid4())
        file_infos.append({
            "upload_id": upload_id,
            "filename": filename,
            "local_path": str(raw_path),
            "extension": ext,
            "file_type": file_type,
        })
        job_file_details.append({
            "upload_id": upload_id,
            "filename": filename,
            "status": "queued",
        })

    if not file_infos:
        job.status = "failed"
        job.error_message = "没有可处理的文件"
        job.file_details = job_file_details
        kb.status = "failed"
        await db.commit()
        raise HTTPException(status_code=400, detail="没有可处理的文件")

    job.file_details = job_file_details
    job.current_step = "processing"
    job.progress_percent = 10
    await db.commit()

    kb.status = "processing"
    await db.commit()

    background_tasks.add_task(
        _process_import_job,
        str(job.id),
        knowledge_base_id,
        file_infos,
        job_file_details,
    )

    return {
        "knowledge_base_id": knowledge_base_id,
        "job_id": str(job.id),
        "status": "processing",
        "files": [
            {
                "filename": fd["filename"],
                "status": fd["status"],
            }
            for fd in job_file_details
        ],
    }


@router.get("/{knowledge_base_id}/jobs/{job_id}")
async def get_import_job(
    knowledge_base_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """查询导入任务进度"""
    # 校验知识库归属当前用户（default 知识库不支持导入任务）
    if knowledge_base_id != "default":
        kb_result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.owner_id == current_user.user_id,
            )
        )
        if not kb_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="知识库不存在")

    result = await db.execute(
        select(ImportJob).where(
            ImportJob.id == job_id,
            ImportJob.knowledge_base_id == knowledge_base_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")

    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress_percent or 0,
        "current_step": job.current_step,
        "total_files": job.total_files,
        "completed_files": job.completed_files,
        "failed_files": job.failed_files,
        "error_message": job.error_message,
        "documents": job.file_details or [],
        "created_at": job.created_at.isoformat() if job.created_at else "",
    }


@router.get("/{knowledge_base_id}/tree")
async def get_knowledge_base_tree(
    knowledge_base_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """获取知识库内文件树"""
    if knowledge_base_id == "default":
        # 默认知识库：返回当前用户的未归类文档 + 共享预置文档（owner_id 为 NULL 或 "__shared__"）
        result = await db.execute(
            select(Document).where(
                Document.knowledge_base_id == None,
                or_(
                    Document.owner_id == current_user.user_id,
                    Document.owner_id == None,
                    Document.owner_id == "__shared__",
                ),
            )
        )
    else:
        # 自定义知识库：先校验归属，再查询文档
        kb_result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.owner_id == current_user.user_id,
            )
        )
        if not kb_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="知识库不存在")
        result = await db.execute(
            select(Document).where(Document.knowledge_base_id == knowledge_base_id)
        )

    docs = result.scalars().all()

    file_nodes = []
    for doc in docs:
        file_nodes.append({
            "id": str(doc.id),
            "title": doc.title,
            "path": doc.file_path or "",
            "type": "file",
            "status": "none",
            "file_type": doc.file_type,
        })

    return {
        "knowledge_base_id": knowledge_base_id,
        "files": file_nodes,
    }
