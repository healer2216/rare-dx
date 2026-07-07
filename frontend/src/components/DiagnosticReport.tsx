'use client'

import { useState } from 'react'
import { useSessionStore } from '@/store/session'

export default function DiagnosticReport() {
  const { report, currentAgent, sessionId, events, setEvidenceModalLayer, doneLayers } = useSessionStore()
  const [downloading, setDownloading] = useState<'docx' | null>(null)
  const [showFullText, setShowFullText] = useState(false)
  const agent = 'report'
  const isActive = currentAgent === agent
  const isDone = doneLayers.has(agent) || !!report
  const isPending = !isActive && !isDone
  const evCount = events.filter(e => e.event === 'evidence' && e.data?.source_layer === 'report')
    .reduce((s, e) => s + (e.data?.references?.length || 0), 0)

  const r: any = report && typeof report === 'object' ? report : {}
  const summary = r.summary_text
  const impression = typeof summary === 'object' ? summary?.impression : (typeof summary === 'string' ? summary : '')
  const llmGenerated = r.llm_generated
  const snapshot = r.summary_snapshot
  const uncertainty = r.uncertainty_notes
  const citations: string[] = Array.isArray(r.evidence_citations) ? r.evidence_citations : []

  // 结构化三段解析
  const sections = { impression: '', differential: '', advice: '' }
  if (impression) {
    // 按「鉴别诊断」或「诊疗建议」标题切分
    const idxDiff = impression.search(/【?鉴别诊断】?/)
    const idxAdvice = impression.search(/【?诊疗建议】?/)
    if (idxDiff >= 0) {
      sections.impression = impression.slice(0, idxDiff).replace(/【?临床印象】?/g,'').trim()
      if (idxAdvice >= 0) {
        sections.differential = impression.slice(idxDiff, idxAdvice).replace(/【?鉴别诊断】?/g,'').trim()
        sections.advice = impression.slice(idxAdvice).replace(/【?诊疗建议】?/g,'').trim()
      } else {
        sections.differential = impression.slice(idxDiff).replace(/【?鉴别诊断】?/g,'').trim()
      }
    } else {
      sections.impression = impression
    }
  }

  const handleDownload = async (format: 'docx') => {
    if (!sessionId) return
    setDownloading(format)
    try {
      const url = `/api/report/download?session_id=${encodeURIComponent(sessionId)}&format=${format}`
      const res = await fetch(url)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: '未知错误' }))
        alert(`下载失败: ${err.error || res.statusText}`)
        return
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `rare-dx-report-${sessionId}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (e: any) {
      alert(`下载失败: ${e.message}`)
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="layer-card" style={{ opacity: isPending ? 0.6 : 1 }}>
      <div className="layer-card-header" style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: 'var(--success)' }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, letterSpacing: 0.2 }}>
          Layer 6 · 综合报告
        </span>
        {llmGenerated && <span style={{
          fontSize: 10, fontWeight: 500, padding: '2px 8px', borderRadius: 999,
          background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.3)',
          color: 'var(--cyan)',
        }}>LLM 增强</span>}
        <span className="layer-status" style={{
          fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 20,
          background: isDone ? 'rgba(16,185,129,0.1)' : isActive ? 'rgba(0,212,255,0.1)' : 'rgba(100,116,139,0.1)',
          color: isDone ? 'var(--success)' : isActive ? 'var(--cyan)' : 'var(--text-dim)',
          animation: isActive ? 'pulse-status 1.5s ease-in-out infinite' : 'none',
        }}>
          {isDone ? '✅ 完成' : isActive ? '⚡ 推理中' : '⏳ 待命'}
        </span>
        {evCount > 0 && (
          <span onClick={() => setEvidenceModalLayer('report')} style={{
            fontSize: 10, cursor: 'pointer', padding: '2px 10px', borderRadius: 10,
            border: '1px solid var(--border)', color: 'var(--cyan)', fontFamily: 'var(--font-mono)',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.1)'; e.currentTarget.style.borderColor = 'var(--cyan)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >证据明细</span>
        )}
      </div>

      <div className="layer-card-body" style={{ padding: 16 }}>
        {isPending && !report && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 13 }}>
            <div className="pulse-bar" />
            <span>等待上游结果...</span>
          </div>
        )}

        {report && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* 临床印象 + 鉴别诊断 + 诊疗建议（结构化） */}
            {impression && (
              <>
                {/* 临床印象 */}
                {sections.impression && (
                  <div style={{
                    padding: 14, borderRadius: 'var(--radius-sm)',
                    background: 'rgba(0,212,255,0.04)',
                    border: '1px solid rgba(0,212,255,0.2)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <span style={{ fontSize: 14 }}>🩺</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--cyan)', letterSpacing: 0.3 }}>临床印象</span>
                    </div>
                    <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', margin: 0 }}>{sections.impression}</p>
                  </div>
                )}

                {/* 鉴别诊断 */}
                {sections.differential && (
                  <div style={{
                    padding: 14, borderRadius: 'var(--radius-sm)',
                    background: 'rgba(22, 32, 68, 0.4)',
                    border: '1px solid var(--border)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <span style={{ fontSize: 14 }}>📋</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: 0.3 }}>鉴别诊断</span>
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.8, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                      {sections.differential.split('\n').map((line, i) => {
                        const isHeading = /^[1-3][.)、]/.test(line.trim())
                        return (
                          <div key={i} style={{
                            padding: isHeading ? '6px 0 2px' : '1px 0',
                            fontWeight: isHeading ? 600 : 400,
                            color: isHeading ? 'var(--text-primary)' : 'var(--text-muted)',
                          }}>
                            {line}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* 诊疗建议 */}
                {sections.advice && (
                  <div style={{
                    padding: 14, borderRadius: 'var(--radius-sm)',
                    background: 'rgba(16, 185, 129, 0.04)',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <span style={{ fontSize: 14 }}>🎯</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--success)', letterSpacing: 0.3 }}>诊疗建议</span>
                    </div>
                    <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', margin: 0 }}>{sections.advice}</p>
                  </div>
                )}

                {/* 无分段时的兜底（旧版报告）*/}
                {!sections.differential && !sections.advice && (
                  <div style={{
                    padding: 14, borderRadius: 'var(--radius-sm)',
                    background: 'rgba(0,212,255,0.04)',
                    border: '1px solid rgba(0,212,255,0.2)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <span style={{ fontSize: 14 }}>🩺</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--cyan)', letterSpacing: 0.3 }}>临床印象</span>
                    </div>
                    <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', margin: 0 }}>{impression}</p>
                  </div>
                )}
              </>
            )}

            {/* 鉴别快照 */}
            {snapshot && (
              <div style={{
                padding: 12, borderRadius: 'var(--radius-sm)',
                background: 'rgba(22, 32, 68, 0.5)',
                border: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>📊 鉴别诊断快照</span>
                <span style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.5 }}>{snapshot}</span>
              </div>
            )}

            {/* 不确定性说明 */}
            {uncertainty && (
              <div style={{
                padding: 12, borderRadius: 'var(--radius-sm)',
                background: 'rgba(245, 158, 11, 0.05)',
                border: '1px solid rgba(245, 158, 11, 0.2)',
                display: 'flex', alignItems: 'flex-start', gap: 10,
              }}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>⚠️</span>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 4, fontWeight: 500 }}>不确定性说明</div>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, margin: 0 }}>{uncertainty}</p>
                </div>
              </div>
            )}

            {/* 证据引用 */}
            {citations.length > 0 && (
              <div style={{
                padding: 12, borderRadius: 'var(--radius-sm)',
                background: 'rgba(22, 32, 68, 0.5)',
                border: '1px solid var(--border)',
              }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, fontWeight: 500 }}>
                  📚 证据引用
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {citations.map((c, i) => (
                    <span key={i} style={{
                      fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)',
                    }}>
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 详细推理文本（可折叠） */}
            {r.main_text && (
              <div>
                <button onClick={() => setShowFullText(!showFullText)} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 11, color: 'var(--cyan)', padding: '4px 0',
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                }}>
                  <span style={{ display: 'inline-block', transition: 'transform 0.2s',
                    transform: showFullText ? 'rotate(90deg)' : 'rotate(0)' }}>▶</span>
                  {showFullText ? '收起详细推理文本' : '展开详细推理文本'}
                </button>
                {showFullText && (
                  <pre style={{
                    marginTop: 8, padding: 12, borderRadius: 'var(--radius-sm)',
                    fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.7,
                    fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap',
                    background: 'rgba(15, 26, 54, 0.6)', border: '1px solid var(--border)',
                    maxHeight: 400, overflow: 'auto',
                  }}>
                    {r.main_text}
                  </pre>
                )}
              </div>
            )}

            {/* 下载按钮 */}
            <div style={{
              display: 'flex', gap: 12, marginTop: 4, paddingTop: 12,
              borderTop: '1px solid var(--border)',
            }}>
              <button onClick={() => handleDownload('docx')} disabled={!sessionId || !!downloading}
                style={{
                  padding: '8px 16px', fontSize: 12, borderRadius: 'var(--radius-sm)',
                  border: '1px solid rgba(0,212,255,0.3)', background: 'transparent',
                  color: 'var(--cyan)', cursor: 'pointer', opacity: !sessionId || !!downloading ? 0.4 : 1,
                  transition: 'background 0.2s',
                }}
                onMouseEnter={e => { if (!downloading) e.currentTarget.style.background = 'rgba(0,212,255,0.1)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
              >
                {downloading === 'docx' ? '生成中…' : '📄 下载 Word 报告'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
