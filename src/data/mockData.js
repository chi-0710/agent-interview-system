/**
 * Mock 数据 —— 模拟后端返回的文件树、Markdown 内容和题库
 */

// ---- 文件树 ----
export const mockFileTree = [
  {
    id: 'cs-basics',
    title: '计算机基础',
    type: 'folder',
    children: [
      {
        id: 'os-memory',
        title: '操作系统 - 内存管理',
        path: '/docs/cs/os-memory.md',
        type: 'file',
        status: 'hot',
      },
    ],
  },
  {
    id: 'frontend',
    title: '前端工程',
    type: 'folder',
    children: [
      {
        id: 'react-fiber',
        title: 'React - Fiber 架构',
        path: '/docs/frontend/react-fiber.md',
        type: 'file',
        status: 'hot',
      },
    ],
  },
];

// ---- Markdown 文档内容 ----
export const mockMarkdownContent = {
  '/docs/cs/os-memory.md': `# 操作系统内存管理

## 虚拟内存

虚拟内存是操作系统提供的一种抽象，它让每个进程都以为自己独占连续的地址空间。

### 核心概念

- **虚拟地址**：进程中使用的地址，由 CPU 中的 MMU（Memory Management Unit）翻译为物理地址。
- **物理地址**：内存硬件上的实际地址。
- **页面（Page）**：虚拟内存的基本单位，通常大小为 4KB。

\`\`\`c
// 简单的地址转换示意
phys_addr = page_table[vpn] + offset;
\`\`\`

## 分页机制

分页是现代操作系统内存管理的基础。页表存储了虚拟页到物理页的映射。

### 页表结构

| 层级 | 名称 | 用途 |
|------|------|------|
| Level 1 | PGD (Page Global Directory) | 顶级目录 |
| Level 2 | PMD (Page Middle Directory) | 中间目录 |
| Level 3 | PTE (Page Table Entry) | 页表项 |

\`\`\`c
typedef struct {
    unsigned long pte_low;
    unsigned long pte_high;
} pte_t;
\`\`\`

## TLB 与缓存

TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的转换。

> **关键问题**：当进程切换时，TLB 如何处理？答案是 TLB flush —— 在 x86 架构上，写入 CR3 寄存器会自动刷掉所有 TLB 条目，除非使用了 PCID（Process-Context Identifier）。

### 短期记忆 vs 长期记忆

从认知科学角度看，TLB 就像计算机的"短期记忆"——容量小、速度快、易失。而物理内存则更像是"长期记忆"的载体。

## 页面置换算法

当物理内存不足时，操作系统必须决定将哪些页面换出到磁盘。

常见算法包括：
- **FIFO**：先进先出，简单但容易产生 Belady 异常
- **LRU**：最近最少使用，效果好但实现成本高
- **Clock 算法**：LRU 的近似实现，Linux 默认使用

\`\`\`python
def clock_algorithm(pages, frames):
    """Clock 页面置换算法示意"""
    memory = [-1] * frames
    ref_bit = [0] * frames
    pointer = 0
    faults = 0
    
    for page in pages:
        if page in memory:
            ref_bit[memory.index(page)] = 1
            continue
        
        faults += 1
        while ref_bit[pointer] == 1:
            ref_bit[pointer] = 0
            pointer = (pointer + 1) % frames
        
        memory[pointer] = page
        ref_bit[pointer] = 1
        pointer = (pointer + 1) % frames
    
    return faults
\`\`\`

## Belady 异常

Belady 异常是指：在某些页面置换算法（特别是 FIFO）中，增加物理页框数反而导致更多的缺页中断。这是一个反直觉的现象。LRU 算法不会出现 Belady 异常。
`,

  '/docs/frontend/react-fiber.md': `# React Fiber 架构深度解析

## 为什么需要 Fiber？

React 16 之前使用的 Stack Reconciler 是同步递归的。一旦开始渲染，就必须一气呵成地完成，无法中断。对于大型应用，这意味着主线程可能被长时间阻塞。

### 核心问题

- **同步不可中断**：递归过程无法被打断
- **帧率下降**：超过 16ms 的渲染会导致掉帧
- **用户交互延迟**：输入事件被排队等待

## Fiber 节点结构

每个 Fiber 节点就是一个 JavaScript 对象，代表一个"工作单元"：

\`\`\`typescript
interface Fiber {
  tag: WorkTag;           // 组件类型
  key: null | string;
  elementType: any;
  
  // 树结构指针
  return: Fiber | null;   // 父节点
  child: Fiber | null;    // 第一个子节点
  sibling: Fiber | null;  // 下一个兄弟节点
  
  // 副作用
  effectTag: Flags;
  nextEffect: Fiber | null;
  
  // 状态
  memoizedState: any;     // Hook 链表
  memoizedProps: any;
  pendingProps: any;
  
  // 调度优先级
  lanes: Lanes;
  childLanes: Lanes;
  
  alternate: Fiber | null; // 双缓冲
}
\`\`\`

## 双缓冲机制

React 维护两棵 Fiber 树：
- **Current Tree**：当前屏幕上显示的树
- **Work-in-Progress Tree**：正在构建的新树

通过 \`alternate\` 指针互相引用，完成更新后两棵树角色互换，实现无缝切换。

## 调度优先级

React 使用 Lane 模型管理更新优先级：

\`\`\`typescript
// 优先级从高到低
const SyncLane = 0b0001;           // 同步渲染
const InputContinuousLane = 0b0010; // 连续输入
const DefaultLane = 0b0100;        // 默认
const IdleLane = 0b1000;           // 空闲时处理
\`\`\`

## 时间切片 (Time Slicing)

Fiber 通过协作式调度实现了时间切片：
1. 每个工作单元执行后，检查剩余时间
2. 如果时间不够（< 5ms），主动让出主线程
3. 浏览器处理完高优先级事件后，恢复工作

\`\`\`javascript
function workLoop(deadline) {
  let shouldYield = false;
  while (nextUnitOfWork && !shouldYield) {
    nextUnitOfWork = performUnitOfWork(nextUnitOfWork);
    shouldYield = deadline.timeRemaining() < 1;
  }
  if (!nextUnitOfWork && workInProgressRoot) {
    commitRoot();
  }
  requestIdleCallback(workLoop);
}
\`\`\`

> **重要**：Fiber 架构中的"短期记忆"体现在 \`memoizedState\` 和 \`memoizedProps\` 中。React 会保留上一次渲染的结果，以便在重新渲染时进行对比，减少不必要的 DOM 操作。
`,
};

// ---- 题库 ----
export const mockQuestions = {
  '/docs/cs/os-memory.md': [
    {
      id: 'q-os-1',
      type: 'single',
      question: '以下哪种页面置换算法不会出现 Belady 异常？',
      options: ['FIFO', 'LRU', 'Clock', 'OPT'],
      answer: 'LRU',
      tags: ['页面置换', 'Belady异常'],
    },
    {
      id: 'q-os-2',
      type: 'text',
      question: '进程切换时，x86 架构写入哪个寄存器会触发 TLB flush？',
      answer: 'CR3 寄存器。写入 CR3 会使得所有 TLB 条目被刷新（除非启用 PCID）。这是因为 CR3 存储了页表基址，进程切换时必须更新它。',
      tags: ['TLB', 'x86架构'],
    },
    {
      id: 'q-os-3',
      type: 'code',
      question: '补全以下 Clock 页面置换算法的核心循环逻辑：',
      code: 'while ref_bit[pointer] == 1:\n    # 你的代码\n    pointer = (pointer + 1) % frames',
      answer: 'ref_bit[pointer] = 0',
      tags: ['页面置换', 'Clock算法'],
    },
  ],
  '/docs/frontend/react-fiber.md': [
    {
      id: 'q-react-1',
      type: 'single',
      question: 'React Fiber 架构中，两棵 Fiber 树通过哪个字段互相引用？',
      options: ['return', 'sibling', 'alternate', 'child'],
      answer: 'alternate',
      tags: ['Fiber', '双缓冲'],
    },
    {
      id: 'q-react-2',
      type: 'text',
      question: '为什么 Fiber 架构被称为"协作式调度"？它与抢占式调度有什么区别？',
      answer: 'Fiber 采用协作式调度，每个工作单元完成后主动检查是否需要让出主线程（yield），而不是被外部强制中断。抢占式调度由操作系统强制切换，不依赖任务主动释放。React 选择协作式是因为它能更好地控制渲染的一致性。',
      tags: ['Fiber', '调度'],
    },
  ],
};

// ---- 错题标签（模拟后端返回） ----
export const mockErrorTags = [
  {
    tag: '页面置换',
    count: 3,
    sections: ['页面置换算法'],
  },
  {
    tag: 'Belady异常',
    count: 2,
    sections: ['Belady 异常'],
  },
  {
    tag: 'TLB',
    count: 1,
    sections: ['TLB 与缓存'],
  },
  {
    tag: '短期记忆',
    count: 1,
    sections: ['短期记忆 vs 长期记忆'],
  },
];

// ---- 模拟 AI 流式响应 ----
export function mockAIStreamResponse(text, onChunk, onDone) {
  let i = 0;
  const chars = text.split('');
  const timer = setInterval(() => {
    if (i < chars.length) {
      onChunk(chars[i]);
      i++;
    } else {
      clearInterval(timer);
      onDone();
    }
  }, 25);
  return () => clearInterval(timer);
}

export const mockAIExplanation = `这段代码实现了 **Clock 页面置换算法**（也称为第二次机会算法）。

## 核心思想

Clock 算法是 LRU 的近似实现，用一个**环形缓冲区**模拟时钟指针：

1. **ref_bit** 数组记录每个页框是否被访问过（1 = 已访问）
2. **pointer** 指针像时钟一样循环扫描
3. 遇到 ref_bit=1 的页面，给它"第二次机会"，将其置为 0
4. 遇到 ref_bit=0 的页面，直接换出

## 复杂度分析

- 时间复杂度：O(n) 最坏情况（所有页面都被访问过）
- 空间复杂度：O(frames + n)

相比真正的 LRU（需要维护访问时间戳），Clock 算法用极小的开销达到了接近 LRU 的效果。`;

export const mockTestFeedback = {
  score: 78,
  summary: '整体掌握了基本概念，但对 TLB flush 和 Belady 异常的细节理解不够深入。',
  details: [
    {
      questionId: 'q-os-1',
      correct: false,
      userAnswer: 'FIFO',
      correctAnswer: 'LRU',
      explanation: 'FIFO 正是最典型的会出现 Belady 异常的算法。LRU 和 OPT（最优置换）都属于栈算法（Stack Algorithm），不会出现 Belady 异常。',
      errorType: '概念混淆',
      errorTags: ['Belady异常', '页面置换'],
    },
    {
      questionId: 'q-os-2',
      correct: false,
      userAnswer: 'CR4',
      correctAnswer: 'CR3',
      explanation: 'CR3 寄存器存储页表基址（PDBR），进程切换时必须更新它，这会导致 TLB flush。CR4 用于控制 CPU 特性（如 PAE）。',
      errorType: '细节遗忘',
      errorTags: ['TLB', 'x86架构'],
    },
    {
      questionId: 'q-os-3',
      correct: true,
      userAnswer: 'ref_bit[pointer] = 0',
      correctAnswer: 'ref_bit[pointer] = 0',
      explanation: '正确！当 ref_bit 为 1 时，给予第二次机会：清除访问位并移动指针。',
      errorType: null,
      errorTags: [],
    },
  ],
};
