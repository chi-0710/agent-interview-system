import React, { useState, useEffect } from 'react';
import {
  Target,
  RefreshCw,
  BookOpen,
  Brain,
  TrendingUp,
  TrendingDown,
  Check,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import useAppStore from '../../store/useAppStore';

/**
 * 状态标签映射
 */
const STATUS_CONFIG = {
  unknown: { label: '未学习', color: 'gray', bg: 'bg-gray-50 text-gray-600 dark:bg-gray-950 dark:text-gray-400' },
  learning: { label: '学习中', color: 'blue', bg: 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400' },
  unstable: { label: '掌握不稳', color: 'yellow', bg: 'bg-yellow-50 text-yellow-600 dark:bg-yellow-950 dark:text-yellow-400' },
  mastered: { label: '已掌握', color: 'green', bg: 'bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400' },
  forgotten: { label: '已遗忘', color: 'orange', bg: 'bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-400' },
};

/**
 * 任务类型图标映射
 */
const TASK_TYPE_ICONS = {
  review_material: { icon: BookOpen, color: 'text-blue-500 bg-blue-50 dark:bg-blue-950' },
  practice_question: { icon: Target, color: 'text-green-500 bg-green-50 dark:bg-green-950' },
  concept_comparison: { icon: Brain, color: 'text-purple-500 bg-purple-50 dark:bg-purple-950' },
  follow_up_test: { icon: RefreshCw, color: 'text-amber-500 bg-amber-50 dark:bg-amber-950' },
};

/**
 * MasteryBar —— 掌握度进度条
 */
function MasteryBar({ score, status }) {
  const statusConfig = STATUS_CONFIG[status] || STATUS_CONFIG.unknown;
  const barColor = status === 'mastered' ? 'bg-green-500' :
                   status === 'unstable' ? 'bg-yellow-500' :
                   status === 'learning' ? 'bg-blue-500' :
                   status === 'forgotten' ? 'bg-orange-500' :
                   'bg-gray-400';

  return (
    <div className="w-full">
      <div className="w-full h-2 bg-surface-200 dark:bg-surface-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-500`}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </div>
    </div>
  );
}

/**
 * 掌握度列表
 */
function MasteryList() {
  const userMasteryList = useAppStore((s) => s.userMasteryList);
  const loadUserMastery = useAppStore((s) => s.loadUserMastery);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    loadUserMastery().finally(() => setLoading(false));
  }, [loadUserMastery]);

  const filtered = filter === 'all'
    ? userMasteryList
    : userMasteryList.filter((m) => m.status === filter);

  const stats = {
    total: userMasteryList.length,
    mastered: userMasteryList.filter((m) => m.status === 'mastered').length,
    unstable: userMasteryList.filter((m) => m.status === 'unstable').length,
    learning: userMasteryList.filter((m) => m.status === 'learning').length,
  };

  return (
    <div className="space-y-4">
      {/* 统计概览 */}
      <div className="grid grid-cols-4 gap-2">
        <div className="text-center p-2 bg-surface-50 dark:bg-surface-800 rounded-lg">
          <p className="text-lg font-bold text-surface-700 dark:text-surface-300">{stats.total}</p>
          <p className="text-xs text-surface-500 dark:text-surface-400">总知识点</p>
        </div>
        <div className="text-center p-2 bg-green-50 dark:bg-green-950/30 rounded-lg">
          <p className="text-lg font-bold text-green-600 dark:text-green-400">{stats.mastered}</p>
          <p className="text-xs text-green-600 dark:text-green-400">已掌握</p>
        </div>
        <div className="text-center p-2 bg-yellow-50 dark:bg-yellow-950/30 rounded-lg">
          <p className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{stats.unstable}</p>
          <p className="text-xs text-yellow-600 dark:text-yellow-400">不稳</p>
        </div>
        <div className="text-center p-2 bg-blue-50 dark:bg-blue-950/30 rounded-lg">
          <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{stats.learning}</p>
          <p className="text-xs text-blue-600 dark:text-blue-400">学习中</p>
        </div>
      </div>

      {/* 筛选标签 */}
      <div className="flex gap-1 flex-wrap">
        {[
          { value: 'all', label: '全部' },
          { value: 'unstable', label: '不稳' },
          { value: 'learning', label: '学习中' },
          { value: 'mastered', label: '已掌握' },
          { value: 'forgotten', label: '已遗忘' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
              filter === f.value
                ? 'bg-primary-500 text-white'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="text-center py-8 text-surface-400 dark:text-surface-500 text-sm">
          加载中...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-8 text-surface-400 dark:text-surface-500 text-sm">
          暂无数据
        </div>
      ) : (
        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
          {filtered.map((m) => {
            const statusConfig = STATUS_CONFIG[m.status] || STATUS_CONFIG.unknown;
            return (
              <div
                key={m.kp_id}
                className="p-3 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-lg"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-surface-700 dark:text-surface-300 truncate pr-2">
                    {m.kp_name || m.kp_id?.slice(0, 8)}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${statusConfig.bg}`}>
                    {statusConfig.label}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <MasteryBar score={m.mastery_score} status={m.status} />
                  <span className="text-xs font-medium text-surface-500 dark:text-surface-400 flex-shrink-0 w-10 text-right">
                    {Math.round(m.mastery_score)}
                  </span>
                </div>
                {m.last_practiced_at && (
                  <p className="text-xs text-surface-400 dark:text-surface-500 flex items-center gap-1 mt-1">
                    <Clock size={10} />
                    上次练习: {new Date(m.last_practiced_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * 复习任务列表
 */
function ReviewTaskList() {
  const reviewTasks = useAppStore((s) => s.reviewTasks);
  const loadReviewTasks = useAppStore((s) => s.loadReviewTasks);
  const completeReviewTask = useAppStore((s) => s.completeReviewTask);
  const [filter, setFilter] = useState('pending');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    loadReviewTasks(filter).finally(() => setLoading(false));
  }, [loadReviewTasks, filter]);

  const filtered = filter === 'all'
    ? reviewTasks
    : reviewTasks.filter((t) => t.status === filter);

  const handleComplete = async (taskId) => {
    await completeReviewTask(taskId);
  };

  return (
    <div className="space-y-4">
      {/* 筛选标签 */}
      <div className="flex gap-1">
        {[
          { value: 'pending', label: '待完成' },
          { value: 'completed', label: '已完成' },
          { value: 'all', label: '全部' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
              filter === f.value
                ? 'bg-primary-500 text-white'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 任务列表 */}
      {loading ? (
        <div className="text-center py-8 text-surface-400 dark:text-surface-500 text-sm">
          加载中...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-8 text-surface-400 dark:text-surface-500 text-sm">
          {filter === 'pending' ? '暂无待完成任务 🎉' : '暂无任务'}
        </div>
      ) : (
        <div className="space-y-2 max-h-[350px] overflow-y-auto pr-1">
          {filtered.map((task) => {
            const typeConfig = TASK_TYPE_ICONS[task.task_type] || TASK_TYPE_ICONS.review_material;
            const IconComponent = typeConfig.icon;
            const isCompleted = task.status === 'completed';

            return (
              <div
                key={task.id}
                className={`p-3 rounded-lg border transition-all ${
                  isCompleted
                    ? 'bg-surface-50 dark:bg-surface-800/50 border-surface-200 dark:border-surface-700 opacity-60'
                    : 'bg-white dark:bg-surface-800 border-surface-200 dark:border-surface-700 hover:border-primary-300 dark:hover:border-primary-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${typeConfig.color}`}>
                    <IconComponent size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${
                      isCompleted
                        ? 'text-surface-400 dark:text-surface-500 line-through'
                        : 'text-surface-700 dark:text-surface-300'
                    }`}>
                      {task.title}
                    </p>
                    {task.description && (
                      <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
                        {task.description}
                      </p>
                    )}
                    {task.kp_name && (
                      <p className="text-xs text-primary-500 dark:text-primary-400 mt-1">
                        📍 {task.kp_name}
                      </p>
                    )}
                    {task.due_at && (
                      <p className="text-xs text-surface-400 dark:text-surface-500 mt-1 flex items-center gap-1">
                        <AlertTriangle size={10} />
                        截止: {new Date(task.due_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  {!isCompleted && (
                    <button
                      onClick={() => handleComplete(task.id)}
                      className="flex-shrink-0 p-1.5 rounded-lg text-surface-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-950/30 transition-colors"
                      title="标记完成"
                    >
                      <Check size={16} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * 薄弱知识点
 */
function WeakPointsPanel() {
  const weakPoints = useAppStore((s) => s.weakPoints);
  const loadWeakPoints = useAppStore((s) => s.loadWeakPoints);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    loadWeakPoints(5).finally(() => setLoading(false));
  }, [loadWeakPoints]);

  if (loading) {
    return <div className="text-center py-4 text-surface-400 dark:text-surface-500 text-sm">加载中...</div>;
  }

  if (weakPoints.length === 0) {
    return (
      <div className="text-center py-4 text-surface-400 dark:text-surface-500 text-sm">
        暂无薄弱知识点 🎉
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {weakPoints.slice(0, 5).map((wp, i) => {
        const statusConfig = STATUS_CONFIG[wp.status] || STATUS_CONFIG.unknown;
        return (
          <div
            key={wp.kp_id}
            className="flex items-center justify-between p-2.5 bg-surface-50 dark:bg-surface-800 rounded-lg"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-bold text-surface-400 dark:text-surface-500 w-5">
                {i + 1}
              </span>
              <span className="text-sm text-surface-700 dark:text-surface-300 truncate">
                {wp.kp_name || wp.kp_id?.slice(0, 8)}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={`text-xs px-1.5 py-0.5 rounded ${statusConfig.bg}`}>
                {Math.round(wp.mastery_score)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * LearningStatusPanel —— 学习状态面板
 *
 * 展示：掌握度概览、复习任务、薄弱知识点
 */
export default function LearningStatusPanel() {
  const [activeTab, setActiveTab] = useState('mastery');

  const tabs = [
    { id: 'mastery', label: '掌握度', icon: Target },
    { id: 'tasks', label: '复习任务', icon: RefreshCw },
    { id: 'weak', label: '薄弱点', icon: AlertTriangle },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-surface-200 dark:border-surface-700">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-500 to-purple-500 flex items-center justify-center">
            <Brain size={14} className="text-white" />
          </div>
          <span className="text-sm font-semibold text-surface-800 dark:text-surface-200">学习状态</span>
        </div>

        {/* Tabs */}
        <div className="flex bg-surface-100 dark:bg-surface-800 rounded-lg p-0.5">
          {tabs.map((tab) => {
            const IconComponent = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-white dark:bg-surface-700 text-surface-800 dark:text-surface-200 shadow-sm'
                    : 'text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-300'
                }`}
              >
                <IconComponent size={12} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {activeTab === 'mastery' && <MasteryList />}
        {activeTab === 'tasks' && <ReviewTaskList />}
        {activeTab === 'weak' && <WeakPointsPanel />}
      </div>
    </div>
  );
}
