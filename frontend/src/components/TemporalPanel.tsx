'use client'

import { useSessionStore } from '@/store/session'

export default function TemporalPanel() {
  const { temporalMatches, currentAgent, events, setEvidenceModalLayer, doneLayers } = useSessionStore()
  const agent = 'temporal'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent)
  const isPending = !isActive && !isDone
  const evCount = events.filter(e => e.event === 'evidence' && e.data?.source_layer === 'temporal')
    .reduce((s, e) => s + (e.data?.references?.length || 0), 0)

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--warning)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 3 · 时序推理
        </span>
        <span className="layer-status" style={{
          fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 20,
          background: isDone ? 'rgba(16,185,129,0.1)' : isActive ? 'rgba(0,212,255,0.1)' : 'rgba(100,116,139,0.1)',
          color: isDone ? 'var(--success)' : isActive ? 'var(--cyan)' : 'var(--text-dim)',
          animation: isActive ? 'pulse-status 1.5s ease-in-out infinite' : 'none',
        }}>
          {isDone ? '✅ 完成' : isActive ? '⚡ 推理中' : '⏳ 排队中'}
        </span>
        {evCount > 0 && (
          <span onClick={() => setEvidenceModalLayer('temporal')} style={{
            fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
            border: '1px solid var(--border)', color: 'var(--cyan)', fontFamily: 'var(--font-mono)',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >证据明细</span>
        )}
      </div>
      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && !temporalMatches?.length && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}
        {isDone && !temporalMatches?.length && (
          <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 12, fontStyle: 'italic' }}>
            该层推理完成，未找到匹配的时序模式。
          </div>
        )}
        {temporalMatches?.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {temporalMatches.slice(0, 3).map((t: any, i: number) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                background: 'rgba(22, 32, 68, 0.5)',
              }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', minWidth: 90 }}>
                  {t.disease_id}
                </span>
                <span style={{ fontSize: 12, color: 'var(--warning)' }}>
                  综合 {t.overall_temporal_score?.toFixed(2)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                  发病 {t.onset_consistency?.toFixed(2)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                  进展 {t.progression_consistency?.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
