import React, { useState, useEffect } from 'react';
import { ArrowRight, Code, Check, X, Loader2 } from 'lucide-react';
import useAppStore from '../../store/useAppStore';

/**
 * TestMode —— 测试模式考试界面
 * 对接真实后端 API（不再使用 mock 数据）
 */
export default function TestMode() {
  const activeFile = useAppStore((s) => s.activeFile);
  const setViewMode = useAppStore((s) => s.setViewMode);
  const openRightDrawer = useAppStore((s) => s.openRightDrawer);
  const setErrorTags = useAppStore((s) => s.setErrorTags);

  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 加载题目
  useEffect(() => {
    if (!activeFile) {
      setQuestions([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setQuestions([]);
    setAnswers({});
    setSubmitted(false);
    setFeedback(null);

    fetch(`/api/questions?file=${encodeURIComponent(activeFile.path)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setQuestions(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [activeFile]);

  const [currentIdx, setCurrentIdx] = useState(0);
  const currentQ = questions[currentIdx];

  const handleAnswer = (value) => {
    if (submitted) return;
    setAnswers((prev) => ({ ...prev, [currentQ.id]: value }));
  };

  const handleSubmit = async () => {
    setSubmitted(true);
    setSubmitting(true);

    try {
      const submitAnswers = questions.map((q) => ({
        question_id: q.id,
        user_answer: answers[q.id] || '',
      }));

      const resp = await fetch('/api/test/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: activeFile.path,
          answers: submitAnswers,
        }),
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        throw new Error(errText || `HTTP ${resp.status}`);
      }

      const data = await resp.json();
      setFeedback(data);

      // 设置错题标签 → 触发热力图
      if (data.errorTags && data.errorTags.length > 0) {
        setErrorTags(data.errorTags);
      }

      // 打开右侧抽屉展示结果
      openRightDrawer();
    } catch (err) {
      setFeedback({
        score: 0,
        summary: `评判失败：${err.message}`,
        details: [],
        errorTags: [],
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackToLearn = () => {
    setViewMode('learn');
  };

  // ---- 加载状态 ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="text-primary-500 animate-spin" />
          <p className="text-surface-500 dark:text-surface-400 text-sm">加载题目中...</p>
        </div>
      </div>
    );
  }

  // ---- 错误状态 ----
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-surface-400 dark:text-surface-500 gap-3">
        <p className="text-lg">加载失败</p>
        <p className="text-sm">{error}</p>
        <button
          onClick={handleBackToLearn}
          className="text-primary-500 hover:text-primary-600 text-sm"
        >
          ← 返回学习模式
        </button>
      </div>
    );
  }

  // ---- 空状态 ----
  if (!activeFile) {
    return (
      <div className="flex items-center justify-center h-full text-surface-400 dark:text-surface-500">
        <p>请先从左侧选择学习材料</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-surface-400 dark:text-surface-500 gap-3">
        <p className="text-lg">该章节暂无测试题</p>
        <button
          onClick={handleBackToLearn}
          className="text-primary-500 hover:text-primary-600 text-sm"
        >
          ← 返回学习模式
        </button>
      </div>
    );
  }

  // ---- 提交中 ----
  if (submitted && submitting) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="text-primary-500 animate-spin" />
          <p className="text-surface-500 dark:text-surface-400 text-sm">AI 正在评判你的答案...</p>
        </div>
      </div>
    );
  }

  // ---- 已提交，显示结果摘要 ----
  if (submitted && feedback) {
    return (
      <div className="max-w-2xl mx-auto py-10 px-6">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary-50 dark:bg-primary-950 mb-4">
            <span className="text-3xl font-bold text-primary-600 dark:text-primary-400">
              {feedback.score}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-surface-900 dark:text-surface-100 mb-2">测试完成</h2>
          <p className="text-surface-500 dark:text-surface-400">{feedback.summary}</p>
        </div>

        <div className="space-y-4 mb-8">
          {feedback.details.map((d, i) => (
            <div
              key={d.questionId}
              className={`test-card border-l-4 ${
                d.correct ? 'border-l-green-500' : 'border-l-red-500'
              }`}
            >
              <div className="flex items-start gap-3">
                {d.correct ? (
                  <Check size={20} className="text-green-500 mt-0.5 flex-shrink-0" />
                ) : (
                  <X size={20} className="text-red-500 mt-0.5 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-surface-800 dark:text-surface-200 mb-1">
                    题目 {i + 1}
                  </p>
                  {!d.correct && d.errorType && (
                    <span className="inline-block text-xs bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400 px-2 py-0.5 rounded-full mb-2">
                      {d.errorType}
                    </span>
                  )}
                  <p className="text-sm text-surface-600 dark:text-surface-400">{d.explanation}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-3 justify-center">
          <button
            onClick={handleBackToLearn}
            className="px-6 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600
                       transition-colors font-medium flex items-center gap-2"
          >
            返回学习（查看错题高亮）
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    );
  }

  // ---- 答题界面 ----
  return (
    <div className="max-w-2xl mx-auto py-10 px-6">
      {/* 进度 */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={handleBackToLearn}
          className="text-sm text-surface-400 dark:text-surface-500 hover:text-surface-600 dark:hover:text-surface-300 transition-colors"
        >
          ← 退出测试
        </button>
        <span className="text-sm text-surface-400 dark:text-surface-500">
          {currentIdx + 1} / {questions.length}
        </span>
      </div>

      {/* 进度条 */}
      <div className="w-full h-1 bg-surface-200 dark:bg-surface-700 rounded-full mb-8">
        <div
          className="h-full bg-primary-500 rounded-full transition-all duration-300"
          style={{
            width: `${((currentIdx + 1) / questions.length) * 100}%`,
          }}
        />
      </div>

      {/* 题目卡片 */}
      {currentQ && (
        <div className="test-card mb-4">
          {/* 题型标签 */}
          <div className="flex items-center gap-2 mb-4">
            {currentQ.type === 'code' && (
              <span className="inline-flex items-center gap-1 text-xs bg-surface-800 dark:bg-surface-600 text-surface-200 dark:text-surface-300 px-2 py-0.5 rounded-full">
                <Code size={12} /> 代码补全
              </span>
            )}
            {currentQ.type === 'single' && (
              <span className="inline-flex items-center gap-1 text-xs bg-primary-50 dark:bg-primary-950 text-primary-700 dark:text-primary-300 px-2 py-0.5 rounded-full">
                单选题
              </span>
            )}
            {currentQ.type === 'text' && (
              <span className="inline-flex items-center gap-1 text-xs bg-accent-50 dark:bg-accent-950 text-accent-700 dark:text-accent-300 px-2 py-0.5 rounded-full">
                简答题
              </span>
            )}
          </div>

          {/* 题干 */}
          <h3 className="text-lg font-semibold text-surface-900 dark:text-surface-100 mb-4">
            {currentQ.question}
          </h3>

          {/* 单选题选项 */}
          {currentQ.type === 'single' && currentQ.options && (
            <div className="space-y-2">
              {currentQ.options.map((opt, i) => (
                <label
                  key={i}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors
                    ${
                      answers[currentQ.id] === opt
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-950'
                        : 'border-surface-200 dark:border-surface-700 hover:border-surface-300 dark:hover:border-surface-600 bg-white dark:bg-surface-800'
                    }`}
                >
                  <div
                    className={`w-4 h-4 rounded-full border-2 flex items-center justify-center
                      ${
                        answers[currentQ.id] === opt
                          ? 'border-primary-500'
                          : 'border-surface-300 dark:border-surface-600'
                      }`}
                  >
                    {answers[currentQ.id] === opt && (
                      <div className="w-2 h-2 rounded-full bg-primary-500" />
                    )}
                  </div>
                  <input
                    type="radio"
                    name={currentQ.id}
                    value={opt}
                    checked={answers[currentQ.id] === opt}
                    onChange={() => handleAnswer(opt)}
                    className="hidden"
                  />
                  <span className="text-sm text-surface-700 dark:text-surface-300">{opt}</span>
                </label>
              ))}
            </div>
          )}

          {/* 简答/代码输入 */}
          {(currentQ.type === 'text' || currentQ.type === 'code') && (
            <textarea
              value={answers[currentQ.id] || ''}
              onChange={(e) => handleAnswer(e.target.value)}
              placeholder={
                currentQ.type === 'code'
                  ? '输入你的代码...'
                  : '输入你的答案...'
              }
              className="w-full p-3 border border-surface-200 dark:border-surface-700 rounded-lg text-sm font-mono
                         bg-white dark:bg-surface-800 text-surface-800 dark:text-surface-200
                         focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
                         placeholder:text-surface-300 dark:placeholder:text-surface-600 min-h-[100px] resize-y"
              rows={4}
            />
          )}
        </div>
      )}

      {/* 导航按钮 */}
      <div className="flex justify-between items-center">
        <button
          onClick={() => setCurrentIdx(Math.max(0, currentIdx - 1))}
          disabled={currentIdx === 0}
          className="px-4 py-2 text-sm text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-200
                     disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          ← 上一题
        </button>

        {currentIdx < questions.length - 1 ? (
          <button
            onClick={() => setCurrentIdx(currentIdx + 1)}
            className="px-5 py-2 bg-surface-100 dark:bg-surface-800 text-surface-700 dark:text-surface-300 rounded-lg
                       hover:bg-surface-200 dark:hover:bg-surface-700 transition-colors text-sm font-medium"
          >
            下一题
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={questions.some((q) => !answers[q.id]?.trim())}
            className="px-6 py-2.5 bg-primary-500 text-white rounded-lg
                       hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors font-medium flex items-center gap-2"
          >
            提交全部答案
            <ArrowRight size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
