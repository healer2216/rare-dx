'use client'

import { useSessionStore } from '@/store/session'
import { useState } from 'react'

export default function HypothesisRanking() {
  const { hypotheses, currentAgent, events, setEvidenceModalLayer, doneLayers } = useSessionStore()
  const [expanded, setExpanded] = useState<number | null>(null)
  // 从 events 数组兜底解析（预防 store 字段被覆盖）
  const hypFromEvents = events
    .filter(e => e.event === 'hypothesis_ranking' && e.data?.hypotheses?.length)
    .flatMap(e => e.data.hypotheses)
  const hypos = (hypotheses?.length ? hypotheses : hypFromEvents) || []
  const agent = 'hypothesis'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent)
  const isPending = !isActive && !isDone
  const evCount = hypos.reduce((s, h) => s + (h.evidence_count || h.evidence_ids?.length || 0), 0)

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--purple)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 2 · 假设生成
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
          <span onClick={() => setEvidenceModalLayer('hypothesis')} style={{
            fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
            border: '1px solid var(--border)', color: 'var(--cyan)',
            fontFamily: 'var(--font-mono)',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >证据明细</span>
        )}
      </div>
      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && !hypos?.length && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}
        {isDone && !hypos?.length && (
          <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 12, fontStyle: 'italic' }}>
            当前表型未匹配到高后验假设，可尝试补充更多临床信息。
          </div>
        )}
        {hypos?.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {hypos.slice(0, 5).map((h: any, i: number) => {
              const rank = h.rank || i + 1
              const conf = h.confidence || h.posterior_prob || 0
              const pct = Math.min(Math.round(conf * 100), 100)
              const llmDiff = h.reasoning_chain?.includes('LLM鉴别:')
                ? h.reasoning_chain.split('LLM鉴别:').pop()?.trim()
                : ''
              const evCount = h.evidence_count ?? (h.evidence_ids?.length || 0)
              const isExpanded = expanded === i
              return (
                <div key={i} className={`hypothesis-card rank-${Math.min(rank, 3)}`} style={{
                  display: 'flex', gap: 12, padding: 12,
                  borderRadius: 'var(--radius-sm)',
                  background: 'rgba(22, 32, 68, 0.5)',
                  border: '1px solid var(--border)',
                  cursor: evCount > 0 ? 'pointer' : 'default',
                }}
                  onClick={() => evCount > 0 && setExpanded(isExpanded ? null : i)}
                >
                  <div style={{
                    width: 24, height: 24, borderRadius: '50%',
                    background: 'var(--bg-surface)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, flexShrink: 0,
                  }}>
                    {rank}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
                      {h.disease_name}
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 8 }}>
                        {h.disease_id}
                      </span>
                    </div>
                    <div style={{ height: 4, background: 'var(--bg-surface)', borderRadius: 2, marginBottom: 6, overflow: 'hidden' }}>
                      <div className="hypo-bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                    <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                      <span>后验概率 <strong style={{ color: 'var(--text-primary)' }}>{(h.posterior_prob ?? h.bayesian_score)?.toFixed(4)}</strong></span>
                      <span>置信度 <strong style={{ color: 'var(--text-primary)' }}>{h.confidence?.toFixed(2)}</strong></span>
                      {evCount > 0 && (
                        <span style={{ color: 'var(--success)', cursor: 'pointer' }}>
                          🅐 {evCount} 条证据 {isExpanded ? '▲' : '▼'}
                        </span>
                      )}
                    </div>
                    {/* LLM 鉴别诊断（展开时显示）*/}
                    {isExpanded && llmDiff && (
                      <div style={{
                        marginTop: 8, padding: 10, borderRadius: 'var(--radius-sm)',
                        background: 'rgba(0,212,255,0.03)',
                        border: '1px solid rgba(0,212,255,0.15)',
                        fontSize: 11, color: 'var(--text-muted)',
                        lineHeight: 1.6,
                      }}>
                        <div style={{ fontSize: 10, color: 'var(--cyan)', marginBottom: 4, fontWeight: 500 }}>📋 该病鉴别分析</div>
                        {llmDiff}
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
