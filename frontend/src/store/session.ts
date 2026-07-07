import { create } from 'zustand'

interface SessionState {
  sessionId: string | null
  userMessage: string
  isStreaming: boolean
  currentAgent: string | null
  phenotypeVectors: any[]
  hypotheses: any[]
  temporalMatches: any[]
  geneticConstraint: any
  pathway: any
  report: any
  events: Array<{ event: string; data: any }>
  doneLayers: Set<string>
  evidenceModalLayer: string | null

  setUserMessage: (msg: string) => void
  setStreaming: (v: boolean) => void
  addEvent: (event: string, data: any) => void
  setEvidenceModalLayer: (layer: string | null) => void
  reset: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  userMessage: '',
  isStreaming: false,
  currentAgent: null,
  phenotypeVectors: [],
  hypotheses: [],
  temporalMatches: [],
  geneticConstraint: null,
  pathway: null,
  report: null,
  evidenceModalLayer: null,
  doneLayers: new Set<string>(),
  events: [],

  setUserMessage: (msg) => set({ userMessage: msg }),
  setStreaming: (v) => set({ isStreaming: v }),
  addEvent: (event, data) =>
    set((state) => {
      const dl = new Set(state.doneLayers)
      if (event === 'agent_done' && data?.agent) dl.add(data.agent)
      if (event === 'report_delta') dl.add('report')
      return {
        events: [...state.events, { event, data }],
        currentAgent: event === 'agent_start' ? data.agent : state.currentAgent,
        report: event === 'report_delta' ? data : state.report,
        doneLayers: dl,
      }
    }),
  setEvidenceModalLayer: (layer) => set({ evidenceModalLayer: layer }),
  reset: () =>
    set({
      sessionId: null,
      isStreaming: false,
      currentAgent: null,
      phenotypeVectors: [],
      hypotheses: [],
      temporalMatches: [],
      geneticConstraint: null,
      pathway: null,
      report: null,
      events: [],
      evidenceModalLayer: null,
      doneLayers: new Set<string>(),
    }),
}))
