/**
 * 提交幂等键暂存(sessionStorage)
 *
 * 防止用户刷新页面丢失 submissionId 导致重复提交。
 * 仅在提交未确认成功时保留;成功后立即清理。
 * 超过 1 小时视为过期自动清理。
 */
const STASH_KEY = 'pending_test_submission';
const TTL_MS = 60 * 60 * 1000; // 1 小时

/**
 * 暂存提交信息到 sessionStorage。
 * @param {{ submissionId: string, answers: Array, practiceSessionId: string|null }} payload
 */
export function stashSubmission({ submissionId, answers, practiceSessionId }) {
  try {
    sessionStorage.setItem(
      STASH_KEY,
      JSON.stringify({
        submissionId,
        answers,
        practiceSessionId,
        createdAt: Date.now(),
      })
    );
  } catch (e) {
    console.error('[submissionStash] stash failed:', e);
  }
}

/**
 * 读取暂存的提交信息。过期则清理并返回 null。
 * @returns {{ submissionId: string, answers: Array, practiceSessionId: string|null, createdAt: number } | null}
 */
export function getStashedSubmission() {
  try {
    const raw = sessionStorage.getItem(STASH_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data.createdAt !== 'number') {
      clearStashedSubmission();
      return null;
    }
    if (Date.now() - data.createdAt > TTL_MS) {
      clearStashedSubmission();
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

/**
 * 清理暂存的提交信息(提交成功后调用)。
 */
export function clearStashedSubmission() {
  try {
    sessionStorage.removeItem(STASH_KEY);
  } catch {}
}
