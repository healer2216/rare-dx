const API_BASE = '/api'

/**
 * SSE 客户端 — 使用浏览器原生 EventSource API（默认支持自动重连、流式解析）
 *
 * 相比 fetch + ReadableStream 方案，EventSource 更稳定：
 * - 浏览器原生实现，无分帧/拼接问题
 * - 自动保活，无需手动处理 ping
 * - 支持 last-event-id 自动重连
 * - 每种 event 类型对应独立的 on<event> 回调
 */
export function listenSSE(
  userMessage: string,
  sessionId?: string,
  onEvent?: (event: string, data: any) => void,
): () => void {
  const params = new URLSearchParams({ user_message: userMessage })
  if (sessionId) params.set('session_id', sessionId)

  const url = `${API_BASE}/diagnostic/stream?${params}`
  const source = new EventSource(url)

  source.addEventListener('message', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      onEvent?.('message', data)
    } catch {
      onEvent?.('message', e.data)
    }
  })

  source.addEventListener('round_start', (e) => parseAndFire(e, 'round_start'))
  source.addEventListener('round_end', (e) => { parseAndFire(e, 'round_end'); source.close() })
  source.addEventListener('agent_start', (e) => parseAndFire(e, 'agent_start'))
  source.addEventListener('agent_delta', (e) => parseAndFire(e, 'agent_delta'))
  source.addEventListener('agent_done', (e) => parseAndFire(e, 'agent_done'))
  source.addEventListener('phenotype_vector', (e) => parseAndFire(e, 'phenotype_vector'))
  source.addEventListener('hypothesis_ranking', (e) => parseAndFire(e, 'hypothesis_ranking'))
  source.addEventListener('temporal_match', (e) => parseAndFire(e, 'temporal_match'))
  source.addEventListener('inheritance_pattern', (e) => parseAndFire(e, 'inheritance_pattern'))
  source.addEventListener('evoi_recommendation', (e) => parseAndFire(e, 'evoi_recommendation'))
  source.addEventListener('report_delta', (e) => parseAndFire(e, 'report_delta'))
  source.addEventListener('evidence', (e) => parseAndFire(e, 'evidence'))
  source.addEventListener('safety_valve', (e) => parseAndFire(e, 'safety_valve'))
  source.addEventListener('error', (e) => { parseAndFire(e, 'error'); source.close() })

  source.onerror = (err) => {
    console.error('SSE 连接错误:', err)
    source.close()
  }

  return () => source.close()

  function parseAndFire(e: MessageEvent, eventName: string) {
    try {
      const data = JSON.parse(e.data)
      onEvent?.(eventName, data)
    } catch {
      onEvent?.(eventName, e.data)
    }
  }
}

// 保留旧函数别名保证兼容
export const fetchSSE = listenSSE
