import React, { useState, useEffect, useCallback } from 'react';
import { ArrowRight, Code, Check, X, Loader2, Brain, Target, BookOpen, RefreshCw, AlertTriangle, Search } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { generateSubmissionId } from '../../utils/uuid';
import {
  stashSubmission,
  getStashedSubmission,
  clearStashedSubmission,
} from '../../utils/submissionStash';

/**
 * TestMode —— 测试模式考试界面
 * 对接真实后端 API，包含完整学习闭环：
 * 答题 → 评判 → 诊断 → 掌握度更新 → 复习任务生成
 */
export default function TestMode() {
  const activeFile = useAppStore((s) => s.activeFile);
  const setViewMode = useAppStore((s) => s.setViewMode);
  const openRightDrawer = useAppStore((s) => s.openRightDrawer);
  const setErrorTags = useAppStore((s) => s.setErrorTags);
  const setDiagnoses = useAppStore((s) => s.setDiagnoses);
  const setMasteryUpdates = useAppStore((s) => s.setMasteryUpdates);
  const setReviewTasks = useAppStore((s) => s.setReviewTasks);
  const setWeakPoints = useAppStore((s) => s.setWeakPoints);

  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // 练习会话 ID（由 /api/learning/next-session 生成），提交测试时携带，用于学习闭环
  const [practiceSessionId, setPracticeSessionId] = useState(null);
  // 幂等提交键:首次提交生成,失败重试复用,成功后清理
  const [submissionId, setSubmissionId] = useState(null);

  // 加载题目：优先使用自适应练习会话，无知识点数据时回退到按文件加载
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
    setPracticeSessionId(null);

    // 1. 尝试自适应出题（学习闭环主路径），按当前文档限定出题范围
    fetch('/api/learning/next-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'adaptive', count: 5, file_path: activeFile.path }),
    })
      .then((r) => r.ok ? r.json() : null)
      .then(async (data) => {
        if (data && data.session_id && data.questions && data.questions.length > 0) {
          setPracticeSessionId(data.session_id);
          // next-session 返回的题目字段适配为 TestMode 使用的结构
          const adapted = data.questions.map((q) => ({
            id: q.id,
            type: q.type || 'text',
            question: q.content,
            options: q.options,
            difficulty: q.difficulty,
          }));
          setQuestions(adapted);
          setLoading(false);
          return;
        }
        // 2. 回退：按文件加载题目（无 practice_session_id）
        const r2 = await fetch(`/api/questions?file=${encodeURIComponent(activeFile.path)}`);
        if (!r2.ok) throw new Error(`HTTP ${r2.status}`);
        const data2 = await r2.json();
        setQuestions(data2);
        setLoading(false);
      })
      .catch(async (err) => {
        // 请求失败也回退到按文件加载
        try {
          const r2 = await fetch(`/api/questions?file=${encodeURIComponent(activeFile.path)}`);
          if (r2.ok) {
            setQuestions(await r2.json());
            setLoading(false);
            return;
          }
        } catch {}
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

    // 幂等键:首次提交生成,失败重试复用,成功后清理
    let currentSubmissionId = submissionId;
    if (!currentSubmissionId) {
      currentSubmissionId = generateSubmissionId();
      setSubmissionId(currentSubmissionId);
    }

    const submitAnswers = questions.map((q) => ({
      question_id: q.id,
      user_answer: answers[q.id] || '',
    }));

    // 暂存到 sessionStorage,防止刷新丢失导致重复提交
    stashSubmission({
      submissionId: currentSubmissionId,
      answers: submitAnswers,
      practiceSessionId,
    });

    try {
      // 约束：测试接口以 practice_session_id + answers 作为输入
      const payload = {
        answers: submitAnswers,
        submission_id: currentSubmissionId,
      };
      if (practiceSessionId) {
        payload.practice_session_id = practiceSessionId;
      } else if (activeFile?.path) {
        payload.file_path = activeFile.path;
      }

      const resp = await fetch('/api/test/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      // 关键:先解析 JSON,再判断状态码。503 响应体含即时评判,不能直接 throw。
      const data = await resp.json().catch(() => null);

      if (!resp.ok) {
        const isBusinessSubmissionState =
          data?.commitStatus === 'not_committed' ||
          data?.commitStatus === 'outcome_unknown';

        if (!isBusinessSubmissionState) {
          // 真正的异常(4xx/5xx 且非提交状态),抛错走错误分支
          throw new Error(data?.detail || `HTTP ${resp.status}`);
        }
        // not_committed / outcome_unknown:继续走 setFeedback 展示即时评判
      }

      setFeedback(data);

      // 仅 committed 时才更新全局学习状态(强一致性:学习档案必须已落库)
      if (data.commitStatus === 'committed') {
        setErrorTags(data.evaluation?.errorTags || []);
        if (data.learningRecord) {
          setDiagnoses(data.learningRecord.diagnoses || []);
          setMasteryUpdates(data.learningRecord.masteryUpdates || {});
          setReviewTasks(data.learningRecord.reviewTasks || []);
          setWeakPoints(data.learningRecord.weakPoints || []);
        }
        openRightDrawer();
        // 提交成功,清理 sessionStorage 暂存
        clearStashedSubmission();
      }
      // persistence_failed / outcome_unknown / tracking_disabled:
      // 不写 store、不更新热力图、不打开抽屉
    } catch (err) {
      setFeedback({
        submissionId: currentSubmissionId,
        commitStatus: 'not_committed',
        retryable: true,
        message: `评判失败:${err.message}`,
        evaluation: {
          score: 0,
          summary: `评判失败:${err.message}`,
          details: [],
          errorTags: [],
        },
        learningRecord: null,
      });
    } finally {
      setSubmitting(false);
    }
  };

  // 查询提交状态(outcome_unknown 恢复 + 刷新后对账)
  const handleQuerySubmissionStatus = useCallback(async (sid) => {
    try {
      const resp = await fetch(`/api/test/submissions/${sid}`);
      const status = await resp.json();
      if (status.found) {
        // 已提交成功,用快照恢复
        setFeedback({
          submissionId: status.submissionId,
          commitStatus: 'committed',
          retryable: false,
          message: '已确认学习记录保存成功',
          evaluation: status.evaluation,
          learningRecord: status.learningRecord,
        });
        setErrorTags(status.evaluation?.errorTags || []);
        if (status.learningRecord) {
          setDiagnoses(status.learningRecord.diagnoses || []);
          setMasteryUpdates(status.learningRecord.masteryUpdates || {});
          setReviewTasks(status.learningRecord.reviewTasks || []);
          setWeakPoints(status.learningRecord.weakPoints || []);
        }
        openRightDrawer();
        clearStashedSubmission();
      } else {
        // 确认未提交,可安全重试
        setFeedback((prev) => ({
          ...prev,
          commitStatus: 'not_committed',
          message: '已确认上次提交未保存,可重新提交。',
        }));
      }
    } catch (e) {
      console.error('[TestMode] query submission status failed:', e);
    }
  }, [setDiagnoses, setMasteryUpdates, setReviewTasks, setWeakPoints, setErrorTags, openRightDrawer]);

  // 挂载时检查 sessionStorage 是否有未确认的提交(刷新恢复)
  useEffect(() => {
    if (!activeFile) return;
    const stashed = getStashedSubmission();
    if (stashed && stashed.submissionId) {
      setSubmissionId(stashed.submissionId);
      // 自动查询提交状态
      handleQuerySubmissionStatus(stashed.submissionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFile]);

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
    // 嵌套结构:evaluation 始终存在(评判层);learningRecord 仅 committed 时非空(学习档案层)
    const evaluation = feedback?.evaluation;
    const learningRecord =
      feedback?.commitStatus === 'committed' ? feedback.learningRecord : null;
    const commitStatus = feedback?.commitStatus;

    const hasDiagnoses = learningRecord?.diagnoses?.length > 0;
    const hasReviewTasks = learningRecord?.reviewTasks?.length > 0;
    const hasMasteryUpdates =
      learningRecord?.masteryUpdates &&
      Object.keys(learningRecord.masteryUpdates).length > 0;
    const hasWeakPoints = learningRecord?.weakPoints?.length > 0;

    return (
      <div className="max-w-2xl mx-auto py-10 px-6">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary-50 dark:bg-primary-950 mb-4">
            <span className="text-3xl font-bold text-primary-600 dark:text-primary-400">
              {evaluation?.score ?? 0}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-surface-900 dark:text-surface-100 mb-2">测试完成</h2>
          <p className="text-surface-500 dark:text-surface-400">{evaluation?.summary}</p>

          {/* 四态警告框:committed 不显示;其他三态分别渲染对应恢复路径 */}
          {commitStatus === 'not_committed' && (
            <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-950 border border-amber-300 dark:border-amber-800 rounded-lg text-left" role="alert">
              <div className="flex items-start gap-2">
                <AlertTriangle size={18} className="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-amber-800 dark:text-amber-200 text-sm font-medium">学习记录未保存</p>
                  <p className="text-amber-700 dark:text-amber-300 text-xs mt-1">
                    {feedback.message || '本次答案已完成评判，但学习记录未保存。请重新提交后再查看学习计划。'}
                  </p>
                  <button
                    onClick={handleSubmit}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs rounded-md font-medium transition-colors"
                  >
                    <RefreshCw size={14} />
                    重新提交并保存
                  </button>
                </div>
              </div>
            </div>
          )}

          {commitStatus === 'outcome_unknown' && (
            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-950 border border-blue-300 dark:border-blue-800 rounded-lg text-left" role="alert">
              <div className="flex items-start gap-2">
                <AlertTriangle size={18} className="text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-blue-800 dark:text-blue-200 text-sm font-medium">提交结果暂时无法确认</p>
                  <p className="text-blue-700 dark:text-blue-300 text-xs mt-1">
                    {feedback.message || '提交结果暂时无法确认，请点击"查询提交状态"确认学习记录是否已保存。'}
                  </p>
                  <button
                    onClick={() => handleQuerySubmissionStatus(feedback.submissionId)}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-md font-medium transition-colors"
                  >
                    <Search size={14} />
                    查询提交状态
                  </button>
                </div>
              </div>
            </div>
          )}

          {commitStatus === 'tracking_disabled' && (
            <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg text-left">
              <p className="text-gray-700 dark:text-gray-300 text-sm font-medium">演示练习</p>
              <p className="text-gray-600 dark:text-gray-400 text-xs mt-1">
                {feedback.message || '演示练习，不保存学习档案。'}
              </p>
            </div>
          )}
        </div>

        {/* 答题详情(任何状态都展示,用户不白答) */}
        {evaluation?.details?.length > 0 && (
          <div className="space-y-4 mb-8">
            <h3 className="text-lg font-semibold text-surface-800 dark:text-surface-200 flex items-center gap-2">
              <Check size={18} className="text-primary-500" />
              答题详情
            </h3>
            {evaluation.details.map((d, i) => (
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
        )}

        {/* 能力诊断(仅 committed 且 learningRecord 非空时渲染) */}
        {hasDiagnoses && (
          <div className="space-y-4 mb-8">
            <h3 className="text-lg font-semibold text-surface-800 dark:text-surface-200 flex items-center gap-2">
              <Brain size={18} className="text-purple-500" />
              能力诊断
            </h3>
            {learningRecord.diagnoses.map((diag, i) => (
              diag.error_category && (
                <div key={i} className="test-card border-l-4 border-l-purple-500">
                  <div className="mb-2">
                    <span className="inline-block text-xs bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400 px-2 py-0.5 rounded-full font-medium">
                      {diag.error_category}
                    </span>
                  </div>
                  <p className="text-sm text-surface-700 dark:text-surface-300 mb-2">
                    {diag.error_conclusion}
                  </p>
                  {diag.review_suggestions && diag.review_suggestions.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-surface-200 dark:border-surface-700">
                      <p className="text-xs text-surface-500 dark:text-surface-400 mb-2">复习建议：</p>
                      <ul className="space-y-1.5">
                        {diag.review_suggestions.slice(0, 3).map((s, j) => (
                          <li key={j} className="flex items-start gap-2 text-sm text-surface-600 dark:text-surface-400">
                            <BookOpen size={14} className="text-primary-500 mt-0.5 flex-shrink-0" />
                            <span>{s.title}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )
            ))}
          </div>
        )}

        {/* 掌握度变化(仅 committed) */}
        {hasMasteryUpdates && (
          <div className="space-y-4 mb-8">
            <h3 className="text-lg font-semibold text-surface-800 dark:text-surface-200 flex items-center gap-2">
              <Target size={18} className="text-blue-500" />
              掌握度变化
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {Object.entries(learningRecord.masteryUpdates).slice(0, 4).map(([kpId, update]) => (
                <div key={kpId} className="test-card">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-surface-700 dark:text-surface-300">
                      {update.kp_name || kpId.slice(0, 8)}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      update.status === 'mastered' ? 'bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400' :
                      update.status === 'unstable' ? 'bg-yellow-50 text-yellow-600 dark:bg-yellow-950 dark:text-yellow-400' :
                      update.status === 'learning' ? 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400' :
                      update.status === 'forgotten' ? 'bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-400' :
                      'bg-gray-50 text-gray-600 dark:bg-gray-950 dark:text-gray-400'
                    }`}>
                      {update.status === 'mastered' ? '已掌握' :
                       update.status === 'unstable' ? '掌握不稳' :
                       update.status === 'learning' ? '学习中' :
                       update.status === 'forgotten' ? '已遗忘' : '未学习'}
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-200 dark:bg-surface-700 rounded-full mb-1">
                    <div
                      className="h-full bg-primary-500 rounded-full transition-all duration-500"
                      style={{ width: `${update.mastery_score}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-surface-500 dark:text-surface-400">
                    <span>{update.mastery_score} 分</span>
                    {update.delta !== undefined && (
                      <span className={update.delta >= 0 ? 'text-green-500' : 'text-red-500'}>
                        {update.delta >= 0 ? '+' : ''}{update.delta}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 复习任务(仅 committed) */}
        {hasReviewTasks && (
          <div className="space-y-4 mb-8">
            <h3 className="text-lg font-semibold text-surface-800 dark:text-surface-200 flex items-center gap-2">
              <RefreshCw size={18} className="text-amber-500" />
              复习任务
            </h3>
            <div className="space-y-2">
              {learningRecord.reviewTasks.slice(0, 5).map((task, i) => (
                <div key={i} className="test-card flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    task.task_type === 'review_material' ? 'bg-blue-50 text-blue-500 dark:bg-blue-950 dark:text-blue-400' :
                    task.task_type === 'practice_question' ? 'bg-green-50 text-green-500 dark:bg-green-950 dark:text-green-400' :
                    task.task_type === 'concept_comparison' ? 'bg-purple-50 text-purple-500 dark:bg-purple-950 dark:text-purple-400' :
                    'bg-amber-50 text-amber-500 dark:bg-amber-950 dark:text-amber-400'
                  }`}>
                    <BookOpen size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-surface-700 dark:text-surface-300">
                      {task.title}
                    </p>
                    {task.description && (
                      <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
                        {task.description}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 薄弱知识点(仅 committed) */}
        {hasWeakPoints && (
          <div className="space-y-4 mb-8">
            <h3 className="text-lg font-semibold text-surface-800 dark:text-surface-200 flex items-center gap-2">
              <Target size={18} className="text-red-500" />
              当前薄弱知识点
            </h3>
            <div className="space-y-2">
              {learningRecord.weakPoints.slice(0, 5).map((wp, i) => (
                <div key={i} className="test-card flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-surface-700 dark:text-surface-300">
                      {wp.kp_name || wp.kp_id}
                    </p>
                    <p className="text-xs text-surface-500 dark:text-surface-400">
                      错误 {wp.wrong_count || 0} 次
                    </p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    wp.status === 'unstable' ? 'bg-yellow-50 text-yellow-600 dark:bg-yellow-950 dark:text-yellow-400' :
                    wp.status === 'learning' ? 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400' :
                    wp.status === 'forgotten' ? 'bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-400' :
                    'bg-gray-50 text-gray-600 dark:bg-gray-950 dark:text-gray-400'
                  }`}>
                    {wp.mastery_score} 分
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 底部按钮区:按 commitStatus 调整 */}
        <div className="flex gap-3 justify-center">
          {commitStatus === 'committed' && (
            <button
              onClick={handleBackToLearn}
              className="px-6 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600
                         transition-colors font-medium flex items-center gap-2"
            >
              返回学习（查看错题高亮）
              <ArrowRight size={16} />
            </button>
          )}
          {commitStatus === 'tracking_disabled' && (
            <button
              onClick={handleBackToLearn}
              className="px-6 py-2.5 bg-surface-500 text-white rounded-lg hover:bg-surface-600
                         transition-colors font-medium flex items-center gap-2"
            >
              返回学习
              <ArrowRight size={16} />
            </button>
          )}
          {/* not_committed / outcome_unknown 的恢复按钮已在上方警告框内,这里不重复 */}
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
