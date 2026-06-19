"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import documents, questions, test, copilot

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    print("Application startup complete")
    yield
    print("Application shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - 允许前端 localhost:3000 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(documents.router)
app.include_router(questions.router)
app.include_router(test.router)
app.include_router(copilot.router)


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查"""
    return {"status": "ok"}
