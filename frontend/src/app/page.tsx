'use client'

import { useSessionStore } from '@/store/session'
import DiagnosticInput from '@/components/DiagnosticInput'
import PhenotypePanel from '@/components/PhenotypePanel'
import HypothesisRanking from '@/components/HypothesisRanking'
import TemporalPanel from '@/components/TemporalPanel'
import GeneticPanel from '@/components/GeneticPanel'
import PathwayPanel from '@/components/PathwayPanel'
import DiagnosticReport from '@/components/DiagnosticReport'
import EvidenceModal from '@/components/EvidenceModal'
import SafetyBadge from '@/components/SafetyBadge'

const PIPELINE_STEPS = [
  { id: 'phenotype', label: '表型分析', layer: 'Layer 1' },
  { id: 'hypothesis', label: '假设生成', layer: 'Layer 2' },
  { id: 'temporal', label: '时序推理', layer: 'Layer 3' },
  { id: 'genetic', label: '遗传推理', layer: 'Layer 4' },
  { id: 'pathway', label: '路径规划', layer: 'Layer 5' },
  { id: 'report', label: '综合报告', layer: 'Layer 6' },
]

const LAYER_ORDER = ['phenotype','hypothesis','temporal','genetic','pathway','report']

export default function Home() {
  const { currentAgent, events, isStreaming, doneLayers } = useSessionStore()

  // 左侧管道导航直接用 store 的 doneLayers
  const currentIdx = currentAgent ? LAYER_ORDER.indexOf(currentAgent) : -1

  const safetyEvents = events.filter(e => e.event === 'safety_valve')

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* 左侧管道导航 */}
      <nav style={{
        width: 180, flexShrink: 0,
        background: 'rgba(15, 26, 54, 0.7)',
        borderRight: '1px solid var(--border)',
        padding: '24px 16px',
        display: 'flex', flexDirection: 'column', gap: 4,
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18,
          background: 'linear-gradient(90deg, #7C3AED, #00D4FF)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          marginBottom: 4, letterSpacing: -0.3,
        }}>
          rare-dx
        </div>
        <div style={{
          fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-body)',
          marginBottom: 20, letterSpacing: 0.3,
        }}>
          罕见病诊断辅助
        </div>
        {PIPELINE_STEPS.map((step, i) => {
          const isDone = doneLayers.has(step.id)
          const isActive = currentAgent === step.id
          const isPending = !isDone && !isActive
          return (
            <div key={step.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 12px', borderRadius: 6,
              fontSize: 13, color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
              background: isActive ? 'rgba(0,212,255,0.06)' : 'transparent',
              position: 'relative', transition: 'all 0.25s ease',
              cursor: 'default',
            }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                border: '2px solid',
                borderColor: isDone ? 'var(--success)' : isActive ? 'var(--cyan)' : 'var(--text-dim)',
                background: isDone ? 'var(--success)' : isActive ? 'var(--cyan)' : 'transparent',
                boxShadow: isActive ? '0 0 8px rgba(0,212,255,0.5)' : 'none',
              }} />
              <div>
                <div style={{ fontWeight: 500, fontSize: 12 }}>{step.label}</div>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{step.layer}</div>
              </div>
              {/* 连接线 */}
              {i < PIPELINE_STEPS.length - 1 && (
                <div style={{
                  position: 'absolute', left: 16, bottom: -4,
                  width: 1, height: 8, background: 'var(--border)',
                }} />
              )}
            </div>
          )
        })}
      </nav>

      {/* 右侧内容 */}
      <main style={{ flex: 1, padding: '24px 32px', maxWidth: 1100 }}>
        {/* Top Bar */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          paddingBottom: 16, borderBottom: '1px solid var(--border)', marginBottom: 20,
        }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 14,
            color: 'var(--text-muted)', letterSpacing: 0.5,
          }}>
            诊断会话
          </div>
          <SafetyBadge events={safetyEvents} />
        </div>

        <DiagnosticInput />

        {/* Streaming 输出区 */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <PhenotypePanel />
          <HypothesisRanking />
          <TemporalPanel />
          <GeneticPanel />
          <PathwayPanel />
          <DiagnosticReport />
        </section>

        {/* Disclaimer */}
        <div style={{
          textAlign: 'center', fontSize: 11, color: 'var(--text-dim)',
          padding: '16px 0', borderTop: '1px solid var(--border)', marginTop: 8,
        }}>
          ⚠️ 本系统输出仅供临床参考，不构成诊断意见。最终诊断由接诊医师结合完整临床信息做出。
        </div>
      </main>

      <EvidenceModal />
    </div>
  )
}
