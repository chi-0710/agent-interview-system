/**
 * SSE 流式请求工具
 * @param {string} url - API 地址
 * @param {object} body - 请求体
 * @param {(text: string) => void} onChunk - 收到 chunk 回调
 * @param {(error?: string) => void} onDone - 完成回调
 */
export async function streamFetch(url, body, onChunk, onDone) {
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const errText = await resp.text().catch(() => '');
      onDone(errText || `HTTP ${resp.status}`);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'chunk') {
            onChunk(data.content);
          } else if (data.type === 'done') {
            onDone();
            return;
          } else if (data.type === 'error') {
            onDone(data.content);
            return;
          }
        } catch {
          // 忽略解析失败的行
        }
      }
    }
    onDone();
  } catch (err) {
    onDone(err.message || '网络错误');
  }
}
