'use client'

import { useSessionStore } from '@/store/session'

export default function PhenotypePanel() {
  const { phenotypeVectors, currentAgent, isStreaming, events, setEvidenceModalLayer, doneLayers, layer1Metrics } = useSessionStore()
  const agent = 'phenotype'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent) || (phenotypeVectors?.length > 0)
  const isPending = !isActive && !isDone
  const evCount = events.filter(e => e.event === 'evidence' && e.data?.source_layer === 'phenotype')
    .reduce((s, e) => s + (e.data?.references?.length || 0), 0)
  const llmCount = layer1Metrics?.llm_count ?? 0
  const dictCount = layer1Metrics?.dict_count ?? 0
  const mergedCount = layer1Metrics?.merged_count ?? 0

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--cyan)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 1 · 表型分析
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
          <span
            onClick={() => setEvidenceModalLayer('phenotype')}
            style={{
              fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
              border: '1px solid var(--border)', color: 'var(--cyan)',
              fontFamily: 'var(--font-mono)',
              transition: 'background 0.2s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >
            证据明细
          </span>
        )}
      </div>
      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && !phenotypeVectors?.length && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}
        {phenotypeVectors?.length > 0 && (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {phenotypeVectors.map((p: any, i: number) => (
                <span key={i} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', borderRadius: 20, fontSize: 12,
                  border: '1px solid', background: 'rgba(0,212,255,0.06)',
                  borderColor: 'rgba(0,212,255,0.15)', color: 'var(--text-primary)',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cyan)', fontWeight: 500 }}>
                    {p.hpo_id || '—'}
                  </span>
                  <span style={{ fontWeight: 500 }}>{p.term_name}</span>
                  {p.modifiers?.length > 0 && (
                    <span style={{
                      fontSize: 10, color: 'var(--text-muted)',
                      paddingLeft: 6, borderLeft: '1px solid var(--border)',
                    }}>
                      {p.modifiers.map((m: any) => [m.distribution, m.temporal_pattern, m.severity].filter(Boolean).join(' · ')).filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
              ))}
            </div>
            {/* 小证据计数 */}
            {phenotypeVectors.length > 0 && (
              <div style={{
                display: 'flex', gap: 8, alignItems: 'center', marginTop: 12,
                paddingTop: 12, borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text-muted)',
              }}>
                <span>📄 共 {phenotypeVectors.length} 个表型</span>
                {layer1Metrics && (
                  <>
                    <span>·</span>
                    <span>LLM: {llmCount}</span>
                    <span>词典: {dictCount}</span>
                    <span>合并: {mergedCount}</span>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
