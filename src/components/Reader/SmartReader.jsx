import React, { useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import { Copy, Check } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { matchErrorTags } from '../../utils/metadata';
import { mockMarkdownContent } from '../../data/mockData';

/**
 * CopyButton - 代码块一键复制
 */
function CopyButton({ code }) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-surface-700/50 text-surface-300
                 hover:bg-surface-700 hover:text-white transition-all opacity-0
                 group-hover/code:opacity-100 z-10"
      title="复制代码"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

/**
 * 自定义渲染组件 —— 支持错题高亮 + 深色模式
 */
function createCustomRenderers(errorTags, currentHeaders) {
  return {
    // 代码块自定义
    pre({ children, node, ...props }) {
      const codeEl = children;
      const codeText =
        codeEl?.props?.children?.[0] ||
        (typeof codeEl?.props?.children === 'string'
          ? codeEl.props.children
          : '');

      const className = codeEl?.props?.className || '';
      const lang = className.replace('language-', '') || 'code';

      return (
        <div className="relative group/code">
          <div className="flex items-center justify-between px-4 py-1.5 bg-surface-800 dark:bg-surface-950 rounded-t-lg border-b border-surface-700">
            <span className="text-xs text-surface-400 font-mono">{lang}</span>
          </div>
          <pre className="!mt-0 !rounded-t-none bg-[#0d1117] dark:bg-[#0d1117]" {...props}>
            {children}
          </pre>
          <CopyButton code={codeText} />
        </div>
      );
    },

    // 代码内联自定义
    code({ children, className, ...props }) {
      if (className) {
        return (
          <code className={className} {...props}>
            {children}
          </code>
        );
      }
      return (
        <code
          className="bg-surface-100 dark:bg-surface-800 text-accent-700 dark:text-accent-300
                     px-1.5 py-0.5 rounded text-sm font-mono"
          {...props}
        >
          {children}
        </code>
      );
    },

    // 段落 —— 错题热力图关键注入点
    p({ children, node, ...props }) {
      const blockText =
        typeof children === 'string'
          ? children
          : Array.isArray(children)
            ? children
                .map((c) => (typeof c === 'string' ? c : c?.props?.children || ''))
                .join('')
            : '';

      const { matched, tags } = matchErrorTags(
        { headers: currentHeaders.current },
        errorTags
      );

      if (matched) {
        return (
          <p
            className="error-hotspot"
            title={`错题标签: ${tags.join(', ')}`}
            data-error-tags={tags.join(',')}
            {...props}
          >
            {children}
          </p>
        );
      }

      return <p className="my-3 leading-7 dark:text-surface-300" {...props}>{children}</p>;
    },

    // 标题 —— 跟踪当前 section 层级（同步到 store 供 AI 解释使用）
    h1({ children, ...props }) {
      currentHeaders.current = [String(children).toLowerCase()];
      useAppStore.getState().setCurrentHeaders(currentHeaders.current);
      return <h1 className="dark:text-surface-100 dark:border-surface-700" {...props}>{children}</h1>;
    },
    h2({ children, ...props }) {
      const prev = currentHeaders.current || [];
      currentHeaders.current = [...prev.slice(0, 1), String(children).toLowerCase()];
      useAppStore.getState().setCurrentHeaders(currentHeaders.current);
      return <h2 className="dark:text-surface-100" {...props}>{children}</h2>;
    },
    h3({ children, ...props }) {
      const prev = currentHeaders.current || [];
      currentHeaders.current = [...prev.slice(0, 2), String(children).toLowerCase()];
      useAppStore.getState().setCurrentHeaders(currentHeaders.current);
      return <h3 className="dark:text-surface-200" {...props}>{children}</h3>;
    },

    // 表格优化
    table({ children, ...props }) {
      return (
        <div className="overflow-x-auto my-4">
          <table className="w-full border-collapse text-sm" {...props}>
            {children}
          </table>
        </div>
      );
    },

    // 引用块
    blockquote({ children, ...props }) {
      return (
        <blockquote
          className="border-l-4 border-primary-400 dark:border-primary-600
                     bg-primary-50 dark:bg-primary-950 px-4 py-2 my-4 rounded-r-lg
                     text-surface-700 dark:text-surface-300 italic"
          {...props}
        >
          {children}
        </blockquote>
      );
    },
  };
}

/**
 * EmptyState - 未选择文件时的占位
 */
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-surface-400 dark:text-surface-500">
      <div className="w-24 h-24 mb-4 rounded-full bg-surface-100 dark:bg-surface-800 flex items-center justify-center">
        <svg
          width="40"
          height="40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-surface-300 dark:text-surface-600"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      </div>
      <p className="text-lg font-medium mb-1 dark:text-surface-300">选择一份学习材料</p>
      <p className="text-sm">从左侧知识库中选择一个文档开始学习</p>
    </div>
  );
}

/**
 * SmartReader —— 智能文本渲染器
 */
export default function SmartReader() {
  const activeFile = useAppStore((s) => s.activeFile);
  const errorTags = useAppStore((s) => s.errorTags);
  const containerRef = React.useRef(null);

  // 文档内容：优先从后端拉取，失败时降级到 mock
  const [content, setContent] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!activeFile) {
      setContent(null);
      return;
    }
    // 先用 mock 内容快速渲染，避免白屏
    setContent(mockMarkdownContent[activeFile.path] || null);
    setLoading(true);
    fetch(`/api/documents/content?path=${encodeURIComponent(activeFile.path)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (data.content) setContent(data.content);
      })
      .catch(() => {
        // 请求失败时保留已设置的 mock 内容，静默降级
      })
      .finally(() => setLoading(false));
  }, [activeFile?.path]);

  const currentHeaders = useRef([]);

  const renderers = useMemo(
    () => createCustomRenderers(errorTags, currentHeaders),
    [errorTags]
  );

  if (!activeFile || !content) {
    return <EmptyState />;
  }

  return (
    <div ref={containerRef} className="max-w-3xl mx-auto py-8 px-6">
      {/* 文档标题区 */}
      <div className="mb-8 pb-6 border-b border-surface-200 dark:border-surface-700">
        <h1 className="text-3xl font-bold text-surface-900 dark:text-surface-100 mb-2">
          {activeFile.title}
        </h1>
        <div className="flex items-center gap-3 text-sm text-surface-400 dark:text-surface-500">
          <span>{activeFile.path}</span>
          {errorTags.length > 0 && (
            <span className="flex items-center gap-1 text-red-500 dark:text-red-400">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              {errorTags.length} 个薄弱知识点
            </span>
          )}
        </div>
      </div>

      {/* Markdown 渲染 */}
      <div className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeHighlight, rehypeKatex]}
          components={renderers}
        >
          {content}
        </ReactMarkdown>
      </div>

      {/* 底部间距 */}
      <div className="h-32" />
    </div>
  );
}
