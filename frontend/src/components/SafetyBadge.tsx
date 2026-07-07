'use client'

const LEVEL_LABEL: Record<string, string> = {
  standard: '标准',
  relaxed: '宽松',
  strict: '严格',
}

export default function SafetyBadge({ events }: { events: Array<{ event: string; data: any }> }) {
  if (!events?.length) {
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px',
        borderRadius: 999, fontSize: 11, fontWeight: 500,
        border: '1px solid', background: 'rgba(100,116,139,0.1)', borderColor: 'var(--border)',
        color: 'var(--text-muted)',
      }}>
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
        标准模式
      </div>
    )
  }
  const latest = events[events.length - 1]?.data
  const level = latest?.safety_level || 'standard'
  const isStrict = level === 'strict' || latest?.severity === 'emergency'
  const label = LEVEL_LABEL[level] || level
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px',
        borderRadius: 999, fontSize: 11, fontWeight: 500,
        border: '1px solid', opacity: isStrict ? 1 : 0.7,
        background: isStrict ? 'rgba(239,68,68,0.1)' : 'rgba(100,116,139,0.1)',
        borderColor: isStrict ? 'rgba(239,68,68,0.3)' : 'var(--border)',
        color: isStrict ? 'var(--danger)' : 'var(--text-muted)',
      }}>
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
        {label}模式
      </span>
      {events.slice(-2).map((e, i) => (
        <span key={i} style={{ fontSize: 11, color: 'var(--warning)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {e.data?.message?.slice(0, 30)}…
        </span>
      ))}
    </div>
  )
}
