# Agent 面试模拟与自适应学习系统

> 从"几个 AI 功能拼在一起"到真正的学习闭环 —— 以用户知识点掌握状态为核心的智能面试备考系统。

## 系统定位

**不再是：**
```
文档阅读 + AI 聊天 + 测试 + 错题高亮
```

**而是：**
```
知识内容 → 知识点体系 → 题目体系 → 用户作答 → 能力诊断 → 个性化复习任务 → 再测试验证
```

真正的核心对象不是"文档"或"题目"，而是：

> **用户对某个知识点的掌握状态。**

## 功能概览

### 核心能力

| 模块 | 说明 |
|------|------|
| **三栏动态布局** | 左侧可折叠导航 + 中间阅读/测试区 + 右侧滑出式 AI + 学习状态双面板 |
| **智能 Markdown 渲染器** | react-markdown + GFM 表格 + KaTeX 数学公式 + 代码高亮 + 一键复制 |
| **错题热力图** | 根据诊断结果自动将对应 Markdown 段落渲染为红色渐变高亮 |
| **划线 AI 伴读** | 鼠标选中任意文字 → 浮动"AI 解释"按钮 → 流式解释 |
| **能力诊断** | 7 种错误类型分类，定位薄弱知识点，生成结构化诊断结论 |
| **掌握度模型** | 五状态模型（未学习/学习中/掌握不稳/已掌握/已遗忘），自适应更新 |
| **复习任务系统** | 答错后自动生成个性化复习任务，包含回看、练习、复测 |
| **测试模式** | 单选 / 简答 / 代码补全三种题型，完整学习闭环反馈 |
| **学习状态面板** | 掌握度概览、复习任务列表、薄弱知识点追踪 |
| **深色模式** | 一键切换，localStorage 持久化，首次跟随系统偏好 |

### 错误类型分类

| 错误类型 | 说明 |
|---------|------|
| `concept_missing` | 概念缺失：未掌握核心概念 |
| `concept_confusion` | 概念混淆：将两个相似概念混为一谈 |
| `reasoning_gap` | 推理断裂：知道概念但推理链条不完整 |
| `application_error` | 应用错误：会背概念但不会应用到具体问题 |
| `coding_error` | 代码错误：代码实现存在语法或逻辑错误 |
| `expression_problem` | 表达不完整：理解了但表达有遗漏或不清晰 |
| `careless_error` | 粗心错误：实际掌握但因粗心答错 |

### 掌握度五状态模型

```
unknown（未学习）→ learning（学习中）→ unstable（掌握不稳）→ mastered（已掌握）→ forgotten（已遗忘）
```

每个知识点维护：`mastery_score`、`wrong_count`、`recent_accuracy`、`last_practiced_at`、`last_success_at`、`mastered_at`、`confidence`、`review_due_at`、`streak`（连续正确次数）

### 自适应出题

根据用户掌握状态自动推荐下一组练习题：

- **优先级算法**：复习到期 + 低掌握度 + 高重要性 + 近期错误 + 前置缺失
- **三种模式**：`adaptive`（自适应）、`review`（复习到期）、`explore`（探索新知）
- **练习会话**：`StudyPlan` → `PracticeSession` → `PracticeSessionQuestion` 三级结构

### 错误模式库

将常见错误从描述文本改为可判定的结构化模式：

```python
{
  "id": "tlb_as_cache",
  "error_type": "concept_confusion",
  "cue_terms": ["缓存数据", "CPU Cache"],        # 用户答案中出现错误关键词
  "missing_terms": ["地址翻译", "页表", "VPN"],   # 用户答案中缺失正确关键词
  "target_kp_ids": ["kp-os-tlb", "kp-os-cpu-cache"],
  "diagnostic_template": "将 TLB 误认为 CPU Cache，混淆了缓存对象。"
}
```

诊断服务直接基于用户答案内容匹配错误模式，不依赖 LLM 解释文本。

## 技术栈

### 前端

- **框架**: Vite + React 18
- **样式**: Tailwind CSS (dark mode: class)
- **状态管理**: Zustand
- **Markdown 渲染**: react-markdown + remark-gfm + rehype-highlight + rehype-katex
- **图标**: Lucide React

### 后端

- **框架**: FastAPI (Python 3.10+)
- **ORM**: SQLAlchemy 2.0 + asyncpg
- **数据库**: PostgreSQL（开发期支持降级内存模式）
- **数据库迁移**: Alembic
- **AI 集成**: OpenAI API / 兼容接口
- **结构化输出**: Pydantic + response_format
- **代码评测**: 沙盒执行 + 测试用例注入

## 快速开始

### 后端

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 数据库迁移（可选，无 PostgreSQL 时自动降级为内存模式）
alembic upgrade head

# 注入种子数据
python scripts/seed_questions.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

开发服务器默认运行在 `http://localhost:3000`，后端 API 默认在 `http://localhost:8000`。

## 项目结构

### 前端

```
src/
├── App.jsx                         # 根组件：三栏布局 + TopBar
├── main.jsx                        # 入口
├── index.css                       # 全局样式 + 错题热力图 + Markdown 深色适配
├── store/
│   └── useAppStore.js              # Zustand 全局状态（主题/视图/选区/对话/错题/学习状态）
├── hooks/
│   └── useTextSelection.js         # 选区监听 Hook（防抖 + 坐标提取）
├── utils/
│   ├── metadata.js                 # 错题标签 ↔ 文档 metadata 匹配引擎
│   └── streamFetch.js              # SSE 流式请求工具
├── data/
│   └── mockData.js                 # Mock 数据
└── components/
    ├── Navigation/
    │   └── FileTree.jsx            # IDE 风格文件树
    ├── Reader/
    │   └── SmartReader.jsx         # 智能文本渲染器（错题热力图核心）
    ├── Test/
    │   └── TestMode.jsx            # 考试界面（答题 + 诊断 + 掌握度 + 复习任务）
    ├── Learning/
    │   └── LearningStatusPanel.jsx # 学习状态面板（掌握度/复习任务/薄弱点）
    ├── Copilot/
    │   ├── AIBubble.jsx            # 划线浮动 AI 按钮
    │   └── CopilotPanel.jsx        # 右侧抽屉对话面板
    └── Layout/
        └── RightDrawer.jsx         # 抽屉容器（AI 伴读 + 学习状态双面板）
```

### 后端

```
backend/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置管理
│   ├── database.py                 # 数据库连接
│   ├── models/
│   │   └── __init__.py             # 数据模型（知识点/题目/作答/诊断/掌握度/复习任务）
│   ├── schemas/
│   │   └── __init__.py             # Pydantic Schema
│   ├── routers/
│   │   ├── documents.py            # 文档管理
│   │   ├── questions.py            # 题目管理
│   │   ├── test.py                 # 测试提交（学习闭环核心）
│   │   ├── learning.py             # 学习状态（掌握度/复习任务/知识点树）
│   │   └── copilot.py              # AI 伴读
│   └── services/
│       ├── diagnosis.py            # 能力诊断服务（错误分类 + 错误模式匹配 + 复习建议）
│       ├── mastery.py              # 掌握度服务（五状态模型 + 逐事件更新 + 状态刷新）
│       ├── learning.py             # 学习规划与自适应出题
│       ├── evaluator.py            # 答案评判服务
│       ├── error_tags.py           # 错题标签聚合（向后兼容）
│       ├── llm.py                  # LLM 调用封装
│       ├── structured_output.py    # 结构化输出中间件
│       ├── code_executor.py        # 代码沙盒执行
│       ├── session_manager.py      # 会话管理
│       ├── ingestion.py            # 文档入库（Document + Chunk + KnowledgeLink）
│       ├── chunker.py              # 文档切片
│       └── vector_store.py         # 向量存储
├── alembic/
│   └── versions/                   # 数据库迁移脚本
├── scripts/
│   ├── seed_questions.py           # 种子数据注入（知识点树+题目+关联）
│   └── ingest.py                   # 文档入库脚本
├── docs/                           # 学习资料
│   ├── cs/os-memory.md             # 操作系统内存管理
│   └── frontend/react-fiber.md     # React Fiber 架构
└── requirements.txt
```

## 核心数据模型

### 实体关系

```
Document
  └── DocumentChunk
        └── ChunkKnowledgeLink ──┐
                                  ├── KnowledgePoint ── UserMastery
Question ── QuestionKnowledgeLink ─┘
  └── TestAnswer（Attempt）
        └── Diagnosis
              └── ReviewTask
```

### 核心表

| 表 | 作用 |
|----|------|
| `knowledge_points` | 知识点树，支持三级层级（如 操作系统→内存管理→TLB） |
| `knowledge_relations` | 知识点关系（前置、包含、相似、易混淆） |
| `document_chunks` | 文档段落及其定位信息 |
| `chunk_knowledge_links` | 段落与知识点的多对多关联 |
| `questions` | 题目主体（含评分标准、常见错误模式） |
| `question_knowledge_links` | 题目与知识点的多对多映射（primary/secondary/distractor） |
| `test_answers` | 用户逐题作答记录（Attempt） |
| `diagnoses` | 对错误的结构化诊断（含 evidence_chunks 证据链） |
| `user_mastery` | 用户对每个知识点的掌握状态（五状态模型） |
| `mastery_events` | 掌握度变更事件（逐题逐知识点，可追溯） |
| `review_tasks` | 系统生成的复习任务（含 target + next_action） |
| `study_plans` | 学习计划 |
| `practice_sessions` | 练习会话（自适应出题产物） |
| `practice_session_questions` | 会话题目关联（含选题原因） |

## 学习闭环流程

```
                    ┌─────────────────┐
                    │   知识内容入库   │
                    │  (文档 + 题目)   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   知识点体系     │
                    │  KnowledgePoint  │
                    └────────┬────────┘
                             │
┌──────────────┐              ▼              ┌──────────────┐
│  自适应出题   │ ◀─────────  │  ───────────▶│  复习任务     │
│ StudyPlan    │        ┌────┴────┐          │ ReviewTask   │
│ PracticeSess │        │ 用户作答 │          │ target/next  │
└──────┬───────┘        │UserAttempt│          └──────┬───────┘
       │                └────┬────┘                 │
       │                     │                       │
       ▼                     ▼                       ▼
┌──────────────┐      ┌─────────────────┐     ┌──────────────┐
│  复测验证     │ ────▶│  MasteryEvent   │     │  能力诊断     │
└──────────────┘      │  逐题逐知识点    │     │  +evidence    │
                      └────────┬────────┘     └──────┬───────┘
                               │                     │
                               ▼                     ▼
                        ┌─────────────────┐   ┌──────────────┐
                        │  用户掌握度      │   │ 错误模式匹配  │
                        │  UserMastery    │   │  cue/missing  │
                        │  五状态 + 遗忘   │   └──────────────┘
                        └─────────────────┘
```

## API 概览

### 学习状态 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/learning/mastery` | 获取用户掌握度列表（支持分类、状态筛选） |
| GET | `/api/learning/mastery/{kp_id}` | 获取单个知识点掌握详情 |
| GET | `/api/learning/weak-points` | 获取薄弱知识点 |
| GET | `/api/learning/review-tasks` | 获取复习任务列表 |
| POST | `/api/learning/review-tasks/{id}/complete` | 标记复习任务完成 |
| GET | `/api/learning/knowledge-tree` | 获取知识点树 |
| GET | `/api/learning/knowledge-points/{id}` | 获取知识点详情 |
| **POST** | **`/api/learning/next-session`** | **生成下一个自适应练习会话** |
| GET | `/api/learning/sessions` | 练习会话列表 |
| GET | `/api/learning/plans` | 学习计划列表 |

### 测试 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/test/submit` | 提交答案，返回完整学习闭环结果 |
| GET | `/api/test/sessions` | 测试会话列表 |
| GET | `/api/test/sessions/{id}` | 会话详情 |
| GET | `/api/test/sessions/{id}/answers` | 作答记录 |

## 开发路线

- [x] **第一阶段**：统一知识点体系（文档、题目、错题、高亮全部映射到 KnowledgePoint）
- [x] **第二阶段**：完整答题记录（保存每一次作答、得分、错误类型和反馈）
- [x] **第三阶段**：用户掌握度模型（五状态 + 评分规则 + MasteryEvent 可追溯）
- [x] **第四阶段**：复习任务与学习计划（答错后自动安排回看、练习和复测，target + next_action）
- [x] **第五阶段**：自适应出题（按薄弱点和遗忘风险出题，StudyPlan + PracticeSession）
- [x] **第五阶段增强**：错误模式库（cue_terms + missing_terms 可判定诊断） + 文档证据链路（DocumentChunk + ChunkKnowledgeLink）
- [ ] **第六阶段**：模拟面试（计时、追问、能力报告、岗位维度评估）
- [ ] **第七阶段**：Agent 编排（诊断、规划、出题、反馈形成自动闭环）

## License

MIT
