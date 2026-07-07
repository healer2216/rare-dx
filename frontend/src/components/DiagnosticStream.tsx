'use client'

import { useState } from 'react'
import { useSessionStore } from '@/store/session'
import { fetchSSE } from '@/lib/api'

export default function DiagnosticStream() {
  const [input, setInput] = useState(
    '男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，眼球震颤'
  )
  const store = useSessionStore()

  const start = async () => {
    if (!input.trim() || store.isStreaming) return
    store.reset()
    store.setStreaming(true)
    const sid = `s-${Date.now()}`
    useSessionStore.setState({ sessionId: sid })
    try {
      await fetchSSE(input, sid, (event, data) => {
        store.addEvent(event, data)
        // 按事件类型更新对应字段
        switch (event) {
          case 'phenotype_vector':
            useSessionStore.setState({ phenotypeVectors: data.phenotypes || [] })
            if (data.metrics) {
              useSessionStore.setState({ layer1Metrics: data.metrics })
            }
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
    } catch (e) {
      console.error('SSE 失败:', e)
      useSessionStore.setState({ isStreaming: false })
    }
  }

  return (
    <div className="dx-card mb-6">
      <label className="block text-sm font-medium text-dx-cyan mb-2">
        输入临床描述
      </label>
      <textarea
        className="w-full h-32 bg-dx-deep border border-dx-cyan/20 rounded-md p-3 text-dx-card placeholder-dx-muted focus:outline-none focus:ring-2 focus:ring-dx-cyan/50"
        placeholder="例：男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        disabled={store.isStreaming}
      />
      <button
        className="mt-3 px-6 py-2 dx-gradient text-white rounded-md disabled:opacity-50 transition hover:opacity-90"
        onClick={start}
        disabled={store.isStreaming || !input.trim()}
      >
        {store.isStreaming ? '推理中…' : '开始诊断分析'}
      </button>
    </div>
  )
}
