'use client'

import { useSessionStore } from '@/store/session'

export default function GeneticPanel() {
  const { geneticConstraint, currentAgent, events, setEvidenceModalLayer, doneLayers } = useSessionStore()
  const agent = 'genetic'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent)
  const patterns = geneticConstraint?.patterns || []
  const compatible = geneticConstraint?.compatible || []
  const incompatible = geneticConstraint?.incompatible || []
  const isPending = !isActive && !isDone
  const evCount = events.filter(e => e.event === 'evidence' && e.data?.source_layer === 'genetic')
    .reduce((s, e) => s + (e.data?.references?.length || 0), 0)

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--success)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 4 · 遗传推理
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
          <span onClick={() => setEvidenceModalLayer('genetic')} style={{
            fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
            border: '1px solid var(--border)', color: 'var(--cyan)', fontFamily: 'var(--font-mono)',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >证据明细</span>
        )}
      </div>
      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && !geneticConstraint && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}
        {isDone && !patterns.length && (
          <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 12, fontStyle: 'italic' }}>
            该层推理完成，未推断出遗传模式。
          </div>
        )}
        {patterns.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {patterns.map((p: any, i: number) => {
              const llmExplain = Array.isArray(p.evidence)
                ? p.evidence.find((e: string) => e.includes('LLM解释:'))?.split('LLM解释:').pop()?.trim()
                : undefined
              return (
                <div key={i} style={{
                  padding: 12, borderRadius: 'var(--radius-sm)',
                  background: 'rgba(22, 32, 68, 0.5)',
                  border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      color: 'var(--cyan)', fontWeight: 500,
                      padding: '2px 8px', borderRadius: 4,
                      background: 'rgba(0,212,255,0.08)',
                    }}>
                      {p.mode}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      置信度 {p.confidence?.toFixed(2)}
                    </span>
                  </div>
                  {llmExplain && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                      {llmExplain}
                    </div>
                  )}
                </div>
              )
            })}
            <div style={{ display: 'flex', gap: 12, fontSize: 11 }}>
              <span style={{ color: 'var(--success)' }}>
                兼容 {compatible.length} 个
              </span>
              <span style={{ color: 'var(--danger)' }}>
                不兼容 {incompatible.length} 个
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
