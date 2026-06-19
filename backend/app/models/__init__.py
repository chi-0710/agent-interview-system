import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    """知识库文档"""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, txt, md
    file_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    questions = relationship("Question", back_populates="document", cascade="all, delete-orphan")


class Question(Base):
    """面试题目"""
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    content = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    difficulty = Column(String(20), default="medium")  # easy, medium, hard
    category = Column(String(100), nullable=True)
    type = Column(String(20), default="text")  # single, text, code
    options = Column(JSON, nullable=True)       # 单选题选项数组
    tags = Column(JSON, nullable=True)          # 知识点标签数组
    sections = Column(JSON, nullable=True)      # 对应的文档 header 路径（用于热力图匹配）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="questions")
    test_answers = relationship("TestAnswer", back_populates="question", cascade="all, delete-orphan")


class TestSession(Base):
    """测试会话"""
    __tablename__ = "test_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, default="Untitled Session")
    total_questions = Column(Integer, default=0)
    completed_questions = Column(Integer, default=0)
    score = Column(Float, nullable=True)
    status = Column(String(20), default="in_progress")  # in_progress, completed, abandoned
    settings = Column(JSON, nullable=True)  # 面试设置（时间限制、题目范围等）
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    answers = relationship("TestAnswer", back_populates="session", cascade="all, delete-orphan")


class TestAnswer(Base):
    """测试回答"""
    __tablename__ = "test_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_text = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)
    error_type = Column(String(50), nullable=True)
    feedback = Column(Text, nullable=True)
    error_tags = Column(JSON, nullable=True)      # 评判返回的错题标签列表
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("TestSession", back_populates="answers")
    question = relationship("Question", back_populates="test_answers")
