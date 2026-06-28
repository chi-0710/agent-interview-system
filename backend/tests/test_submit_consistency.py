"""强一致性提交协议回归测试。

14 个测试用例,覆盖:
- 四态协议 (committed / not_committed / outcome_unknown / tracking_disabled)
- 幂等提交 (同内容回放 / 不同内容 409)
- 并发提交 (IntegrityError 回查)
- 严格校验 (重复 qid / 不存在 qid / 归属不符)
- 查询接口 (found / not_found)

依赖 conftest.py 提供的 fixtures:client / seed_questions / seed_practice_session /
user_headers / unique_sid / test_session_factory
"""
import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models import TestSession

pytestmark = pytest.mark.asyncio

TEST_USER_ID = "test-user-001"


async def _count_test_sessions(test_session_factory, user_id=TEST_USER_ID):
    """统计指定用户的 TestSession 记录数。"""
    async with test_session_factory() as session:
        result = await session.execute(
            select(TestSession).where(TestSession.user_id == user_id)
        )
        return len(result.scalars().all())


# ========== 场景 1: 正常提交 → committed ==========

async def test_normal_submit_committed(
    client, seed_questions, user_headers, unique_sid, test_session_factory
):
    """正常提交:200 + committed + evaluation + learningRecord,DB 有 1 条记录。"""
    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["commitStatus"] == "committed"
    assert data["retryable"] is False
    assert data["evaluation"] is not None
    assert data["evaluation"]["score"] == 95
    assert data["learningRecord"] is not None
    assert data["learningRecord"]["sessionId"] is not None

    count = await _count_test_sessions(test_session_factory)
    assert count == 1


# ========== 场景 2: flush 异常 → not_committed ==========

async def test_flush_exception_not_committed(
    client, seed_questions, user_headers, unique_sid, monkeypatch
):
    """persist_learning_record 抛 ValueError → 503 + not_committed + retryable。"""

    async def mock_persist(*args, **kwargs):
        raise ValueError("flush failed")

    monkeypatch.setattr("app.routers.test.persist_learning_record", mock_persist)

    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["commitStatus"] == "not_committed"
    assert data["retryable"] is True
    assert data["learningRecord"] is None
    assert data["evaluation"] is not None


# ========== 场景 3: commit 阶段 OperationalError → outcome_unknown ==========

async def test_commit_phase_operational_error_outcome_unknown(
    client, seed_questions, user_headers, unique_sid, monkeypatch
):
    """persist_learning_record 抛 OperationalError → 503 + outcome_unknown + retryable=False。"""

    async def mock_persist(*args, **kwargs):
        raise OperationalError(
            "INSERT INTO test_sessions ...",
            {},
            Exception("connection lost during commit"),
        )

    monkeypatch.setattr("app.routers.test.persist_learning_record", mock_persist)

    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["commitStatus"] == "outcome_unknown"
    assert data["retryable"] is False
    assert data["learningRecord"] is None
    assert data["evaluation"] is not None


# ========== 场景 4: DB 加载阶段不可用 → 503 无 evaluation ==========

async def test_db_unavailable_at_load_no_evaluation(
    client, seed_questions, user_headers, unique_sid, monkeypatch
):
    """load_submission_questions 抛 HTTPException(503) → 503 + 无 evaluation 字段。"""

    async def mock_load(*args, **kwargs):
        raise HTTPException(status_code=503, detail="数据库不可用，请稍后重试")

    monkeypatch.setattr("app.routers.test.load_submission_questions", mock_load)

    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 503
    data = resp.json()
    # FastAPI HTTPException 默认格式:{"detail": "..."}
    assert "detail" in data
    assert "数据库不可用" in data["detail"]
    # 关键:加载阶段失败不返回 evaluation
    assert "evaluation" not in data or data.get("evaluation") is None


# ========== 场景 5: 评判后 DB 失败 → 返回即时评判 ==========

async def test_db_fail_after_eval_returns_evaluation(
    client, seed_questions, user_headers, unique_sid, monkeypatch
):
    """评判完成后 persist 阶段失败 → 503 + evaluation 非空(含 score/details)+ learningRecord=null。"""

    async def mock_persist(*args, **kwargs):
        raise ValueError("persist failed after evaluation")

    monkeypatch.setattr("app.routers.test.persist_learning_record", mock_persist)

    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 503
    data = resp.json()
    # 重点:即使持久化失败,即时评判仍返回
    assert data["evaluation"] is not None
    assert data["evaluation"]["score"] == 95
    assert len(data["evaluation"]["details"]) > 0
    assert data["learningRecord"] is None


# ========== 场景 6: demo 提交 → tracking_disabled ==========

async def test_demo_submit_tracking_disabled(client, user_headers):
    """POST /api/demo/test/submit → 200 + tracking_disabled + learningRecord=null。"""
    resp = await client.post(
        "/api/demo/test/submit",
        json={
            "answers": [{"question_id": "q-os-1", "user_answer": "LRU"}],
        },
        headers=user_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["commitStatus"] == "tracking_disabled"
    assert data["learningRecord"] is None
    assert data["evaluation"] is not None


# ========== 场景 7: 幂等同内容回放 ==========

async def test_idempotent_same_submission_replays_snapshot(
    client, seed_questions, user_headers, unique_sid, test_session_factory
):
    """同 submission_id + 同 answers 提交两次 → 均 committed,evaluation 一致,DB 仅 1 条。"""
    qids = seed_questions
    payload = {
        "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
        "file_path": "kb://default/cs/os-memory.md",
        "submission_id": unique_sid,
    }

    resp1 = await client.post("/api/test/submit", json=payload, headers=user_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["commitStatus"] == "committed"

    resp2 = await client.post("/api/test/submit", json=payload, headers=user_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["commitStatus"] == "committed"

    # 两次 evaluation 完全一致(快照回放)
    assert data1["evaluation"] == data2["evaluation"]
    assert data1["learningRecord"] == data2["learningRecord"]

    count = await _count_test_sessions(test_session_factory)
    assert count == 1


# ========== 场景 8: 幂等不同内容 → 409 ==========

async def test_idempotent_different_answers_409(
    client, seed_questions, user_headers, unique_sid
):
    """同 submission_id 但不同 answers → 第一次 200,第二次 409。"""
    qids = seed_questions

    payload1 = {
        "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
        "file_path": "kb://default/cs/os-memory.md",
        "submission_id": unique_sid,
    }
    resp1 = await client.post("/api/test/submit", json=payload1, headers=user_headers)
    assert resp1.status_code == 200

    payload2 = {
        "answers": [{"question_id": qids[0], "user_answer": "FIFO"}],
        "file_path": "kb://default/cs/os-memory.md",
        "submission_id": unique_sid,
    }
    resp2 = await client.post("/api/test/submit", json=payload2, headers=user_headers)
    assert resp2.status_code == 409
    detail = resp2.json().get("detail", "")
    assert "不一致" in detail


# ========== 场景 9: 并发提交 → 仅 1 条记录 ==========

async def test_concurrent_submission_single_record(
    client, seed_questions, user_headers, unique_sid, test_session_factory
):
    """asyncio.gather 并发两次相同提交 → 均 committed,DB 仅 1 条 TestSession。"""
    qids = seed_questions
    payload = {
        "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
        "file_path": "kb://default/cs/os-memory.md",
        "submission_id": unique_sid,
    }

    resp_a, resp_b = await asyncio.gather(
        client.post("/api/test/submit", json=payload, headers=user_headers),
        client.post("/api/test/submit", json=payload, headers=user_headers),
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["commitStatus"] == "committed"
    assert resp_b.json()["commitStatus"] == "committed"

    count = await _count_test_sessions(test_session_factory)
    assert count == 1


# ========== 场景 10: 查询提交状态 — 已找到 ==========

async def test_get_submission_status_found(
    client, seed_questions, user_headers, unique_sid
):
    """提交后 GET /api/test/submissions/{sid} → found=true + committed + 快照。"""
    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[0], "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 200

    status_resp = await client.get(
        f"/api/test/submissions/{unique_sid}", headers=user_headers
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["found"] is True
    assert status_data["commitStatus"] == "committed"
    assert status_data["evaluation"] is not None
    assert status_data["learningRecord"] is not None


# ========== 场景 11: 查询提交状态 — 未找到 ==========

async def test_get_submission_status_not_found(client, user_headers):
    """GET 不存在的 submission_id → found=false + not_committed。"""
    random_sid = str(uuid.uuid4())
    resp = await client.get(
        f"/api/test/submissions/{random_sid}", headers=user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["commitStatus"] == "not_committed"
    assert data["evaluation"] is None
    assert data["learningRecord"] is None


# ========== 场景 12: 重复 question_id → 422 ==========

async def test_duplicate_question_id_422(client, seed_questions, user_headers, unique_sid):
    """answers 含两个相同 question_id → 422。"""
    qids = seed_questions
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [
                {"question_id": qids[0], "user_answer": "LRU"},
                {"question_id": qids[0], "user_answer": "FIFO"},
            ],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "重复" in detail


# ========== 场景 13: 不存在的 question_id → 404 ==========

async def test_missing_question_id_404(client, user_headers, unique_sid):
    """提交不存在的 question_id → 404。"""
    fake_qid = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": fake_qid, "user_answer": "LRU"}],
            "file_path": "kb://default/cs/os-memory.md",
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 404
    detail = resp.json().get("detail", "")
    assert "不存在" in detail


# ========== 场景 14: 题目不属于练习会话 → 422 ==========

async def test_question_not_in_practice_session_422(
    client, seed_questions, seed_practice_session, user_headers, unique_sid
):
    """practice_session_id 仅含 Q1,但 answers 提交 Q2 → 422。"""
    qids = seed_questions
    ps_id = seed_practice_session  # 仅含 Q1
    resp = await client.post(
        "/api/test/submit",
        json={
            "answers": [{"question_id": qids[1], "user_answer": "ref_bit"}],
            "practice_session_id": ps_id,
            "submission_id": unique_sid,
        },
        headers=user_headers,
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "不属于" in detail
