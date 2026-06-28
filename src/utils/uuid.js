/**
 * 生成提交幂等键(UUID v4)。
 * 优先使用 crypto.randomUUID(需 secure context);否则用 Math.random fallback。
 * Vite dev server 是 HTTP(非 secure context),crypto.randomUUID 可能不可用。
 */
export function generateSubmissionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID();
    } catch {}
  }
  // Fallback for non-secure context (HTTP dev server)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
