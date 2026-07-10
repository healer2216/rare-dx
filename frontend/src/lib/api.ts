'use client'

import { useState } from 'react'
import { useSessionStore } from '@/store/session'

const API_BASE = '/api'

// ========== SSE Client ==========

export interface SSEOptions {
  /** 心跳超时（毫秒），超过此时间无任何事件则判定连接死亡 */
  heartbeatTimeoutMs?: number
  /** 连接疑似死亡时的回调 */
  onStale?: () => void
}

/**
 * SSE 客户端 — 浏览器原生 EventSource。
 *
 * 特性：
 * - 自动保活心跳处理
 * - 连接死亡检测 + 自动重连回调
 * - 每种 event 类型对应独立的回调
 */
export function listenSSE(
  userMessage: string,
  sessionId?: string,
  onEvent?: (event: string, data: any) => void,
  opts?: SSEOptions,
): () => void {
  const params = new URLSearchParams({ user_message: userMessage })
  if (sessionId) params.set('session_id', sessionId)

  const url = `${API_BASE}/diagnostic/stream?${params}`
  const source = new EventSource(url)
  const heartbeatTimeoutMs = opts?.heartbeatTimeoutMs ?? 30000
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  let staleCalled = false

  const resetHeartbeat = () => {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => {
      if (!staleCalled) {
        staleCalled = true
        console.warn('[sse] heartbeat timeout, connection considered stale')
        opts?.onStale?.()
      }
    }, heartbeatTimeoutMs)
  }

  // 启动心跳计时器
  resetHeartbeat()

  source.addEventListener('message', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      onEvent?.('message', data)
    } catch {
      onEvent?.('message', e.data)
    }
    resetHeartbeat()
  })

  source.addEventListener('round_start', (e) => { parseAndFire(e, 'round_start'); resetHeartbeat() })
  source.addEventListener('round_end', (e) => { parseAndFire(e, 'round_end'); source.close() })
  source.addEventListener('agent_start', (e) => { parseAndFire(e, 'agent_start'); resetHeartbeat() })
  source.addEventListener('agent_delta', (e) => { parseAndFire(e, 'agent_delta'); resetHeartbeat() })
  source.addEventListener('agent_done', (e) => { parseAndFire(e, 'agent_done'); resetHeartbeat() })
  source.addEventListener('phenotype_vector', (e) => { parseAndFire(e, 'phenotype_vector'); resetHeartbeat() })
  source.addEventListener('hypothesis_ranking', (e) => { parseAndFire(e, 'hypothesis_ranking'); resetHeartbeat() })
  source.addEventListener('temporal_match', (e) => { parseAndFire(e, 'temporal_match'); resetHeartbeat() })
  source.addEventListener('inheritance_pattern', (e) => { parseAndFire(e, 'inheritance_pattern'); resetHeartbeat() })
  source.addEventListener('evoi_recommendation', (e) => { parseAndFire(e, 'evoi_recommendation'); resetHeartbeat() })
  source.addEventListener('report_delta', (e) => { parseAndFire(e, 'report_delta'); resetHeartbeat() })
  source.addEventListener('evidence', (e) => { parseAndFire(e, 'evidence'); resetHeartbeat() })
  source.addEventListener('safety_valve', (e) => { parseAndFire(e, 'safety_valve'); resetHeartbeat() })
  source.addEventListener('heartbeat', (e) => { /* keepalive, no-op */ resetHeartbeat() })
  source.addEventListener('error', (e: MessageEvent) => {
    parseAndFire(e, 'error')
    source.close()
  })

  source.onerror = (err) => {
    console.error('SSE 连接错误:', err)
    source.close()
  }

  return () => {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    source.close()
  }

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
