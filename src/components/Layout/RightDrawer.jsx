import React, { useState } from 'react';
import { X, Bot, Brain } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import CopilotPanel from '../Copilot/CopilotPanel';
import LearningStatusPanel from '../Learning/LearningStatusPanel';

/**
 * RightDrawer —— 右侧抽屉面板容器
 *
 * 支持两个面板切换：
 * - AI 伴读（copilot）
 * - 学习状态（learning）
 */
export default function RightDrawer() {
  const rightDrawerOpen = useAppStore((s) => s.rightDrawerOpen);
  const closeRightDrawer = useAppStore((s) => s.closeRightDrawer);
  const [activePanel, setActivePanel] = useState('copilot');

  if (!rightDrawerOpen) return null;

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 bg-black/20 dark:bg-black/50 z-40 transition-opacity"
        onClick={closeRightDrawer}
      />

      {/* 抽屉 */}
      <div
        className={`fixed right-0 top-0 bottom-0 w-[420px] max-w-[90vw] bg-white dark:bg-surface-900
                    border-l border-surface-200 dark:border-surface-700 shadow-2xl z-50 flex flex-col
                    transition-colors ${rightDrawerOpen ? 'animate-slide-in' : ''}`}
      >
        {/* 关闭按钮 */}
        <button
          onClick={closeRightDrawer}
          className="absolute top-3 left-3 z-10 p-1.5 rounded-md text-surface-400 dark:text-surface-500
                     hover:text-surface-700 dark:hover:text-surface-200
                     hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
        >
          <X size={18} />
        </button>

        {/* 面板切换标签 */}
        <div className="flex items-center justify-center gap-1 pt-3 pb-2 border-b border-surface-200 dark:border-surface-700">
          <button
            onClick={() => setActivePanel('copilot')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activePanel === 'copilot'
                ? 'bg-primary-50 dark:bg-primary-950/50 text-primary-600 dark:text-primary-400'
                : 'text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-300'
            }`}
          >
            <Bot size={14} />
            AI 伴读
          </button>
          <button
            onClick={() => setActivePanel('learning')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activePanel === 'learning'
                ? 'bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400'
                : 'text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-300'
            }`}
          >
            <Brain size={14} />
            学习状态
          </button>
        </div>

        {/* 面板内容 */}
        <div className="flex-1 overflow-hidden">
          {activePanel === 'copilot' && <CopilotPanel />}
          {activePanel === 'learning' && <LearningStatusPanel />}
        </div>
      </div>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
      `}</style>
    </>
  );
}
