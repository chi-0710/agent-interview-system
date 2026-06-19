"""Pydantic 请求/响应模型"""
from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel


# ============= Document =============
class DocumentBase(BaseModel):
    title: str
    content: str
    file_type: str
    file_path: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============= Question =============
class QuestionBase(BaseModel):
    content: str
    expected_answer: Optional[str] = None
    difficulty: str = "medium"
    category: Optional[str] = None
    document_id: Optional[UUID] = None


class QuestionCreate(QuestionBase):
    pass


class QuestionResponse(QuestionBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= TestSession =============
class TestSessionBase(BaseModel):
    title: str = "Untitled Session"
    total_questions: int = 0
    settings: Optional[dict] = None


class TestSessionCreate(TestSessionBase):
    question_ids: list[UUID] = []


class TestSessionResponse(TestSessionBase):
    id: UUID
    completed_questions: int = 0
    score: Optional[float] = None
    status: str = "in_progress"
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============= TestAnswer =============
class TestAnswerBase(BaseModel):
    question_id: UUID
    answer_text: Optional[str] = None


class TestAnswerCreate(TestAnswerBase):
    pass


class TestAnswerResponse(TestAnswerBase):
    id: UUID
    session_id: UUID
    score: Optional[float] = None
    feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= Health =============
class HealthResponse(BaseModel):
    status: str
