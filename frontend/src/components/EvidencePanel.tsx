'use client'

import { useState } from 'react'
import { useSessionStore } from '@/store/session'

interface Evidence {
  id: string
  title: string
  doi: string
  journal: string
  publish_date: string
  study_type: string
  impact_factor: string
  abstract: string
  grade: string
  source: string
  url: string | null
}

export default function EvidencePanel() {
  const { events } = useSessionStore()
  const evidenceEvents = events.filter((e) => e.event === 'evidence')
  const [active, setActive] = useState<string | null>(null)

  if (!evidenceEvents.length) return null

  const allRefs: Evidence[] = evidenceEvents.flatMap((e) => e.data?.references || [])
  const totalCount = allRefs.length
  const byLayer = evidenceEvents.map((e) => ({
    layer: e.data?.source_layer || 'unknown',
    items: (e.data?.references || []) as Evidence[],
  }))

  const activeItem: Evidence | null =
    active ? allRefs.find((r) => r.id === active) || null : null

  const gradeColor: Record<string, string> = {
    A: 'rgba(16,185,129,0.8)',
    B: 'rgba(0,212,255,0.8)',
    C: 'rgba(245,158,11,0.8)',
    D: 'rgba(100,116,139,0.8)',
    E: 'rgba(239,68,68,0.8)',
  }

  return (
    <div className="dx-card mb-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full bg-dx-success" />
        <h3 className="font-display font-semibold text-dx-success">循证证据池</h3>
        <span className="text-xs text-dx-muted">{totalCount} 条证据 · {byLayer.length} 层</span>
      </div>

      {/* Per-layer list */}
      <div className="space-y-3">
        {byLayer.map((group, gi) => (
          <div key={gi}>
            <div className="text-xs text-dx-cyan mb-1.5 flex items-center gap-1.5">
              <span className="opacity-60">Layer</span>
              <span className="font-mono font-medium">{group.layer}</span>
              <span className="opacity-40">·</span>
              <span className="opacity-60">{group.items.length} 条</span>
            </div>
            <div className="grid grid-cols-1 gap-1.5">
              {group.items.map((r, ri) => (
                <button
                  key={ri}
                  onClick={() => setActive(active === r.id ? null : r.id)}
                  className="w-full text-left group rounded transition-colors"
                  style={{
                    padding: '8px 10px',
                    background: 'rgba(22, 32, 68, 0.4)',
                    border: '1px solid',
                    borderColor: active === r.id ? 'rgba(0,212,255,0.4)' : 'var(--border)',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => { if (active !== r.id) e.currentTarget.style.background = 'rgba(22, 32, 68, 0.7)' }}
                  onMouseLeave={e => { if (active !== r.id) e.currentTarget.style.background = 'rgba(22, 32, 68, 0.4)' }}
                >
                  <div className="flex items-center gap-2">
                    <span style={{
                      flexShrink: 0,
                      width: 22, height: 22,
                      borderRadius: 4,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 700,
                      background: gradeColor[r.grade] || 'rgba(100,116,139,0.6)',
                      color: '#0a0f1f',
                    }}>
                      {r.grade || '?'}
                    </span>
                    <span style={{
                      flex: 1, minWidth: 0,
                      fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      color: 'var(--text-primary)', fontWeight: 500,
                    }}>
                      {r.title}
                    </span>
                    {r.doi && (
                      <a
                        href={`https://doi.org/${r.doi}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          flexShrink: 0,
                          fontSize: 10, color: 'var(--cyan)',
                          padding: '2px 6px', borderRadius: 4,
                          background: 'rgba(0,212,255,0.08)',
                          textDecoration: 'none',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.textDecoration = 'underline' }}
                        onMouseLeave={e => { e.currentTarget.style.textDecoration = 'none' }}
                      >
                        DOI ↗
                      </a>
                    )}
                    <span style={{
                      flexShrink: 0, fontSize: 10, color: 'var(--text-dim)',
                      display: 'inline-block', transition: 'transform 0.2s',
                      transform: active === r.id ? 'rotate(90deg)' : 'rotate(0)',
                    }}>▶</span>
                  </div>

                  {/* Expand detail */}
                  {active === r.id && (
                    <div style={{
                      marginTop: 8, paddingTop: 8,
                      borderTop: '1px solid var(--border)',
                      fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6,
                    }}>
                      {r.abstract && (
                        <p style={{ marginBottom: 6 }}>{r.abstract}</p>
                      )}
                      <div style={{
                        display: 'flex', flexWrap: 'wrap', gap: '4px 12px', fontSize: 10, color: 'var(--text-dim)',
                      }}>
                        {r.journal && <span>📰 {r.journal}</span>}
                        {r.publish_date && <span>📅 {r.publish_date}</span>}
                        {r.study_type && <span>🔬 {r.study_type}</span>}
                        {r.impact_factor && <span>📈 IF {r.impact_factor}</span>}
                        {r.source && <span>📦 {r.source}</span>}
                      </div>
                      {r.url && r.doi && (
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            marginTop: 6, fontSize: 11, color: 'var(--cyan)',
                            textDecoration: 'none',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.textDecoration = 'underline' }}
                          onMouseLeave={e => { e.currentTarget.style.textDecoration = 'none' }}
                        >
                          🔗 打开来源页
                        </a>
                      )}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
