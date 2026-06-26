import { useEffect, useRef, useCallback } from 'react';
import useAppStore from '../store/useAppStore';

/**
 * useTextSelection - 监听用户文本选区
 *
 * 功能：
 * 1. 监听 mouseup 事件，获取选中文本和坐标
 * 2. 过滤空选区、过短选区（<2字符）
 * 3. 向上查找最近的块级元素，提取完整段落作为上下文
 * 4. 将选区信息写入 Zustand Store，供 AI 气泡组件消费
 */
export default function useTextSelection(containerRef) {
  const setSelection = useAppStore((s) => s.setSelection);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const viewMode = useAppStore((s) => s.viewMode);
  const timerRef = useRef(null);

  /**
   * 从选区节点向上查找最近的块级元素，提取完整文本
   * @param {Node} node 选区的起始节点
   * @returns {{ blockText: string, blockElement: Element|null }}
   */
  const extractBlockContext = useCallback((node) => {
    let current = node;
    const blockTags = ['P', 'LI', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'PRE', 'TD', 'TH'];
    
    while (current && current !== containerRef?.current) {
      if (current.nodeType === Node.ELEMENT_NODE) {
        const tagName = current.tagName;
        if (blockTags.includes(tagName)) {
          // 提取整个块级元素的文本内容
          const blockText = current.textContent || '';
          return {
            blockText: blockText.trim(),
            blockElement: current,
          };
        }
      }
      current = current.parentNode;
    }
    return { blockText: '', blockElement: null };
  }, [containerRef]);

  const handleMouseUp = useCallback(
    (e) => {
      // 仅在学习模式下启用
      if (viewMode !== 'learn') return;

      // 防抖：避免快速连续触发
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed) {
          clearSelection();
          return;
        }

        const text = sel.toString().trim();
        if (!text || text.length < 2) {
          clearSelection();
          return;
        }

        // 检查选区是否在容器内
        const container = containerRef?.current;
        if (container) {
          const range = sel.getRangeAt(0);
          if (!container.contains(range.commonAncestorContainer)) {
            clearSelection();
            return;
          }
        }

        // 获取选区末尾的屏幕坐标
        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        // 向上提取完整段落作为上下文
        const { blockText } = extractBlockContext(range.startContainer);

        setSelection({
          text: text.length > 80 ? text.slice(0, 80) + '...' : text,
          fullText: text,
          x: rect.left + rect.width / 2,
          y: rect.top - 10,
          blockContext: blockText, // 新增：完整段落上下文
        });
      }, 150);
    },
    [viewMode, setSelection, clearSelection, containerRef, extractBlockContext]
  );

  const handleMouseDown = useCallback((e) => {
    // 点击 AI 气泡（含其外层定位容器）时不清空选区，避免按钮被卸载导致 click 无法派发
    if (e.target.closest('.ai-bubble')) return;
    clearSelection();
  }, [clearSelection]);

  useEffect(() => {
    document.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('mousedown', handleMouseDown);
    return () => {
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('mousedown', handleMouseDown);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [handleMouseUp, handleMouseDown]);
}
