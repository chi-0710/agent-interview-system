import React, { useState, useRef } from 'react';
import { X, Upload, FileText, Tag as TagIcon, Plus, Loader2 } from 'lucide-react';
import useAppStore from '../../store/useAppStore';

function CreateKnowledgeBaseModal() {
  const setShowCreateKBModal = useAppStore((s) => s.setShowCreateKBModal);
  const createKnowledgeBase = useAppStore((s) => s.createKnowledgeBase);
  const uploadDocuments = useAppStore((s) => s.uploadDocuments);
  const loadKnowledgeBases = useAppStore((s) => s.loadKnowledgeBases);
  const setShowImportProgress = useAppStore((s) => s.setShowImportProgress);
  const setImportJob = useAppStore((s) => s.setImportJob);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState([]);
  const [importMode, setImportMode] = useState('upload');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleAddTag = () => {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) {
      setTags([...tags, t]);
    }
    setTagInput('');
  };

  const handleRemoveTag = (t) => {
    setTags(tags.filter((tag) => tag !== t));
  };

  const handleTagKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTag();
    }
  };

  const ALLOWED_EXTENSIONS = [
    'md', 'markdown', 'txt',
    'pdf',
    'docx', 'doc',
    'pptx', 'ppt',
    'py', 'js', 'jsx', 'ts', 'tsx',
    'java', 'go', 'c', 'h', 'cpp',
    'cs', 'sql', 'json', 'yaml', 'yml',
    'html', 'css', 'sh',
  ];

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    const allowed = files.filter((f) => {
      const ext = f.name.split('.').pop()?.toLowerCase();
      return ALLOWED_EXTENSIONS.includes(ext || '');
    });
    setSelectedFiles(allowed);
    if (allowed.length < files.length) {
      setError('部分文件类型不支持（支持 Markdown/TXT/PDF/Office/代码文件）');
    } else {
      setError('');
    }
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('请输入知识库名称');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('请至少选择一个文件');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      const kb = await createKnowledgeBase({
        name: name.trim(),
        description: description.trim(),
        tags,
      });

      setShowCreateKBModal(false);

      const result = await uploadDocuments(kb.id, selectedFiles);

      setImportJob({
        ...result,
        knowledgeBaseId: kb.id,
        kbName: name.trim(),
      });
      setShowImportProgress(true);

      await loadKnowledgeBases();
    } catch (err) {
      setError(err.message || '创建失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setShowCreateKBModal(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={handleClose} />
      <div className="relative bg-white dark:bg-surface-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-200 dark:border-surface-700">
          <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-200">
            新建知识库
          </h2>
          <button
            onClick={handleClose}
            disabled={isSubmitting}
            className="p-1 rounded-md text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              知识库名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：Java 后端面试准备"
              className="w-full px-3 py-2 text-sm rounded-lg border border-surface-200 dark:border-surface-600
                         bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200
                         placeholder:text-surface-400 dark:placeholder:text-surface-500
                         focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              disabled={isSubmitting}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              说明
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Spring Boot、Redis、MySQL 面试资料"
              className="w-full px-3 py-2 text-sm rounded-lg border border-surface-200 dark:border-surface-600
                         bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200
                         placeholder:text-surface-400 dark:placeholder:text-surface-500
                         focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              disabled={isSubmitting}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-2">
              导入方式
            </label>
            <div className="space-y-2">
              <label className="flex items-center gap-2.5 p-2.5 rounded-lg border border-primary-200 dark:border-primary-800 bg-primary-50/50 dark:bg-primary-950/30 cursor-pointer">
                <input
                  type="radio"
                  name="importMode"
                  value="upload"
                  checked={importMode === 'upload'}
                  onChange={() => setImportMode('upload')}
                  className="text-primary-600"
                />
                <Upload size={16} className="text-primary-600" />
                <span className="text-sm text-surface-700 dark:text-surface-300">上传文件</span>
              </label>
              <label className="flex items-center gap-2.5 p-2.5 rounded-lg border border-surface-200 dark:border-surface-600 opacity-60 cursor-not-allowed">
                <input type="radio" name="importMode" disabled className="opacity-50" />
                <Upload size={16} />
                <span className="text-sm text-surface-500">上传文件夹</span>
                <span className="text-[10px] text-surface-400 ml-auto">即将支持</span>
              </label>
              <label className="flex items-center gap-2.5 p-2.5 rounded-lg border border-surface-200 dark:border-surface-600 opacity-60 cursor-not-allowed">
                <input type="radio" name="importMode" disabled className="opacity-50" />
                <FileText size={16} />
                <span className="text-sm text-surface-500">导入 Markdown 仓库</span>
                <span className="text-[10px] text-surface-400 ml-auto">即将支持</span>
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              文件
            </label>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-sm rounded-lg
                         border-2 border-dashed border-surface-300 dark:border-surface-600
                         text-surface-500 dark:text-surface-400
                         hover:border-primary-400 hover:text-primary-600 dark:hover:border-primary-500
                         transition-colors"
            >
              <Upload size={16} />
              <span>选择文件</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".md,.markdown,.txt,.pdf,.docx,.doc,.pptx,.ppt,.py,.js,.jsx,.ts,.tsx,.java,.go,.c,.h,.cpp,.cs,.sql,.json,.yaml,.yml,.html,.css,.sh"
              onChange={handleFileChange}
              className="hidden"
              disabled={isSubmitting}
            />
            {selectedFiles.length > 0 && (
              <div className="mt-2 space-y-1">
                {selectedFiles.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 text-xs text-surface-600 dark:text-surface-400"
                  >
                    <FileText size={12} />
                    <span className="truncate">{f.name}</span>
                    <span className="text-surface-400 ml-auto">
                      {(f.size / 1024).toFixed(1)} KB
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              分类标签
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={handleTagKeyDown}
                placeholder="输入标签后回车"
                className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-surface-200 dark:border-surface-600
                           bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200
                           placeholder:text-surface-400
                           focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                disabled={isSubmitting}
              />
              <button
                onClick={handleAddTag}
                disabled={!tagInput.trim() || isSubmitting}
                className="p-1.5 rounded-md text-surface-500 hover:text-primary-600 hover:bg-surface-100
                           dark:hover:bg-surface-700 transition-colors disabled:opacity-30"
              >
                <Plus size={16} />
              </button>
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full
                               bg-primary-50 dark:bg-primary-950 text-primary-700 dark:text-primary-300
                               border border-primary-200 dark:border-primary-800"
                  >
                    <TagIcon size={10} />
                    {tag}
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-0.5 hover:text-red-500 transition-colors"
                      disabled={isSubmitting}
                    >
                      <X size={10} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-2">
              高级选项
            </label>
            <div className="space-y-2 text-sm">
              <label className="flex items-center gap-2 text-surface-600 dark:text-surface-400">
                <input type="checkbox" defaultChecked disabled className="opacity-60" />
                自动建立向量检索索引
              </label>
              <label className="flex items-center gap-2 text-surface-400 dark:text-surface-500">
                <input type="checkbox" disabled className="opacity-40" />
                自动提取知识点
                <span className="text-[10px] ml-auto">即将支持</span>
              </label>
              <label className="flex items-center gap-2 text-surface-400 dark:text-surface-500">
                <input type="checkbox" disabled className="opacity-40" />
                自动生成练习题
                <span className="text-[10px] ml-auto">即将支持</span>
              </label>
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-surface-200 dark:border-surface-700">
          <button
            onClick={handleClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm rounded-lg text-surface-600 dark:text-surface-400
                       hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !name.trim() || selectedFiles.length === 0}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                       bg-primary-600 text-white hover:bg-primary-700
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSubmitting && <Loader2 size={14} className="animate-spin" />}
            开始导入
          </button>
        </div>
      </div>
    </div>
  );
}

export default CreateKnowledgeBaseModal;
