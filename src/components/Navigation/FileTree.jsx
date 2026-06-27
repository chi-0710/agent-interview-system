import React, { useEffect, useState } from 'react';
import {
  PanelLeftClose,
  PanelLeftOpen,
  Folder,
  FileText,
  Flame,
  CheckCircle2,
  Library,
  Plus,
  ChevronDown,
  ChevronRight,
  Trash2,
} from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { mockFileTree } from '../../data/mockData';

function normalizeTree(nodes) {
  return nodes.map((node) => ({
    ...node,
    children: node.children ? normalizeTree(node.children) : undefined,
  }));
}

/**
 * 从 URI 标识中提取相对路径
 * kb://default/cs/os-memory.md → cs/os-memory.md
 * /kb/{kb_id}/filename.md → filename.md (自定义知识库，无子目录)
 * /docs/cs/os-memory.md → cs/os-memory.md (兼容旧格式)
 */
function extractRelPath(uri, knowledgeBaseId) {
  if (!uri) return '';
  // 自定义知识库格式: /kb/{kb_id}/filename.ext
  if (uri.startsWith('/kb/')) {
    const parts = uri.split('/').filter(Boolean);
    // /kb/{kb_id}/filename.ext → 取最后一部分
    return parts.length > 2 ? parts[parts.length - 1] : uri;
  }
  // 默认知识库格式: kb://default/cs/os-memory.md
  if (uri.startsWith('kb://')) {
    return uri.split('://')[1].split('/').slice(1).join('/');
  }
  // 兼容旧格式
  return uri.replace(/^\/docs\//, '');
}

function FileTreeNode({ node, depth = 0 }) {
  const activeFile = useAppStore((s) => s.activeFile);
  const setActiveFile = useAppStore((s) => s.setActiveFile);
  const [expanded, setExpanded] = useState(true);

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
          {expanded ? (
            <ChevronDown size={12} className="mr-1 flex-shrink-0" />
          ) : (
            <ChevronRight size={12} className="mr-1 flex-shrink-0" />
          )}
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

function KnowledgeBaseTreeItem({ kb, isActive, onClick, onDelete }) {
  const [showDelete, setShowDelete] = useState(false);

  return (
    <div
      className="group relative"
      onMouseEnter={() => setShowDelete(true)}
      onMouseLeave={() => setShowDelete(false)}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
        className={`flex items-center w-full px-3 py-2 text-sm transition-colors
          ${isActive
            ? 'bg-primary-50 dark:bg-primary-950 text-primary-700 dark:text-primary-300 border-r-2 border-primary-500'
            : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-800 dark:hover:text-surface-200'
          }`}
      >
        <Library size={14} className="mr-2 flex-shrink-0" />
        <div className="flex-1 text-left min-w-0">
          <div className="truncate font-medium text-xs">{kb.name}</div>
          <div className="text-[10px] text-surface-400 dark:text-surface-500 truncate">
            {kb.document_count || 0} 篇文档
            {kb.status === 'ready' && ' · 就绪'}
            {kb.status === 'processing' && ' · 处理中'}
            {kb.status === 'draft' && ' · 草稿'}
            {kb.status === 'failed' && ' · 失败'}
          </div>
        </div>
        {showDelete && kb.id !== 'default' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(kb.id);
            }}
            className="p-0.5 rounded text-surface-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"
            title="删除知识库"
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

function KnowledgeBaseFileTree({ knowledgeBaseId }) {
  const activeFile = useAppStore((s) => s.activeFile);
  const setActiveFile = useAppStore((s) => s.setActiveFile);
  const loadKnowledgeBaseTree = useAppStore((s) => s.loadKnowledgeBaseTree);
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (knowledgeBaseId === 'default') {
      fetch('/api/documents')
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            setFiles(normalizeTree(data));
          } else {
            setFiles(mockFileTree);
          }
        })
        .catch(() => {
          setFiles(mockFileTree);
        });
    } else {
      setLoading(true);
      loadKnowledgeBaseTree(knowledgeBaseId)
        .then((data) => {
          if (data && data.files && data.files.length > 0) {
            const folders = {};
            data.files.forEach((f) => {
              // 从 URI 提取相对路径: kb://default/cs/os-memory.md → cs/os-memory.md
              const relPath = extractRelPath(f.path || f.title || '', knowledgeBaseId);
              const parts = relPath.split(/[/\\]/).filter(Boolean);
              let current = folders;
              let depth = 0;
              parts.forEach((part, i) => {
                const isFile = i === parts.length - 1 && f.type === 'file';
                if (isFile) {
                  if (!current._files) current._files = [];
                  current._files.push({
                    ...f,
                    title: f.title || part,
                  });
                } else {
                  if (!current[part]) {
                    current[part] = {};
                  }
                  current = current[part];
                }
              });
            });

            const buildTree = (obj, depth = 0) => {
              const result = [];
              const fileItems = obj._files || [];
              const folderKeys = Object.keys(obj).filter((k) => k !== '_files');

              folderKeys.forEach((key) => {
                result.push({
                  id: `${knowledgeBaseId}-${key}`,
                  title: key,
                  type: 'folder',
                  children: buildTree(obj[key], depth + 1),
                });
              });

              fileItems.forEach((f) => {
                result.push({
                  ...f,
                  id: f.id || f.path || f.title,
                });
              });

              return result;
            };

            const tree = buildTree(folders);

            if (tree.length === 0) {
              setFiles(
                data.files.map((f) => ({
                  ...f,
                  id: f.id || f.path || f.title,
                  type: 'file',
                }))
              );
            } else if (tree.length === 1 && tree[0].type === 'file' && data.files.length > 1) {
              setFiles(
                data.files.map((f) => ({
                  ...f,
                  id: f.id || f.path || f.title,
                  type: 'file',
                }))
              );
            } else {
              setFiles(tree);
            }
          } else {
            setFiles([]);
          }
        })
        .catch(() => {
          setFiles([]);
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [knowledgeBaseId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="w-4 h-4 border-2 border-primary-300 border-t-primary-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-surface-400 dark:text-surface-500 text-center">
        暂无文档
      </div>
    );
  }

  return (
    <>
      {files.map((node) => (
        <FileTreeNode key={node.id} node={node} />
      ))}
    </>
  );
}

export default function LeftSidebar() {
  const collapsed = useAppStore((s) => s.leftSidebarCollapsed);
  const toggleLeftSidebar = useAppStore((s) => s.toggleLeftSidebar);
  const knowledgeBases = useAppStore((s) => s.knowledgeBases);
  const activeKnowledgeBaseId = useAppStore((s) => s.activeKnowledgeBaseId);
  const setActiveKnowledgeBase = useAppStore((s) => s.setActiveKnowledgeBase);
  const setShowCreateKBModal = useAppStore((s) => s.setShowCreateKBModal);
  const loadKnowledgeBases = useAppStore((s) => s.loadKnowledgeBases);
  const deleteKnowledgeBase = useAppStore((s) => s.deleteKnowledgeBase);

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  const handleDeleteKB = async (kbId) => {
    if (!window.confirm('确定要删除该知识库吗？所有关联数据将被永久删除。')) return;
    try {
      await deleteKnowledgeBase(kbId);
      await loadKnowledgeBases();
    } catch (e) {
      alert(e.message || '删除失败');
    }
  };

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
      <div className="flex items-center justify-between px-3 py-3 border-b border-surface-100 dark:border-surface-800">
        <span className="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider">
          知识库
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowCreateKBModal(true)}
            className="p-1 rounded-md text-surface-400 dark:text-surface-500
                       hover:text-primary-600 dark:hover:text-primary-400
                       hover:bg-primary-50 dark:hover:bg-primary-950 transition-colors"
            title="添加知识库"
          >
            <Plus size={16} />
          </button>
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
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="py-1 border-b border-surface-100 dark:border-surface-800">
          {(knowledgeBases.length > 0 ? knowledgeBases : [
            { id: 'default', name: '默认知识库', status: 'ready', document_count: 0 },
          ]).map((kb) => (
            <div key={kb.id}>
              <KnowledgeBaseTreeItem
                kb={kb}
                isActive={activeKnowledgeBaseId === kb.id}
                onClick={() => setActiveKnowledgeBase(kb.id)}
                onDelete={handleDeleteKB}
              />
              {activeKnowledgeBaseId === kb.id && (
                <div className="py-1 border-t border-surface-100 dark:border-surface-800">
                  <KnowledgeBaseFileTree knowledgeBaseId={kb.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

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
