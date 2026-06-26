import React from 'react';
import { Sparkles } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { streamFetch } from '../../utils/streamFetch';


/**
 * AIBubble —— 选中文字后弹出的浮动 AI 按钮
 */
export default function AIBubble() {
  const selection = useAppStore((s) => s.selection);
  const activeFile = useAppStore((s) => s.activeFile);
  const currentHeaders = useAppStore((s) => s.currentHeaders);
  const activeKnowledgeBaseId = useAppStore((s) => s.activeKnowledgeBaseId);
  const openRightDrawer = useAppStore((s) => s.openRightDrawer);
  const addChatMessage = useAppStore((s) => s.addChatMessage);
  const setStreaming = useAppStore((s) => s.setStreaming);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const ensureCopilotSession = useAppStore((s) => s.ensureCopilotSession);

  const [position, setPosition] = React.useState({ x: 0, y: 0 });

  React.useEffect(() => {
    if (selection) {
      setPosition({ x: selection.x, y: selection.y });
    }
  }, [selection]);

  const handleClick = async (e) => {
    e.stopPropagation();
    if (isStreaming) return;

    const selectedText = selection.fullText || selection.text;
    const filePath = activeFile?.path || '';
    const blockContext = selection.blockContext || null; // 新增：完整段落上下文

    // 确保存在后端会话（前端只存 session_id，状态由后端持久化）
    const sessionId = await ensureCopilotSession();

    const userMsg = {
      role: 'user',
      content: `请解释以下内容：\n\n> ${selectedText}`,
    };
    addChatMessage(userMsg);
    openRightDrawer();
    setStreaming(true);

    // 发起真实 SSE 请求
    let accumulated = '';
    streamFetch(
      '/api/copilot/explain',
      {
        selected_text: selectedText,
        file_path: filePath,
        knowledge_base_id: activeKnowledgeBaseId || null,
        headers: currentHeaders || [],
        block_context: blockContext,
        session_id: sessionId,
      },
      (chunk) => {
        accumulated += chunk;
        const store = useAppStore.getState();
        const msgs = [...store.chatMessages];
        const lastMsg = msgs[msgs.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          msgs[msgs.length - 1] = { ...lastMsg, content: accumulated };
        } else {
          msgs.push({ role: 'assistant', content: accumulated });
        }
        useAppStore.setState({ chatMessages: msgs });
      },
      (error) => {
        if (error) {
          const store = useAppStore.getState();
          const msgs = [...store.chatMessages];
          msgs.push({ role: 'assistant', content: `❌ ${error}` });
          useAppStore.setState({ chatMessages: msgs });
        }
        setStreaming(false);
      }
    );
  };

  if (!selection) return null;

  return (
    <div
      className="fixed z-50"
      style={{
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -100%)',
      }}
    >
      <button
        onClick={handleClick}
        className="ai-bubble flex items-center gap-1.5 text-white"
      >
        <Sparkles size={14} />
        <span>AI 解释</span>
      </button>
    </div>
  );
}
