"""pytest fixtures for 强一致性提交协议回归测试。

依赖:pip install pytest pytest-asyncio httpx asyncpg
使用 PostgreSQL 测试数据库(与生产同 dialect,避免 UUID 类型兼容问题)。
"""
import os
import sys
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 确保 backend/ 在 sys.path 上
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base, Document, Question, PracticeSession, PracticeSessionQuestion

# 测试用户
TEST_USER_ID = "test-user-001"

# 固定 UUID(便于断言)
DOC_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
Q1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
Q2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
Q1_STR = str(Q1_ID)
Q2_STR = str(Q2_ID)


@pytest_asyncio.fixture
async def test_engine():
    """创建 PostgreSQL 测试引擎并建表(每个测试函数隔离)。"""
    db_url = "postgresql+asyncpg://postgres:postgres@postgres:5432/interview_test"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # partial unique index(PostgreSQL 原生支持)
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_test_session_user_submission "
            "ON test_sessions (user_id, client_submission_id) "
            "WHERE client_submission_id IS NOT NULL"
        ))

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine):
    """测试用 session factory。"""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_questions(test_session_factory):
    """播种测试题目,返回题目 ID 字符串列表。"""
    async with test_session_factory() as session:
        doc = Document(
            id=DOC_ID,
            title="测试文档",
            content="操作系统内存管理测试内容",
            file_type="md",
            file_path="kb://default/cs/os-memory.md",
            owner_id=TEST_USER_ID,
        )
        session.add(doc)

        q1 = Question(
            id=Q1_ID,
            document_id=DOC_ID,
            type="text",
            content="以下哪种页面置换算法不会出现 Belady 异常？",
            expected_answer="LRU",
            tags=["页面置换", "Belady异常"],
            sections=["操作系统内存管理"],
            difficulty="medium",
        )
        q2 = Question(
            id=Q2_ID,
            document_id=DOC_ID,
            type="code",
            content="补全 Clock 算法的核心逻辑",
            expected_answer="ref_bit 清零",
            tags=["Clock算法"],
            sections=["操作系统内存管理"],
            difficulty="hard",
        )
        session.add(q1)
        session.add(q2)
        await session.commit()

    return [Q1_STR, Q2_STR]


@pytest_asyncio.fixture
async def seed_practice_session(test_session_factory, seed_questions):
    """播种一个练习会话(仅包含 Q1),返回 session_id 字符串。"""
    ps_id = uuid.uuid4()
    async with test_session_factory() as session:
        ps = PracticeSession(
            id=ps_id,
            user_id=TEST_USER_ID,
            mode="adaptive",
            status="in_progress",
            question_count=1,
        )
        session.add(ps)

        psq = PracticeSessionQuestion(
            session_id=ps_id,
            question_id=Q1_ID,
            sequence=0,
        )
        session.add(psq)
        await session.commit()

    return str(ps_id)


@pytest_asyncio.fixture
async def client(test_session_factory, monkeypatch):
    """创建带 patch 的 HTTP client。

    patch 内容:
    - async_session_factory → 测试 PostgreSQL factory
    - evaluate_single / evaluate_code_answer → 固定返回(不调 LLM)
    - get_diagnosis_service → mock 诊断服务
    - get_mastery_service → mock 掌握度服务
    """
    # 关键:patch 路由模块内的 async_session_factory(路由直接引用,不走 DI)
    monkeypatch.setattr("app.routers.test.async_session_factory", test_session_factory)

    # mock LLM 评判
    async def mock_evaluate_single(question: str, answer: str, user_answer: str) -> dict:
        correct = "LRU" in (user_answer or "")
        return {
            "correct": correct,
            "score": 95 if correct else 30,
            "error_type": None if correct else "concept_confusion",
            "explanation": "关键词命中" if correct else "未命中关键概念",
            "error_tags": [] if correct else ["页面置换"],
        }

    async def mock_evaluate_code_answer(
        question: str, user_code: str, test_cases: list = None, question_id: str = None
    ) -> dict:
        correct = "ref_bit" in (user_code or "").lower()
        return {
            "correct": correct,
            "score": 90 if correct else 40,
            "error_type": None if correct else "coding_error",
            "explanation": "逻辑正确" if correct else "缺少访问位清零",
            "error_tags": [] if correct else ["Clock算法"],
        }

    monkeypatch.setattr("app.routers.test.evaluate_single", mock_evaluate_single)
    monkeypatch.setattr("app.routers.test.evaluate_code_answer", mock_evaluate_code_answer)

    # mock 诊断服务
    class MockDiagnosisService:
        def diagnose(self, question, evaluation, knowledge_points, common_mistakes):
            correct = evaluation.get("correct", False)
            return {
                "error_category": None if correct else "concept_confusion",
                "error_conclusion": "答对了" if correct else "概念混淆",
                "knowledge_point_ids": [],
                "evidence_chunk_ids": [],
                "mastery_delta": {} if correct else {"kp-1": -10},
                "review_suggestions": [] if correct else [{"title": "复习页面置换算法"}],
                "weak_kp_ids": [] if correct else ["kp-1"],
            }

    monkeypatch.setattr("app.routers.test.get_diagnosis_service", lambda: MockDiagnosisService())

    # mock 掌握度服务
    class MockMasteryService:
        async def apply_mastery_delta(self, db, user_id, mastery_delta, is_correct,
                                       answer_id, question_id, error_category, error_pattern_id):
            return {}

        async def get_evidence_chunks_for_kps(self, db, kp_ids, limit_per_kp):
            return {}

        async def create_review_tasks_from_diagnosis(self, db, user_id, diagnosis,
                                                      diagnosis_id, question_id, evidence_map):
            return []

        async def get_weak_points(self, db, user_id, limit):
            return []

    monkeypatch.setattr("app.routers.test.get_mastery_service", lambda: MockMasteryService())

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def user_headers():
    """携带测试用户 ID 的请求头。"""
    return {"X-User-ID": TEST_USER_ID}


@pytest.fixture
def unique_sid():
    """每次测试生成独立 submission_id。"""
    return str(uuid.uuid4())
