"""
AI 会话状态与记忆管理

核心能力：
1. 会话状态后端化（替代前端 Zustand 内存存储）
2. 滑动窗口记忆机制：
   - 保留最近 K 轮原始对话
   - 更早的对话由后台异步生成摘要进行压缩
   - 防止上下文窗口爆炸

会话 ID 由后端生成，前端只需保存 session_id 即可恢复会话。
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# 常量配置
RECENT_MESSAGES_KEEP = 5  # 保留最近 N 轮原始对话
SUMMARY_TRIGGER_THRESHOLD = 8  # 超过 N 轮时触发摘要压缩


@dataclass
class ChatMessage:
    """单条对话消息"""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatSession:
    """对话会话"""
    session_id: str
    user_id: str  # 会话归属用户，用于多用户隔离
    file_path: Optional[str] = None  # 关联的文档路径
    messages: List[ChatMessage] = field(default_factory=list)
    summary: Optional[str] = None  # 历史对话摘要
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str):
        self.messages.append(ChatMessage(role=role, content=content))
        self.last_active = time.time()

    def get_context_messages(self) -> List[dict]:
        """
        获取用于 LLM 调用的上下文消息列表。

        策略：
        - 如果有 summary，放在最前面作为 system context
        - 加上最近 K 轮原始对话
        """
        result = []

        # 摘要作为历史背景
        if self.summary:
            result.append({
                "role": "system",
                "content": f"【历史对话摘要】{self.summary}"
            })

        # 最近 K 轮原始对话
        recent = self.messages[-RECENT_MESSAGES_KEEP * 2:]  # 每轮 2 条（user + assistant）
        result.extend([m.to_dict() for m in recent])

        return result

    def should_summarize(self) -> bool:
        """是否需要触发摘要压缩"""
        total_turns = len(self.messages) // 2
        return total_turns > SUMMARY_TRIGGER_THRESHOLD


class SessionManager:
    """会话管理器（内存版，可扩展到数据库持久化）"""

    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}
        self._summary_lock: set[str] = set()  # 防止并发重复摘要

    def create_session(self, file_path: Optional[str] = None, user_id: str = "default_user") -> str:
        """创建新会话，返回 session_id"""
        session_id = str(uuid.uuid4())
        session = ChatSession(session_id=session_id, user_id=user_id, file_path=file_path)
        self._sessions[session_id] = session
        logger.info(f"[session] created: {session_id} (user={user_id})")
        return session_id

    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[ChatSession]:
        """获取会话。传入 user_id 时校验归属，不匹配返回 None。"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        # 用户隔离：传入 user_id 时必须匹配
        if user_id is not None and session.user_id != user_id:
            return None
        session.last_active = time.time()
        return session

    def add_user_message(self, session_id: str, content: str, file_path: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """添加用户消息"""
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return False
        if file_path and not session.file_path:
            session.file_path = file_path
        session.add_message("user", content)
        return True

    def add_assistant_message(self, session_id: str, content: str, user_id: Optional[str] = None) -> bool:
        """添加助手消息"""
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return False
        session.add_message("assistant", content)

        # 检查是否需要异步摘要
        if session.should_summarize() and session_id not in self._summary_lock:
            self._summary_lock.add(session_id)
            asyncio.create_task(self._async_summarize(session_id))

        return True

    async def _async_summarize(self, session_id: str):
        """异步生成历史对话摘要（后台执行，不阻塞主流程）"""
        try:
            session = self.get_session(session_id)
            if not session:
                return

            # 取需要压缩的旧对话（除了最近 K 轮）
            keep_count = RECENT_MESSAGES_KEEP * 2
            old_messages = session.messages[:-keep_count] if len(session.messages) > keep_count else []

            if not old_messages:
                return

            # 构造摘要 prompt
            old_text = "\n".join([
                f"{m.role}: {m.content[:200]}"
                for m in old_messages
            ])
            summary_prompt = f"""请将以下对话历史压缩为一段简洁的摘要（100字以内），保留关键信息：

{old_text[:1000]}

摘要："""

            try:
                from app.services.llm import chat
                summary = await chat(
                    messages=[{"role": "user", "content": summary_prompt}],
                    temperature=0.3,
                    max_tokens=200,
                )
                session.summary = summary.strip()
                logger.info(f"[session] summary updated for {session_id}: {len(summary)} chars")
            except Exception as e:
                logger.warning(f"[session] summary generation failed: {e}")
        finally:
            self._summary_lock.discard(session_id)

    def get_context_messages(self, session_id: str, user_id: Optional[str] = None) -> List[dict]:
        """获取 LLM 用的上下文消息列表"""
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return []
        return session.get_context_messages()

    def clear_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """清空会话消息（保留 session 本身）"""
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return False
        session.messages = []
        session.summary = None
        return True

    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """删除会话"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        # 用户隔离：传入 user_id 时必须匹配
        if user_id is not None and session.user_id != user_id:
            return False
        del self._sessions[session_id]
        logger.info(f"[session] deleted: {session_id}")
        return True

    def cleanup_expired(self, ttl_seconds: int = 3600) -> int:
        """清理过期会话（1小时无活动）"""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_active > ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info(f"[session] cleaned up {len(expired)} expired sessions")
        return len(expired)


# 全局单例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager