import React from 'react';
import { Sparkles } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { mockAIStreamResponse, mockAIExplanation } from '../../data/mockData';

/**
 * AIBubble —— 选中文字后弹出的浮动 AI 按钮
 *
 * 功能：
 * - 根据 selection 坐标定位
 * - 点击触发右侧抽屉打开，发起 AI 解释
 */
export default function AIBubble() {
  const selection = useAppStore((s) => s.selection);
  const openRightDrawer = useAppStore((s) => s.openRightDrawer);
  const addChatMessage = useAppStore((s) => s.addChatMessage);
  const setStreaming = useAppStore((s) => s.setStreaming);
  const isStreaming = useAppStore((s) => s.isStreaming);

  const [position, setPosition] = React.useState({ x: 0, y: 0 });

  // 节流更新位置（避免频繁重渲染）
  React.useEffect(() => {
    if (selection) {
      setPosition({ x: selection.x, y: selection.y });
    }
  }, [selection]);

  const handleClick = (e) => {
    e.stopPropagation();
    if (isStreaming) return;

    const userMsg = {
      role: 'user',
      content: `请解释以下内容：\n\n> ${selection.fullText || selection.text}`,
    };
    addChatMessage(userMsg);
    openRightDrawer();
    setStreaming(true);

    // 模拟流式响应
    let accumulated = '';
    mockAIStreamResponse(
      mockAIExplanation,
      (chunk) => {
        accumulated += chunk;
        // 更新最后一条消息
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
      () => {
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
