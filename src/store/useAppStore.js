import { create } from 'zustand';

/**
 * 从 localStorage 读取初始主题
 */
function getInitialTheme() {
  try {
    const stored = localStorage.getItem('app-theme');
    if (stored === 'dark' || stored === 'light') return stored;
  } catch {}
  // 跟随系统偏好
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

/**
 * 应用主题到 HTML 根元素
 */
function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

/**
 * 全局状态管理 Store
 * 管理：主题、当前文件、视图模式、划线选中、AI 对话、错题标签、侧栏状态
 */
const useAppStore = create((set, get) => ({
  // ========== 主题 ==========
  /** @type {'light' | 'dark'} */
  theme: getInitialTheme(),
  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('app-theme', next); } catch {}
    set({ theme: next });
  },

  // ========== 导航与视图 ==========
  /** @type {'learn' | 'test'} */
  viewMode: 'learn',
  /** @type {{ id: string; title: string; path: string } | null} */
  activeFile: null,
  /** @type {boolean} */
  leftSidebarCollapsed: false,
  /** @type {boolean} */
  rightDrawerOpen: false,

  setViewMode: (mode) => set({ viewMode: mode }),
  setActiveFile: (file) => set({ activeFile: file, viewMode: 'learn', rightDrawerOpen: false }),
  toggleLeftSidebar: () => set((s) => ({ leftSidebarCollapsed: !s.leftSidebarCollapsed })),
  toggleRightDrawer: () => set((s) => ({ rightDrawerOpen: !s.rightDrawerOpen })),
  openRightDrawer: () => set({ rightDrawerOpen: true }),
  closeRightDrawer: () => set({ rightDrawerOpen: false }),

  // ========== 选区监听 ==========
  /** @type {{ text: string; x: number; y: number } | null} */
  selection: null,
  setSelection: (sel) => set({ selection: sel }),
  clearSelection: () => set({ selection: null }),

  // ========== 阅读器标题追踪（供 AI 解释使用）==========
  /** @type {string[]} */
  currentHeaders: [],
  setCurrentHeaders: (headers) => set({ currentHeaders: headers }),

  // ========== AI 对话 ==========
  /** @type {{ role: 'user' | 'assistant'; content: string }[]} */
  chatMessages: [],
  /** @type {boolean} */
  isStreaming: false,

  addChatMessage: (msg) =>
    set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setStreaming: (v) => set({ isStreaming: v }),
  clearChat: () => set({ chatMessages: [], isStreaming: false }),

  // ========== 错题热力图 ==========
  /**
   * 错题标签数组，每个元素形如：
   * { tag: string; count: number; sections: string[] }
   * sections 对应文档中的 header 路径，用于匹配高亮
   */
  /** @type {{ tag: string; count: number; sections: string[] }[]} */
  errorTags: [],
  setErrorTags: (tags) => set({ errorTags: tags }),

  // ========== 测试 ==========
  /** @type {{ id: string; question: string; options?: string[]; answer?: string } | null} */
  currentQuestion: null,
  /** @type {number} */
  questionIndex: 0,
  /** @type {{ questionId: string; userAnswer: string; score: number; feedback: string; errorTags: string[] }[]} */
  testResults: [],

  setCurrentQuestion: (q) => set({ currentQuestion: q }),
  setQuestionIndex: (i) => set({ questionIndex: i }),
  addTestResult: (result) =>
    set((s) => ({ testResults: [...s.testResults, result] })),
  clearTestResults: () => set({ testResults: [], questionIndex: 0, currentQuestion: null }),

  // ========== 学习闭环 ==========
  /** @type {Array} 最近一次测试的诊断结果 */
  diagnoses: [],
  /** @type {Object} 掌握度更新记录 {kp_id: {status, mastery_score, ...}} */
  masteryUpdates: {},
  /** @type {Array} 生成的复习任务 */
  reviewTasks: [],
  /** @type {Array} 薄弱知识点列表 */
  weakPoints: [],
  /** @type {Array} 用户所有知识点掌握情况 */
  userMasteryList: [],

  setDiagnoses: (d) => set({ diagnoses: d }),
  setMasteryUpdates: (m) => set({ masteryUpdates: m }),
  setReviewTasks: (t) => set({ reviewTasks: t }),
  setWeakPoints: (w) => set({ weakPoints: w }),
  setUserMasteryList: (m) => set({ userMasteryList: m }),

  // 加载用户掌握度列表
  loadUserMastery: async (category = null, status = null) => {
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (status) params.set('status', status);
      const resp = await fetch(`/api/learning/mastery?${params.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        set({ userMasteryList: data });
        return data;
      }
    } catch (e) {
      console.error('[store] load user mastery failed:', e);
    }
    return [];
  },

  // 加载复习任务
  loadReviewTasks: async (status = null, limit = 20) => {
    try {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      params.set('limit', limit);
      const resp = await fetch(`/api/learning/review-tasks?${params.toString()}`);
      if (resp.ok) {
        const data = await resp.json();
        set({ reviewTasks: data });
        return data;
      }
    } catch (e) {
      console.error('[store] load review tasks failed:', e);
    }
    return [];
  },

  // 加载薄弱知识点
  loadWeakPoints: async (limit = 10) => {
    try {
      const resp = await fetch(`/api/learning/weak-points?limit=${limit}`);
      if (resp.ok) {
        const data = await resp.json();
        set({ weakPoints: data });
        return data;
      }
    } catch (e) {
      console.error('[store] load weak points failed:', e);
    }
    return [];
  },

  // 完成复习任务
  completeReviewTask: async (taskId) => {
    try {
      const resp = await fetch(`/api/learning/review-tasks/${taskId}/complete`, {
        method: 'POST',
      });
      if (resp.ok) {
        // 更新本地列表
        set((s) => ({
          reviewTasks: s.reviewTasks.map((t) =>
            t.id === taskId ? { ...t, status: 'completed' } : t
          ),
        }));
        return true;
      }
    } catch (e) {
      console.error('[store] complete review task failed:', e);
    }
    return false;
  },
}));

export default useAppStore;
