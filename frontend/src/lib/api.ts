const API_BASE = '/api'

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
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = 'message'
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        const dataStr = line.slice(5).trim()
        try {
          const data = JSON.parse(dataStr)
          onEvent?.(currentEvent, data)
        } catch {
          onEvent?.(currentEvent, dataStr)
        }
      }
    }
  }
}
