import React from 'react';
import {
  PanelLeftClose,
  PanelLeftOpen,
  Folder,
  FileText,
  Flame,
  CheckCircle2,
} from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { mockFileTree } from '../../data/mockData';

/**
 * 将后端返回的文件树节点格式标准化为前端所需格式
 */
function normalizeTree(nodes) {
  return nodes.map((node) => ({
    ...node,
    children: node.children ? normalizeTree(node.children) : undefined,
  }));
}

/**
 * FileTreeNode - 递归渲染文件树节点
 */
function FileTreeNode({ node, depth = 0 }) {
  const activeFile = useAppStore((s) => s.activeFile);
  const setActiveFile = useAppStore((s) => s.setActiveFile);
  const [expanded, setExpanded] = React.useState(true);

  const isActive = activeFile?.id === node.id;
  const paddingLeft = 12 + depth * 16;

  if (node.type === 'folder') {
    return (
      <div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center w-full px-2 py-1 text-xs text-surface-500
                     dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-300
                     transition-colors"
          style={{ paddingLeft }}
        >
          <Folder size={14} className="mr-1.5 flex-shrink-0" />
          <span className="truncate font-medium">{node.title}</span>
        </button>
        {expanded &&
          node.children?.map((child) => (
            <FileTreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
      </div>
    );
  }

  // file
  const statusIcon =
    node.status === 'hot' ? (
      <Flame size={12} className="text-red-500 ml-auto" />
    ) : node.status === 'passed' ? (
      <CheckCircle2 size={12} className="text-green-500 ml-auto" />
    ) : null;

  return (
    <button
      onClick={() => setActiveFile(node)}
      className={`flex items-center w-full px-2 py-1.5 text-sm transition-colors group
        ${isActive
          ? 'bg-primary-50 dark:bg-primary-950 text-primary-700 dark:text-primary-300 border-r-2 border-primary-500'
          : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-800 dark:hover:text-surface-200'
        }`}
      style={{ paddingLeft }}
    >
      <FileText size={14} className="mr-1.5 flex-shrink-0" />
      <span className="truncate">{node.title}</span>
      <span className="flex-shrink-0 ml-1">{statusIcon}</span>
    </button>
  );
}

/**
 * LeftSidebar - 左侧知识库导航栏
 *
 * 特性：
 * - IDE 风格文件树
 * - 文件状态指示器（🔥高频错题 / ✅已通过）
 * - 可折叠，给阅读模式提供纯净视野
 */
export default function LeftSidebar() {
  const collapsed = useAppStore((s) => s.leftSidebarCollapsed);
  const toggleLeftSidebar = useAppStore((s) => s.toggleLeftSidebar);
  const [fileTree, setFileTree] = React.useState(mockFileTree);

  React.useEffect(() => {
    fetch('/api/documents')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setFileTree(normalizeTree(data));
        }
      })
      .catch(() => {
        // 请求失败时保留 mock 数据，静默降级
      });
  }, []);

  if (collapsed) {
    return (
      <div className="flex flex-col items-center py-3 w-10 border-r border-surface-200
                      dark:border-surface-700 bg-white dark:bg-surface-900 transition-colors">
        <button
          onClick={toggleLeftSidebar}
          className="p-1.5 rounded-md text-surface-400 dark:text-surface-500
                     hover:text-surface-700 dark:hover:text-surface-200
                     hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          title="展开导航"
        >
          <PanelLeftOpen size={18} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-56 border-r border-surface-200 dark:border-surface-700
                    bg-white dark:bg-surface-900 shrink-0 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-surface-100 dark:border-surface-800">
        <span className="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">
          知识库
        </span>
        <button
          onClick={toggleLeftSidebar}
          className="p-1 rounded-md text-surface-400 dark:text-surface-500
                     hover:text-surface-700 dark:hover:text-surface-200
                     hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          title="折叠导航"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* File Tree */}
      <div className="flex-1 overflow-y-auto py-2">
        {fileTree.map((node) => (
          <FileTreeNode key={node.id} node={node} />
        ))}
      </div>

      {/* Footer - Legend */}
      <div className="border-t border-surface-100 dark:border-surface-800 px-3 py-2 space-y-1">
        <div className="flex items-center gap-1.5 text-[10px] text-surface-400 dark:text-surface-500">
          <Flame size={10} className="text-red-500" />
          <span>高频错题</span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-surface-400 dark:text-surface-500">
          <CheckCircle2 size={10} className="text-green-500" />
          <span>已通过测试</span>
        </div>
      </div>
    </div>
  );
}
