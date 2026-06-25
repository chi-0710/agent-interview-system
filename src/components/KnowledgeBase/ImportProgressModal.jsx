import React, { useEffect, useRef } from 'react';
import { X, Loader2, CheckCircle2, FileText, AlertCircle, ArrowRight } from 'lucide-react';
import useAppStore from '../../store/useAppStore';

const STEP_LABELS = {
  uploading: '文件上传中',
  queued: '等待处理',
  parsing: '文本解析中',
  chunking: '文档切片中',
  embedding: '向量索引入库中',
  processing: '处理中',
  done: '导入完成',
};

function ImportProgressModal() {
  const importJob = useAppStore((s) => s.importJob);
  const setImportJob = useAppStore((s) => s.setImportJob);
  const setShowImportProgress = useAppStore((s) => s.setShowImportProgress);
  const getImportJob = useAppStore((s) => s.getImportJob);
  const loadKnowledgeBases = useAppStore((s) => s.loadKnowledgeBases);
  const loadKnowledgeBaseTree = useAppStore((s) => s.loadKnowledgeBaseTree);
  const activeKnowledgeBaseId = useAppStore((s) => s.activeKnowledgeBaseId);
  const setActiveKnowledgeBase = useAppStore((s) => s.setActiveKnowledgeBase);
  const pollingRef = useRef(null);

  useEffect(() => {
    if (!importJob || importJob.status === 'completed' || importJob.status === 'failed') {
      return;
    }

    const poll = async () => {
      try {
        const updated = await getImportJob(importJob.knowledgeBaseId, importJob.job_id);
        if (updated) {
          setImportJob({
            ...updated,
            knowledgeBaseId: importJob.knowledgeBaseId,
            kbName: importJob.kbName,
          });

          if (updated.status === 'completed' || updated.status === 'failed') {
            await loadKnowledgeBases();
            if (importJob.knowledgeBaseId === activeKnowledgeBaseId) {
              await loadKnowledgeBaseTree(importJob.knowledgeBaseId);
            }
            return;
          }
        }
      } catch {
        // ignore polling errors
      }

      pollingRef.current = setTimeout(poll, 1500);
    };

    pollingRef.current = setTimeout(poll, 1000);

    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, [importJob?.job_id, importJob?.status]);

  if (!importJob) return null;

  const handleClose = async () => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
    }

    if (importJob.status === 'completed') {
      await loadKnowledgeBases();
      setActiveKnowledgeBase(importJob.knowledgeBaseId);
    }

    setShowImportProgress(false);
    setImportJob(null);
  };

  const isProcessing =
    importJob.status !== 'completed' && importJob.status !== 'failed';

  const progress = importJob.progress ?? 0;
  const documents = importJob.documents || [];
  const currentStep = importJob.current_step || 'processing';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={handleClose} />
      <div className="relative bg-white dark:bg-surface-800 rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-200 dark:border-surface-700">
          <div>
            <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-200">
              {importJob.kbName || '知识库导入'}
            </h2>
            <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
              {importJob.status === 'completed'
                ? '导入完成'
                : importJob.status === 'failed'
                  ? '导入失败'
                  : STEP_LABELS[currentStep] || '正在处理'}
            </p>
          </div>
          <button
            onClick={handleClose}
            className="p-1 rounded-md text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4 max-h-[50vh] overflow-y-auto">
          {importJob.status === 'completed' && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400">
              <CheckCircle2 size={18} />
              <span className="text-sm font-medium">所有文件导入成功</span>
            </div>
          )}

          {importJob.status === 'failed' && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400">
              <div className="flex items-center gap-2 mb-1">
                <AlertCircle size={18} />
                <span className="text-sm font-medium">导入失败</span>
              </div>
              {importJob.error_message && (
                <p className="text-xs opacity-80">{importJob.error_message}</p>
              )}
            </div>
          )}

          {isProcessing && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-surface-600 dark:text-surface-400">
                  {STEP_LABELS[currentStep] || '处理中'}
                </span>
                <span className="text-surface-500 dark:text-surface-400">{progress}%</span>
              </div>
              <div className="w-full bg-surface-200 dark:bg-surface-700 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-primary-500 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          <div>
            <h3 className="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider mb-2">
              文件状态
            </h3>
            <div className="space-y-1.5">
              {documents.map((doc, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-50 dark:bg-surface-750"
                >
                  <FileText size={14} className="text-surface-400 flex-shrink-0" />
                  <span className="text-sm text-surface-700 dark:text-surface-300 truncate flex-1">
                    {doc.filename}
                  </span>
                  {doc.status === 'ready' && (
                    <CheckCircle2 size={14} className="text-green-500 flex-shrink-0" />
                  )}
                  {doc.status === 'failed' && (
                    <AlertCircle size={14} className="text-red-500 flex-shrink-0" />
                  )}
                  {(doc.status === 'queued' || doc.status === 'processing') && (
                    <Loader2 size={14} className="text-primary-500 animate-spin flex-shrink-0" />
                  )}
                  {doc.status === 'skipped' && (
                    <span className="text-xs text-surface-400 flex-shrink-0">已跳过</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {isProcessing && (
            <div className="space-y-1.5 pt-1">
              {[
                { step: 'uploading', label: '文件上传' },
                { step: 'parsing', label: '文本解析' },
                { step: 'chunking', label: '文档切片' },
                { step: 'embedding', label: '向量索引' },
                { step: 'done', label: '知识点提取' },
              ].map(({ step, label }) => {
                const stepOrder = ['uploading', 'parsing', 'chunking', 'embedding', 'done'];
                const currentIdx = stepOrder.indexOf(currentStep);
                const thisIdx = stepOrder.indexOf(step);
                const isDone = thisIdx < currentIdx;
                const isCurrent = thisIdx === currentIdx;

                return (
                  <div
                    key={step}
                    className="flex items-center gap-2 text-xs"
                  >
                    {isDone ? (
                      <CheckCircle2 size={12} className="text-green-500" />
                    ) : isCurrent ? (
                      <Loader2 size={12} className="text-primary-500 animate-spin" />
                    ) : (
                      <ArrowRight size={12} className="text-surface-300" />
                    )}
                    <span
                      className={
                        isDone
                          ? 'text-green-600 dark:text-green-400'
                          : isCurrent
                            ? 'text-primary-600 dark:text-primary-400 font-medium'
                            : 'text-surface-400'
                      }
                    >
                      {label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-surface-200 dark:border-surface-700">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
          >
            {importJob.status === 'completed' ? '进入知识库' : '关闭'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ImportProgressModal;
