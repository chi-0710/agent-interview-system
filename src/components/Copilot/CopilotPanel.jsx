import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Loader2 } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { streamFetch } from '../../utils/streamFetch';

/**
 * ChatMessage —— 单条对话气泡
 */
function ChatMessage({ message, isLast }) {
  const isUser = message.role === 'user';
  const isStreaming = useAppStore((s) => s.isStreaming);
  const isLastAssistant = !isUser && isLast;

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* 头像 */}
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5
          ${isUser ? 'bg-primary-500' : 'bg-surface-800 dark:bg-surface-600'}`}
      >
        {isUser ? (
          <User size={14} className="text-white" />
        ) : (
          <Bot size={14} className="text-white" />
        )}
      </div>

      {/* 内容 */}
      <div
        className={`flex-1 min-w-0 ${
          isUser
            ? 'bg-primary-500 text-white rounded-xl rounded-tr-sm'
            : 'bg-surface-100 dark:bg-surface-800 text-surface-800 dark:text-surface-200 rounded-xl rounded-tl-sm'
        } px-3 py-2.5`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div
            className={`text-sm prose-sm max-w-none ${
              isLastAssistant && isStreaming ? 'typing-cursor' : ''
            }`}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * EmptyCopilot —— 无对话时的引导页
 */
function EmptyCopilot() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-surface-400 dark:text-surface-500 px-6">
      <div className="w-16 h-16 mb-4 rounded-2xl bg-surface-100 dark:bg-surface-800 flex items-center justify-center">
        <Bot size={28} className="text-surface-300 dark:text-surface-600" />
      </div>
      <p className="text-sm font-medium mb-1 dark:text-surface-300">AI 伴读助手</p>
      <p className="text-xs text-center leading-relaxed">
        在学习模式下选中任意文字，
        <br />
        点击 "AI 解释" 即可获得深度解析
      </p>
      <div className="mt-6 p-3 bg-surface-50 dark:bg-surface-800 rounded-lg border border-surface-200 dark:border-surface-700 w-full">
        <p className="text-xs text-surface-400 dark:text-surface-500">
          💡 提示：你也可以直接在这里输入问题，AI 将基于知识库内容进行回答。
        </p>
      </div>
    </div>
  );
}

/**
 * CopilotPanel —— AI 伴读对话框
 */
export default function CopilotPanel() {
  const chatMessages = useAppStore((s) => s.chatMessages);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const activeFile = useAppStore((s) => s.activeFile);
  const addChatMessage = useAppStore((s) => s.addChatMessage);
  const setStreaming = useAppStore((s) => s.setStreaming);
  const clearChat = useAppStore((s) => s.clearChat);
  const messagesEndRef = useRef(null);

  const [input, setInput] = React.useState('');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    addChatMessage({ role: 'user', content: text });
    setInput('');
    setStreaming(true);

    // 发起真实 SSE 请求 — 自由对话接口
    let accumulated = '';
    streamFetch(
      '/api/copilot/chat',
      {
        message: text,
        file_path: activeFile?.path || '',
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

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-200 dark:border-surface-700">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-surface-800 dark:bg-surface-600 flex items-center justify-center">
            <Bot size={14} className="text-white" />
          </div>
          <span className="text-sm font-semibold text-surface-800 dark:text-surface-200">AI 伴读</span>
          {isStreaming && (
            <Loader2 size={14} className="text-primary-500 animate-spin" />
          )}
        </div>
        {chatMessages.length > 0 && !isStreaming && (
          <button
            onClick={clearChat}
            className="text-xs text-surface-400 dark:text-surface-500 hover:text-surface-600 dark:hover:text-surface-300 transition-colors"
          >
            清空对话
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {chatMessages.length === 0 ? (
          <EmptyCopilot />
        ) : (
          <>
            {chatMessages.map((msg, i) => (
              <ChatMessage key={i} message={msg} isLast={i === chatMessages.length - 1} />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-surface-200 dark:border-surface-700 p-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题..."
            rows={1}
            disabled={isStreaming}
            className="flex-1 resize-none rounded-lg border border-surface-200 dark:border-surface-700
                       bg-white dark:bg-surface-800 text-surface-800 dark:text-surface-200
                       px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
                       placeholder:text-surface-300 dark:placeholder:text-surface-600 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className="px-4 py-2 bg-surface-800 dark:bg-surface-600 text-white rounded-lg text-sm font-medium
                       hover:bg-surface-700 dark:hover:bg-surface-500 disabled:opacity-30 disabled:cursor-not-allowed
                       transition-colors flex-shrink-0"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
