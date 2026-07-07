'use client'

import { useSessionStore } from '@/store/session'

export default function PathwayPanel() {
  const { pathway, currentAgent, events, setEvidenceModalLayer, doneLayers } = useSessionStore()
  const agent = 'pathway'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent)
  const isPending = !isActive && !isDone
  const evCount = events.filter(e => e.event === 'evidence' && e.data?.source_layer === 'pathway')
    .reduce((s, e) => s + (e.data?.references?.length || 0), 0)

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--cyan)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 5 · 路径规划 (EVOI)
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
          <span onClick={() => setEvidenceModalLayer('pathway')} style={{
            fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
            border: '1px solid var(--border)', color: 'var(--cyan)', fontFamily: 'var(--font-mono)',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >证据明细</span>
        )}
      </div>
      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && (!pathway?.steps?.length && !isDone) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}
        {isDone && !pathway?.steps?.length && (
          <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 12, fontStyle: 'italic' }}>
            该层推理完成，未生成推荐检查路径。
          </div>
        )}
        {pathway?.steps?.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {pathway.steps.slice(0, 3).map((s: any, i: number) => {
              const llmReason = s.rationale?.includes('LLM理由:')
                ? s.rationale.split('LLM理由:').pop()?.trim()
                : ''
              return (
                <div key={i} className={`hypothesis-card rank-${Math.min(s.rank || i + 1, 3)}`} style={{
                  display: 'flex', gap: 12, padding: 12,
                  borderRadius: 'var(--radius-sm)',
                  background: 'rgba(22, 32, 68, 0.5)',
                  border: '1px solid var(--border)',
                }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: '50%',
                    background: 'var(--bg-surface)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, flexShrink: 0,
                  }}>
                    {s.rank || i + 1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                      {s.test_name}
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cyan)', fontWeight: 400, marginLeft: 8 }}>
                        EVOI {(s.evoi_score ?? s.net_evoi)?.toFixed(3)}
                      </span>
                    </div>
                    {llmReason && (
                      <div style={{
                        fontSize: 11, color: 'var(--text-muted)',
                        lineHeight: 1.5,
                      }}>
                        {llmReason}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
