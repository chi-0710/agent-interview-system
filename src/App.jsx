import React, { useEffect, useRef } from 'react';
import {
  BookOpen,
  ClipboardCheck,
  PanelRightOpen,
  Sun,
  Moon,
} from 'lucide-react';
import useAppStore from './store/useAppStore';
import LeftSidebar from './components/Navigation/FileTree';
import SmartReader from './components/Reader/SmartReader';
import TestMode from './components/Test/TestMode';
import RightDrawer from './components/Layout/RightDrawer';
import AIBubble from './components/Copilot/AIBubble';
import CreateKnowledgeBaseModal from './components/KnowledgeBase/CreateKnowledgeBaseModal';
import ImportProgressModal from './components/KnowledgeBase/ImportProgressModal';
import useTextSelection from './hooks/useTextSelection';

/**
 * ThemeToggle —— 日夜模式切换按钮
 */
function ThemeToggle() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const isDark = theme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      className="p-1.5 rounded-md text-surface-400 hover:text-surface-700
                 hover:bg-surface-100 dark:hover:bg-surface-800
                 dark:hover:text-surface-300 transition-colors"
      title={isDark ? '切换到白天模式' : '切换到黑夜模式'}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

/**
 * TopBar —— 顶部工具栏
 */
function TopBar() {
  const viewMode = useAppStore((s) => s.viewMode);
  const setViewMode = useAppStore((s) => s.setViewMode);
  const activeFile = useAppStore((s) => s.activeFile);
  const rightDrawerOpen = useAppStore((s) => s.rightDrawerOpen);
  const openRightDrawer = useAppStore((s) => s.openRightDrawer);

  return (
    <header className="h-12 border-b border-surface-200 dark:border-surface-700
                        bg-white dark:bg-surface-900 flex items-center justify-between
                        px-4 flex-shrink-0 transition-colors">
      {/* Logo / Title */}
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-surface-800 dark:bg-surface-600 flex items-center justify-center">
          <BookOpen size={14} className="text-white" />
        </div>
        <span className="text-sm font-semibold text-surface-800 dark:text-surface-200">
          Agent 面试模拟
        </span>
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-1">
        {activeFile && (
          <div className="flex bg-surface-100 dark:bg-surface-800 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('learn')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5
                ${viewMode === 'learn'
                  ? 'bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200 shadow-sm'
                  : 'text-surface-400 dark:text-surface-500 hover:text-surface-600 dark:hover:text-surface-300'
                }`}
            >
              <BookOpen size={14} />
              学习
            </button>
            <button
              onClick={() => setViewMode('test')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5
                ${viewMode === 'test'
                  ? 'bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200 shadow-sm'
                  : 'text-surface-400 dark:text-surface-500 hover:text-surface-600 dark:hover:text-surface-300'
                }`}
            >
              <ClipboardCheck size={14} />
              测试
            </button>
          </div>
        )}

        {/* Divider */}
        <div className="w-px h-5 bg-surface-200 dark:bg-surface-700 mx-1" />

        {/* Dark/Light Toggle */}
        <ThemeToggle />

        {/* Open AI Panel */}
        {activeFile && !rightDrawerOpen && (
          <button
            onClick={openRightDrawer}
            className="ml-1 p-1.5 rounded-md text-surface-400 dark:text-surface-500
                       hover:text-surface-700 dark:hover:text-surface-300
                       hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
            title="打开 AI 伴读"
          >
            <PanelRightOpen size={18} />
          </button>
        )}
      </div>
    </header>
  );
}

/**
 * MainContent —— 中间主区域容器
 */
function MainContent() {
  const viewMode = useAppStore((s) => s.viewMode);
  const contentRef = useRef(null);

  // 激活选区监听
  useTextSelection(contentRef);

  return (
    <div ref={contentRef} className="flex-1 overflow-y-auto bg-white dark:bg-surface-900 transition-colors">
      {viewMode === 'learn' ? <SmartReader /> : <TestMode />}
    </div>
  );
}

/**
 * App —— 应用根组件
 *
 * 布局：三栏式动态布局
 * ┌──────────┬────────────────────────┬──────────┐
 * │  左侧导航  │      中间主区域           │  AI 抽屉  │
 * │ (可折叠)  │  (学习模式 / 测试模式)      │  (滑出)   │
 * └──────────┴────────────────────────┴──────────┘
 */
export default function App() {
  const theme = useAppStore((s) => s.theme);
  const showCreateKBModal = useAppStore((s) => s.showCreateKBModal);
  const showImportProgress = useAppStore((s) => s.showImportProgress);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, []);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface-50 dark:bg-surface-950 transition-colors">
      <TopBar />

      <div className="flex-1 flex overflow-hidden">
        <LeftSidebar />
        <MainContent />
      </div>

      <AIBubble />
      <RightDrawer />

      {showCreateKBModal && <CreateKnowledgeBaseModal />}
      {showImportProgress && <ImportProgressModal />}
    </div>
  );
}
