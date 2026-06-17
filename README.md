# Agent 面试模拟与自适应学习系统

> 将散落的工具整合成有机的学习机器 —— 基于 React 的智能面试备考前端系统。

## 功能概览

| 模块 | 说明 |
|------|------|
| **三栏动态布局** | 左侧可折叠导航 + 中间阅读/测试区 + 右侧滑出式 AI 抽屉 |
| **智能 Markdown 渲染器** | react-markdown + GFM 表格 + KaTeX 数学公式 + 代码高亮 + 一键复制 |
| **错题热力图** | 根据后端返回的 `errorTags` 自动将对应 Markdown 段落渲染为红色渐变高亮 |
| **划线 AI 伴读** | 鼠标选中任意文字 → 浮动"AI 解释"按钮 → 流式解释 |
| **测试模式** | 单选 / 简答 / 代码补全三种题型，AI 评判反馈 + 错因分析 |
| **深色模式** | 一键切换，localStorage 持久化，首次跟随系统偏好 |
| **AI 对话面板** | 右侧抽屉，支持流式打字机效果和 Markdown 渲染 |

## 技术栈

- **框架**: Vite + React 18
- **样式**: Tailwind CSS (dark mode: class)
- **状态管理**: Zustand
- **Markdown 渲染**: react-markdown + remark-gfm + rehype-highlight + rehype-katex
- **图标**: Lucide React
- **AI 流式**: Vercel AI SDK (useChat / useCompletion)

## 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览构建结果
npm run preview
```

开发服务器默认运行在 `http://localhost:3000`。

## 项目结构

```
src/
├── App.jsx                         # 根组件：三栏布局 + TopBar
├── main.jsx                        # 入口
├── index.css                       # 全局样式 + 错题热力图 + Markdown 深色适配
├── store/
│   └── useAppStore.js              # Zustand 全局状态（主题/视图/选区/对话/错题/测试）
├── hooks/
│   └── useTextSelection.js         # 选区监听 Hook（防抖 + 坐标提取）
├── utils/
│   └── metadata.js                 # 错题标签 ↔ 文档 metadata 匹配引擎
├── data/
│   └── mockData.js                 # Mock 数据（文件树、Markdown、题库、AI 响应）
└── components/
    ├── Navigation/
    │   └── FileTree.jsx            # IDE 风格文件树（🔥高频错题 / ✅已通过）
    ├── Reader/
    │   └── SmartReader.jsx         # 智能文本渲染器（错题热力图核心）
    ├── Test/
    │   └── TestMode.jsx            # 考试界面（卡片式 / 多种题型 / 评判反馈）
    ├── Copilot/
    │   ├── AIBubble.jsx            # 划线浮动 AI 按钮
    │   └── CopilotPanel.jsx        # 右侧抽屉对话面板
    └── Layout/
        └── RightDrawer.jsx         # 抽屉容器（滑入动画）
```

## 数据流转

```
资料入库: Markdown → LangChain 切片 → 向量数据库 + PostgreSQL
伴读学习: 划线选中 → FastAPI → LLM → 流式渲染
检验评判: 触发测试 → 抽取题库 → 用户作答 → Codex 评分 → JSON 反馈
复盘反哺: 错题标签 → 对比文档 Metadata → 前端段落红色高亮
```

## License

MIT
