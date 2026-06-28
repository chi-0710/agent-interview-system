import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float, JSON, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ============== 知识库 ==============

class KnowledgeBase(Base):
    """知识库 - 独立的学习空间，包含文档、切片、向量索引、知识点"""
    __tablename__ = "knowledge_bases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    owner_id = Column(String(100), nullable=False, default="default_user")
    status = Column(String(30), default="draft")

    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    import_jobs = relationship("ImportJob", back_populates="knowledge_base", cascade="all, delete-orphan")


class ImportJob(Base):
    """知识库导入任务 - 追踪批量文件导入进度"""
    __tablename__ = "import_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default="queued")

    total_files = Column(Integer, default=0)
    completed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    current_step = Column(String(50), nullable=True)
    progress_percent = Column(Integer, default=0)

    file_details = Column(JSON, nullable=True)

    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_base = relationship("KnowledgeBase", back_populates="import_jobs")


# ============== 文档与内容 ==============

class Document(Base):
    """知识库文档"""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_id = Column(String(100), nullable=False, default="default_user", index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, pptx, txt, md, py, js, ...
    file_path = Column(String(1000), nullable=True)

    # 来源元数据（支持多格式和 Git 仓库）
    source_type = Column(String(30), nullable=False, default="upload")  # upload, git_repository, generated
    source_uri = Column(String(2000), nullable=True)  # Git 地址、原始文件路径、网页 URL
    content_hash = Column(String(64), nullable=True)  # SHA-256，用于去重
    source_metadata = Column(JSON, nullable=True)     # commit SHA、分支、页数、语言等
    parse_status = Column(String(30), nullable=False, default="ready")  # ready, partial, needs_ocr, failed
    parse_warning = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    questions = relationship("Question", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """文档段落/分块，带定位信息"""
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # 在文档中的顺序
    headers = Column(JSON, nullable=True)  # 所属 header 路径数组，如 ["操作系统内存管理", "页面置换算法"]
    section_path = Column(String(1000), nullable=True)  # 完整 section 路径字符串
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="chunks")
    knowledge_links = relationship("ChunkKnowledgeLink", back_populates="chunk", cascade="all, delete-orphan")


# ============== 知识点体系 ==============

class KnowledgePoint(Base):
    """知识点（核心实体）

    支持树形结构：操作系统 → 内存管理 → TLB
    """
    __tablename__ = "knowledge_points"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)  # 知识点名称，如 "TLB"
    description = Column(Text, nullable=True)   # 简要描述
    parent_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True)
    level = Column(Integer, default=1)  # 层级：1=一级，2=二级，3=三级
    path = Column(String(1000), nullable=True)  # 完整路径，如 "操作系统/内存管理/TLB"
    importance = Column(Integer, default=5)  # 面试重要性 1-10
    category = Column(String(100), nullable=True)  # 学科分类
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    parent = relationship("KnowledgePoint", remote_side=[id], back_populates="children")
    children = relationship("KnowledgePoint", back_populates="parent", cascade="all, delete-orphan")
    question_links = relationship("QuestionKnowledgeLink", back_populates="knowledge_point", cascade="all, delete-orphan")
    chunk_links = relationship("ChunkKnowledgeLink", back_populates="knowledge_point", cascade="all, delete-orphan")
    mastery_records = relationship("UserMastery", back_populates="knowledge_point", cascade="all, delete-orphan")
    review_tasks = relationship("ReviewTask", back_populates="knowledge_point", cascade="all, delete-orphan")


class KnowledgeRelation(Base):
    """知识点之间的关系：前置、包含、相似、易混淆"""
    __tablename__ = "knowledge_relations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(30), nullable=False)  # prerequisite, contains, similar, confused_with
    strength = Column(Float, default=1.0)  # 关系强度 0-1
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('source_id', 'target_id', 'relation_type', name='uq_kp_relation'),
    )


class ChunkKnowledgeLink(Base):
    """文档段落与知识点的关联（多对多）"""
    __tablename__ = "chunk_knowledge_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    relevance = Column(Float, default=1.0)  # 相关度 0-1
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('chunk_id', 'knowledge_point_id', name='uq_chunk_kp'),
    )

    chunk = relationship("DocumentChunk", back_populates="knowledge_links")
    knowledge_point = relationship("KnowledgePoint", back_populates="chunk_links")


# ============== 学习规划 ==============

class StudyPlan(Base):
    """学习计划"""
    __tablename__ = "study_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user")
    name = Column(String(200), nullable=False)
    objective = Column(Text, nullable=True)  # 学习目标描述
    status = Column(String(20), default="active")  # active, completed, paused
    config = Column(JSON, nullable=True)  # { target_kp_ids, difficulty, sessions_per_week }
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sessions = relationship("PracticeSession", back_populates="plan", cascade="all, delete-orphan")


class PracticeSession(Base):
    """练习会话：一次刷题/测试"""
    __tablename__ = "practice_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user")
    plan_id = Column(UUID(as_uuid=True), ForeignKey("study_plans.id", ondelete="SET NULL"), nullable=True)
    mode = Column(String(30), default="adaptive")  # adaptive, review, explore, custom
    # adaptive: 自适应出题; review: 复习到期; explore: 探索新知识点
    status = Column(String(20), default="in_progress")  # in_progress, completed, abandoned
    question_count = Column(Integer, default=5)
    score = Column(Float, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    plan = relationship("StudyPlan", back_populates="sessions")
    session_questions = relationship("PracticeSessionQuestion", back_populates="session", cascade="all, delete-orphan")


class PracticeSessionQuestion(Base):
    """练习会话中的题目"""
    __tablename__ = "practice_session_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, default=0)  # 题目顺序
    selected_reason = Column(String(50), nullable=True)  # 选题原因
    # review_due: 复习到期; low_mastery: 低掌握度; high_importance: 高重要性; prerequisite: 前置知识
    score = Column(Float, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    answered_at = Column(DateTime, nullable=True)

    session = relationship("PracticeSession", back_populates="session_questions")
    question = relationship("Question")


# ============== 题目体系 ==============

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
    correct_option = Column(Integer, nullable=True)  # 选择题正确答案索引 (0=A, 1=B, 2=C, 3=D)
    option_explanations = Column(JSON, nullable=True)  # 每个选项的解释数组
    tags = Column(JSON, nullable=True)          # 知识点标签数组（兼容旧逻辑）
    sections = Column(JSON, nullable=True)      # 对应的文档 header 路径（兼容旧逻辑）
    rubric = Column(JSON, nullable=True)        # 评分标准（结构化）
    common_mistakes = Column(JSON, nullable=True)  # 常见错误映射 [{error_type, description, knowledge_point_ids}]
    follow_up_questions = Column(JSON, nullable=True)  # 追问题目 ID 列表
    status = Column(String(20), default="active")  # active, deprecated
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="questions")
    test_answers = relationship("TestAnswer", back_populates="question", cascade="all, delete-orphan")
    knowledge_links = relationship("QuestionKnowledgeLink", back_populates="question", cascade="all, delete-orphan")
    diagnoses = relationship("Diagnosis", back_populates="question", cascade="all, delete-orphan")


class QuestionKnowledgeLink(Base):
    """题目与知识点的多对多映射"""
    __tablename__ = "question_knowledge_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(30), default="primary")  # primary, secondary, distractor
    weight = Column(Float, default=1.0)  # 权重 0-1
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('question_id', 'knowledge_point_id', name='uq_question_kp'),
    )

    question = relationship("Question", back_populates="knowledge_links")
    knowledge_point = relationship("KnowledgePoint", back_populates="question_links")


# ============== 测试与作答 ==============

class TestSession(Base):
    """测试/练习会话"""
    __tablename__ = "test_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user", index=True)
    title = Column(String(500), nullable=False, default="Untitled Session")
    mode = Column(String(30), default="learn")  # learn, mock_interview
    total_questions = Column(Integer, default=0)
    completed_questions = Column(Integer, default=0)
    score = Column(Float, nullable=True)
    status = Column(String(20), default="in_progress")  # in_progress, completed, abandoned
    settings = Column(JSON, nullable=True)  # 面试设置（时间限制、题目范围等）
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    answers = relationship("TestAnswer", back_populates="session", cascade="all, delete-orphan")


class TestAnswer(Base):
    """用户逐题作答记录（Attempt）"""
    __tablename__ = "test_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_text = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)
    error_type = Column(String(50), nullable=True)
    feedback = Column(Text, nullable=True)
    error_tags = Column(JSON, nullable=True)
    time_spent = Column(Integer, nullable=True)  # 答题用时（秒）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("TestSession", back_populates="answers")
    question = relationship("Question", back_populates="test_answers")
    diagnoses = relationship("Diagnosis", back_populates="answer", cascade="all, delete-orphan")


# ============== 能力诊断 ==============

class Diagnosis(Base):
    """对错误的结构化诊断"""
    __tablename__ = "diagnoses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id = Column(UUID(as_uuid=True), ForeignKey("test_answers.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    error_category = Column(String(50), nullable=True)
    # concept_missing | concept_confusion | reasoning_gap | application_error | coding_error | expression_problem | careless_error
    error_conclusion = Column(Text, nullable=True)  # 诊断结论
    knowledge_point_ids = Column(JSON, nullable=True)  # 涉及的薄弱知识点 ID 列表
    evidence_chunk_ids = Column(JSON, nullable=True)  # 资料证据 chunk ID 列表
    mastery_delta = Column(JSON, nullable=True)  # 掌握度变化 {kp_id: delta}
    review_suggestions = Column(JSON, nullable=True)  # 复习建议 [{action, kp_id, description}]
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    answer = relationship("TestAnswer", back_populates="diagnoses")
    question = relationship("Question", back_populates="diagnoses")


# ============== 用户掌握度 ==============

class UserMastery(Base):
    """用户对每个知识点的掌握状态

    状态机：unknown → learning → unstable → mastered → forgotten
    """
    __tablename__ = "user_mastery"
    __table_args__ = (
        UniqueConstraint('user_id', 'knowledge_point_id', name='uq_user_kp_mastery'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user")
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="unknown")  # unknown, learning, unstable, mastered, forgotten
    mastery_score = Column(Float, default=0.0)  # 掌握度分数 0-100
    wrong_count = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    recent_accuracy = Column(Float, nullable=True)  # 最近 N 次的正确率
    last_practiced_at = Column(DateTime, nullable=True)  # 最后一次练习时间
    last_success_at = Column(DateTime, nullable=True)  # 最后一次答对时间
    last_reviewed_at = Column(DateTime, nullable=True)  # 最后一次复习时间
    mastered_at = Column(DateTime, nullable=True)  # 首次达到 mastered 的时间
    confidence = Column(Float, default=0.0)  # 系统对掌握状态的置信度 0-1
    review_due_at = Column(DateTime, nullable=True)  # 下次复习时间
    streak = Column(Integer, default=0)  # 连续正确次数
    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_point = relationship("KnowledgePoint", back_populates="mastery_records")
    mastery_events = relationship("MasteryEvent", back_populates="mastery", cascade="all, delete-orphan")


class MasteryEvent(Base):
    """掌握度变更事件（逐题逐知识点记录）

    每道题的每个知识点都会产生一条事件记录，用于追溯掌握度变化历史。
    """
    __tablename__ = "mastery_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user")
    mastery_id = Column(UUID(as_uuid=True), ForeignKey("user_mastery.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    answer_id = Column(UUID(as_uuid=True), ForeignKey("test_answers.id", ondelete="SET NULL"), nullable=True)
    question_id = Column(UUID(as_uuid=True), nullable=True)

    # 事件信息
    event_type = Column(String(30), nullable=False)  # answer_correct, answer_wrong, review, manual_adjust
    is_correct = Column(Boolean, nullable=True)
    delta = Column(Float, default=0.0)  # 本次分数变化量
    score_before = Column(Float, nullable=True)  # 变化前分数
    score_after = Column(Float, nullable=True)  # 变化后分数
    status_before = Column(String(20), nullable=True)  # 变化前状态
    status_after = Column(String(20), nullable=True)  # 变化后状态

    # 错误分类（答错时）
    error_category = Column(String(50), nullable=True)  # concept_missing, concept_confusion, ...
    error_pattern_id = Column(String(100), nullable=True)  # 匹配到的错误模式 ID

    extra_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    mastery = relationship("UserMastery", back_populates="mastery_events")


# ============== 复习任务 ==============

class ReviewTask(Base):
    """系统生成的复习任务"""
    __tablename__ = "review_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, default="default_user")
    knowledge_point_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=True)
    task_type = Column(String(30), nullable=False)
    # review_material | practice_question | concept_comparison | follow_up_test
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    action = Column(JSON, nullable=True)  # 具体动作 {type, target_id, ...}
    target = Column(JSON, nullable=True)  # 任务目标 {document_id, chunk_ids, question_ids, ...}
    next_action = Column(JSON, nullable=True)  # 完成后下一步动作 {type, ...}
    priority = Column(Integer, default=5)  # 优先级 1-10
    status = Column(String(20), default="pending")  # pending, in_progress, completed, skipped
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    source_diagnosis_id = Column(UUID(as_uuid=True), nullable=True)  # 来源于哪个诊断
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_point = relationship("KnowledgePoint", back_populates="review_tasks")
