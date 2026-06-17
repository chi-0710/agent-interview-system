import React from 'react';
import { X } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import CopilotPanel from '../Copilot/CopilotPanel';

/**
 * RightDrawer —— 右侧抽屉面板容器
 */
export default function RightDrawer() {
  const rightDrawerOpen = useAppStore((s) => s.rightDrawerOpen);
  const closeRightDrawer = useAppStore((s) => s.closeRightDrawer);

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
          className="absolute top-3 left-3 p-1.5 rounded-md text-surface-400 dark:text-surface-500
                     hover:text-surface-700 dark:hover:text-surface-200
                     hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors z-10"
        >
          <X size={18} />
        </button>

        <CopilotPanel />
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
