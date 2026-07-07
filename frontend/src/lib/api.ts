const API_BASE = '/api'

/**
 * SSE 客户端 — 按 SSE 规范分帧解析。
 *
 * 关键点：
 * - 以空行（\n\n）分隔一个 event 帧
 * - 同一帧内 event: 行指定该帧 data: 行的事件名
 * - data: 行可有多行，拼成完整 JSON 再解析（防网络分片截断）
 * - 不完整帧留在 buffer 等下次拼接
 */
export async function fetchSSE(
  userMessage: string,
  sessionId?: string,
  onEvent?: (event: string, data: any) => void,
) {
  const params = new URLSearchParams({ user_message: userMessage })
  if (sessionId) params.set('session_id', sessionId)

  const res = await fetch(`${API_BASE}/diagnostic/stream?${params}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // 按 SSE 规范：双换行分帧
    let frameEnd: number
    while ((frameEnd = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, frameEnd)
      buffer = buffer.slice(frameEnd + 2)

      // 解析这一帧
      let eventName = 'message'
      const dataLines: string[] = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        }
      }

      if (dataLines.length === 0) continue
      const dataStr = dataLines.join('\n')

      try {
        const data = JSON.parse(dataStr)
        onEvent?.(eventName, data)
      } catch {
        // JSON 解析失败：把原始字符串传给上层兜底
        onEvent?.(eventName, dataStr)
      }
    }
  }
}
