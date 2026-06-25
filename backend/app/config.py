import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/interview_db"

    # LLM API Keys (占位，第二步才会用到)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # LLM 调用参数
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"

    # Docs
    docs_dir: str = ""
    uploads_dir: str = ""

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # App
    app_name: str = "Agent Interview System"
    debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_docs_dir(self) -> str:
        """获取 docs 目录的绝对路径"""
        if self.docs_dir and os.path.isdir(self.docs_dir):
            return os.path.abspath(self.docs_dir)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "docs")

    def get_uploads_dir(self) -> str:
        """获取上传文件目录的绝对路径"""
        if self.uploads_dir and os.path.isdir(self.uploads_dir):
            return os.path.abspath(self.uploads_dir)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        uploads = os.path.join(base, "uploads")
        os.makedirs(uploads, exist_ok=True)
        return uploads


@lru_cache()
def get_settings() -> Settings:
    return Settings()
