'use client'

import { useState, useEffect, useRef } from 'react'
import { useSessionStore } from '@/store/session'
import { listenSSE } from '@/lib/api'

export default function DiagnosticInput() {
  const [age, setAge] = useState('3 月龄')
  const [sex, setSex] = useState('男')
  const [description, setDescription] = useState(
    '男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒（血乳酸 5.2 mmol/L），眼球震颤'
  )
  const store = useSessionStore()
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // 组件卸载时关闭 SSE 连接
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [])

  const start = () => {
    const text = description.trim()
    if (!text || store.isStreaming) return
    store.reset()
    store.setStreaming(true)
    const sid = `s-${Date.now()}`
    useSessionStore.setState({ sessionId: sid })

    // 先关闭旧连接
    if (cleanupRef.current) {
      cleanupRef.current()
    }

    cleanupRef.current = listenSSE(text, sid, (event, data) => {
      store.addEvent(event, data)
      switch (event) {
        case 'phenotype_vector':
          useSessionStore.setState({ phenotypeVectors: data.phenotypes || [] })
          break
        case 'hypothesis_ranking':
          useSessionStore.setState({ hypotheses: data.hypotheses || [] })
          break
        case 'temporal_match':
          useSessionStore.setState({ temporalMatches: data.matches || [] })
          break
        case 'inheritance_pattern':
          useSessionStore.setState({ geneticConstraint: data })
          break
        case 'evoi_recommendation':
          useSessionStore.setState({ pathway: data })
          break
        case 'report_delta':
          useSessionStore.setState({ report: data })
          break
        case 'agent_start':
          useSessionStore.setState({ currentAgent: data.agent })
          break
        case 'round_end':
          useSessionStore.setState({ isStreaming: false, currentAgent: null })
          break
        case 'error':
          useSessionStore.setState({ isStreaming: false })
          break
      }
    })
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _hasMetrics = false

  return (
    <section style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', overflow: 'hidden', marginBottom: 20,
    }}>
      {/* Card Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '12px 16px', fontSize: 13, fontWeight: 600,
        color: 'var(--text-muted)', borderBottom: '1px solid var(--border)',
        letterSpacing: 0.3,
      }}>
        <span>📋</span>
        <span>临床信息输入</span>
      </div>

      {/* Card Body */}
      <div style={{ padding: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{
              display: 'block', fontSize: 11, fontWeight: 500,
              color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 0.3,
            }}>年龄</label>
            <input
              type="text" value={age}
              onChange={e => setAge(e.target.value)}
              style={{
                width: '100%', background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 14,
                color: 'var(--text-primary)', outline: 'none',
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--cyan)' }}
              onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
              disabled={store.isStreaming}
            />
          </div>
          <div>
            <label style={{
              display: 'block', fontSize: 11, fontWeight: 500,
              color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 0.3,
            }}>性别</label>
            <select value={sex} onChange={e => setSex(e.target.value)}
              style={{
                width: '100%', background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 14,
                color: 'var(--text-primary)', outline: 'none',
                appearance: 'none',
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2364748B' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat',
                backgroundPosition: 'right 10px center',
                paddingRight: 30,
              }}
              disabled={store.isStreaming}
            >
              <option>男</option>
              <option>女</option>
            </select>
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <label style={{
            display: 'block', fontSize: 11, fontWeight: 500,
            color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 0.3,
          }}>临床描述</label>
          <textarea value={description}
            onChange={e => setDescription(e.target.value)}
            rows={4}
            placeholder="例：男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒..."
            style={{
              width: '100%', background: 'var(--bg-surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 14,
              color: 'var(--text-primary)', outline: 'none', resize: 'vertical',
              minHeight: 80,
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--cyan)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
            disabled={store.isStreaming}
          />
        </div>

        <button onClick={start} disabled={store.isStreaming || !description.trim()}
          style={{
            position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 8,
            marginTop: 16, padding: '10px 24px', border: 'none',
            borderRadius: 'var(--radius-sm)',
            background: 'linear-gradient(90deg, #7C3AED, #00D4FF)',
            color: 'white', fontFamily: 'var(--font-display)', fontWeight: 600,
            fontSize: 14, cursor: 'pointer', opacity: store.isStreaming ? 0.6 : 1,
            transition: 'transform 0.15s, box-shadow 0.2s',
            overflow: 'hidden',
          }}
          onMouseEnter={e => {
            if (!store.isStreaming) {
              e.currentTarget.style.transform = 'translateY(-1px)'
              e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,212,255,0.25)'
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'translateY(0)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        >
          <span style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent)',
            transform: 'translateX(-100%)',
            transition: 'transform 0.6s',
          }} />
          {store.isStreaming ? '⏳ 推理中...' : '开始诊断分析'}
        </button>
      </div>
    </section>
  )
}
