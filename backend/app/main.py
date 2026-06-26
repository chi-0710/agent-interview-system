"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update

from app.config import get_settings
from app.database import async_session_factory
from app.models import ImportJob, KnowledgeBase
from app.routers import documents, questions, test, copilot, learning, knowledge_bases

settings = get_settings()


async def _recover_interrupted_jobs():
    """启动补偿：将上一轮容器重启中断的导入任务标记为 failed，避免永久卡住。

    FastAPI BackgroundTasks 是进程内任务，容器重启即丢失，且新进程不会重新拾起。
    这些中断的 ImportJob/KnowledgeBase 会永远停留在 processing/uploading 状态。
    """
    try:
        async with async_session_factory() as session:
            # 查出中断的任务及其关联知识库 ID
            result = await session.execute(
                select(ImportJob.id, ImportJob.knowledge_base_id).where(
                    ImportJob.status.in_(["processing", "uploading"])
                )
            )
            interrupted = result.all()
            if not interrupted:
                return

            job_ids = [row[0] for row in interrupted]
            kb_ids = [row[1] for row in interrupted if row[1]]

            # 重置中断任务为 failed
            await session.execute(
                update(ImportJob)
                .where(ImportJob.id.in_(job_ids))
                .values(status="failed", error_message="容器重启中断，任务未完成")
            )
            # 关联知识库回退到 failed 状态（用户可删除重建）
            if kb_ids:
                await session.execute(
                    update(KnowledgeBase)
                    .where(KnowledgeBase.id.in_(kb_ids))
                    .values(status="failed")
                )
            await session.commit()
            print(f"[startup] recovered {len(interrupted)} interrupted import job(s)")
    except Exception as e:
        print(f"[startup] recover interrupted jobs failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await _recover_interrupted_jobs()
    print("Application startup complete")
    yield
    print("Application shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - 允许前端跨域访问
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(documents.router)
app.include_router(questions.router)
app.include_router(test.router)
app.include_router(copilot.router)
app.include_router(learning.router)
app.include_router(knowledge_bases.router)


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查"""
    return {"status": "ok"}
