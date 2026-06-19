# React Fiber 架构深度解析

## 为什么需要 Fiber？

React 16 之前使用的 Stack Reconciler 是同步递归的。一旦开始渲染，就必须一气呵成地完成，无法中断。对于大型应用，这意味着主线程可能被长时间阻塞。

### 核心问题

- **同步不可中断**：递归过程无法被打断
- **帧率下降**：超过 16ms 的渲染会导致掉帧
- **用户交互延迟**：输入事件被排队等待

## Fiber 节点结构

每个 Fiber 节点就是一个 JavaScript 对象，代表一个"工作单元"：

```typescript
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
```

## 双缓冲机制

React 维护两棵 Fiber 树：
- **Current Tree**：当前屏幕上显示的树
- **Work-in-Progress Tree**：正在构建的新树

通过 `alternate` 指针互相引用，完成更新后两棵树角色互换，实现无缝切换。

## 调度优先级

React 使用 Lane 模型管理更新优先级：

```typescript
// 优先级从高到低
const SyncLane = 0b0001;           // 同步渲染
const InputContinuousLane = 0b0010; // 连续输入
const DefaultLane = 0b0100;        // 默认
const IdleLane = 0b1000;           // 空闲时处理
```

## 时间切片 (Time Slicing)

Fiber 通过协作式调度实现了时间切片：
1. 每个工作单元执行后，检查剩余时间
2. 如果时间不够（< 5ms），主动让出主线程
3. 浏览器处理完高优先级事件后，恢复工作

```javascript
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
```

> **重要**：Fiber 架构中的"短期记忆"体现在 `memoizedState` 和 `memoizedProps` 中。React 会保留上一次渲染的结果，以便在重新渲染时进行对比，减少不必要的 DOM 操作。
