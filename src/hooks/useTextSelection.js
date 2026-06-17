import { useEffect, useRef, useCallback } from 'react';
import useAppStore from '../store/useAppStore';

/**
 * useTextSelection - 监听用户文本选区
 *
 * 功能：
 * 1. 监听 mouseup 事件，获取选中文本和坐标
 * 2. 过滤空选区、过短选区（<2字符）
 * 3. 将选区信息写入 Zustand Store，供 AI 气泡组件消费
 */
export default function useTextSelection(containerRef) {
  const setSelection = useAppStore((s) => s.setSelection);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const viewMode = useAppStore((s) => s.viewMode);
  const timerRef = useRef(null);

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

        setSelection({
          text: text.length > 80 ? text.slice(0, 80) + '...' : text,
          fullText: text,
          x: rect.left + rect.width / 2,
          y: rect.top - 10,
        });
      }, 150);
    },
    [viewMode, setSelection, clearSelection, containerRef]
  );

  const handleMouseDown = useCallback(() => {
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
