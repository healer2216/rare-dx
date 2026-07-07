'use client'

import { useSessionStore } from '@/store/session'
import { useMemo } from 'react'

export default function EvidenceModal() {
  const { events, evidenceModalLayer, setEvidenceModalLayer, hypotheses } = useSessionStore()

  const layerRefs = useMemo(() => {
    if (!evidenceModalLayer) return []
    // 优先从 evidence 事件读取
    const fromEvents = events
      .filter((e) => e.event === 'evidence' && e.data?.source_layer === evidenceModalLayer)
      .flatMap((e) => e.data?.references || [])
    if (fromEvents.length > 0) return fromEvents
    // hypothesis 层兜底：从 hypotheses 的 evidence_ids 读取
    if (evidenceModalLayer === 'hypothesis' && hypotheses?.length) {
      return hypotheses.slice(0, 5).flatMap((h: any) => {
        const ids = h.evidence_ids || []
        return ids.slice(0, 3).map((id: string) => ({
          id, title: `相关证据: ${h.disease_name}`,
          doi: null, url: null, source: 'hypothesis',
          grade: 'C', journal: '', publish_date: '',
        }))
      })
    }
    return []
  }, [events, evidenceModalLayer, hypotheses])

  const gradeColor: Record<string, string> = {
    A: 'rgba(16,185,129,0.8)',
    B: 'rgba(0,212,255,0.8)',
    C: 'rgba(245,158,11,0.8)',
    D: 'rgba(100,116,139,0.8)',
    E: 'rgba(239,68,68,0.8)',
  }

  function jumpUrl(r: any): string | null {
    // 优先 DOI
    if (r.doi) return `https://doi.org/${r.doi}`
    // 显式 url
    if (r.url) return r.url
    const id = r.id || ''
    const src = r.source || ''
    // PubMed 数字 ID
    if (src === 'paper_en' && /^\d+$/.test(id)) return `https://pubmed.ncbi.nlm.nih.gov/${id}/`
    // ORPHA 号（guide 类中国共识等）
    const orphaMatch = id.match(/ORPHA:(\d+)/) || id.match(/^(\d{3,})$/)
    if (orphaMatch && (src === 'guide' || src === 'guide_cn')) {
      return `https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=EN&Expert=ORPHA${orphaMatch[1]}`
    }
    // 通用数字 ID 兜底 PubMed
    if (/^\d+$/.test(id)) return `https://pubmed.ncbi.nlm.nih.gov/${id}/`
    return null
  }

  if (!evidenceModalLayer) return null

  return (
    <div
      onClick={() => setEvidenceModalLayer(null)}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(8,14,36,0.85)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 600, maxHeight: '80vh',
          background: 'var(--bg-card)', borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: '1px solid var(--border)',
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            📚 证据明细 — Layer {evidenceModalLayer}
          </span>
          <button
            onClick={() => setEvidenceModalLayer(null)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 18, color: 'var(--text-muted)',
              width: 28, height: 28, borderRadius: 6,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(100,116,139,0.2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>
          {layerRefs.length === 0 && (
            <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-dim)', fontSize: 13 }}>
              该层暂无证据
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {layerRefs.map((r: any, i: number) => {
              const url = jumpUrl(r)
              return (
                <div key={i} style={{
                  padding: '10px 12px', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(22, 32, 68, 0.5)',
                  border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <span style={{
                      flexShrink: 0, width: 22, height: 22, borderRadius: 4,
                      fontSize: 10, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: gradeColor[r.grade] || 'rgba(100,116,139,0.6)',
                      color: '#0a0f1f',
                    }}>
                      {r.grade || '?'}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500, marginBottom: 4 }}>
                        {r.title}
                      </div>
                      {/* 元数据 */}
                      {(r.journal || r.publish_date || r.study_type || r.impact_factor) && (
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 6, display: 'flex', flexWrap: 'wrap', gap: '2px 10px' }}>
                          {r.journal && <span>📰 {r.journal}</span>}
                          {r.publish_date && <span>📅 {r.publish_date}</span>}
                          {r.study_type && <span>🔬 {r.study_type}</span>}
                          {r.impact_factor && <span>📈 IF {r.impact_factor}</span>}
                        </div>
                      )}
                      {/* 摘要 */}
                      {r.abstract && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 6 }}>
                          {r.abstract}
                        </div>
                      )}
                      {/* guide 类无摘要兜底 */}
                      {!r.abstract && r.source && (r.source === 'guide' || r.source === 'guide_cn') && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 6, fontStyle: 'italic' }}>
                          📄 中国专家共识文献 · 发布于 {r.publish_date || '未知日期'} · 本地知识库收录
                        </div>
                      )}
                      {/* 跳转 */}
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            fontSize: 11, color: 'var(--cyan)',
                            textDecoration: 'none', padding: '4px 10px', borderRadius: 4,
                            background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.15)'; e.currentTarget.style.textDecoration = 'underline' }}
                          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.08)'; e.currentTarget.style.textDecoration = 'none' }}
                        >
                          🔗 查看原文{r.doi ? ' (DOI)' : r.source === 'guide' ? ' (ORPHA)' : ' (PubMed)'}
                        </a>
                      ) : (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 11, color: 'var(--text-dim)',
                          padding: '4px 10px', borderRadius: 4,
                          background: 'rgba(100,116,139,0.08)', border: '1px solid var(--border)',
                        }}>
                          📦 本地文献（无网络原文）
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 18px', borderTop: '1px solid var(--border)',
          fontSize: 11, color: 'var(--text-dim)', textAlign: 'right',
        }}>
          {layerRefs.length} 条
          <span style={{ marginLeft: 12, cursor: 'pointer' }}
            onClick={() => setEvidenceModalLayer(null)}>
            关闭
          </span>
        </div>
      </div>
    </div>
  )
}
