import { useEffect, useRef, useState } from 'react'
import { api, fmtMinutes, fmtTime, type Answer } from '../api'
import { Card } from '../components'
import { IconCheck, IconSend, IconShield, IconSpark } from '../icons'
import { useApp, useData } from '../state'

const SUGGESTED = [
  'Give me a hospital summary',
  'Which units will be full in the next 8 hours?',
  'Who is boarding in the ED?',
  'What lab barriers are holding up discharges?',
  'How is 4W doing?',
]

type Msg = { role: 'user'; text: string } | { role: 'bot'; answer: Answer }

export function Assistant() {
  const { health } = useApp()
  const brief = useData(() => api.brief())
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  const ask = async (q: string) => {
    if (!q.trim() || busy) return
    setMsgs((m) => [...m, { role: 'user', text: q }])
    setInput('')
    setBusy(true)
    try {
      const answer = await api.ask(q)
      setMsgs((m) => [...m, { role: 'bot', answer }])
    } finally { setBusy(false) }
  }

  return (
    <div className="grid-2">
      <Card title={<span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}><IconSpark width={16} height={16} />Ops assistant</span>}
        hint="Read-only tools · every number is checked against its source"
        right={<span className="badge accent">{health?.assistant === 'foundry' ? 'Microsoft Foundry' : 'Offline engine'}</span>}
        className="chat-card">
        <div className="chat">
          <div className="messages">
            {msgs.length === 0 && (
              <div style={{ display: 'grid', gap: 12 }}>
                <div className="text-2">Ask about capacity, flow, boarding or discharge barriers. The assistant can recommend, but only a person can approve an action.</div>
                <div className="chips">{SUGGESTED.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div>
              </div>
            )}
            {msgs.map((m, i) => m.role === 'user'
              ? <div key={i} className="msg user">{m.text}</div>
              : (
                <div key={i} className="msg bot">
                  {m.answer.text}
                  <div className="msg-meta">
                    {m.answer.grounded
                      ? <span className="badge good"><IconCheck width={12} height={12} />Grounded</span>
                      : <span className="badge crit">Unverified: {m.answer.unverified_numbers.join(', ')}</span>}
                    {m.answer.citations.map((c) => <span key={c} className="badge mono">{c}</span>)}
                  </div>
                </div>
              ))}
            {busy && <div className="msg bot muted">Checking live census…</div>}
            <div ref={end} />
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(input) }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about beds, flow or barriers…" />
            <button className="btn primary" type="submit" disabled={busy}><IconSend width={14} height={14} /></button>
          </form>
        </div>
      </Card>

      <div className="stack">
        <Card title="Bed huddle brief" hint={brief ? `Generated ${fmtTime(brief.as_of)}` : ''}>
          {brief && (
            <div style={{ display: 'grid', gap: 14 }}>
              <div style={{ fontWeight: 600 }}>{brief.headline}</div>
              <div className="terms" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
                <div className="term"><div className="v">{brief.capacity.inpatient_occupancy_pct}%</div><div className="l">Inpatient occupancy</div></div>
                <div className="term"><div className="v">{brief.capacity.clean_beds}</div><div className="l">Clean beds ready</div></div>
                <div className="term"><div className="v">{brief.discharges.ready}/{brief.discharges.remaining}</div><div className="l">Discharges ready</div></div>
                <div className="term"><div className="v">{brief.capacity.ed_boarding}</div><div className="l">ED boarding</div></div>
              </div>
              {brief.forecast_risks.length > 0 && (
                <div>
                  <div className="nav-label" style={{ padding: '0 0 6px' }}>Forecast risks</div>
                  {brief.forecast_risks.map((r) => (
                    <div key={r.unit} className="feed-row" style={{ padding: '4px 0' }}>
                      <span><b style={{ color: 'var(--text)' }}>{r.unit}</b> projected {r.predicted_pct}%</span><span className="mono">{fmtTime(r.at)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div>
                <div className="nav-label" style={{ padding: '0 0 6px' }}>Longest-open barriers</div>
                {brief.top_barriers.map((b, i) => (
                  <div key={i} className="feed-row" style={{ padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
                    <span><span className="mono">{b.bed_id}</span> · {b.dept_name}: {b.note}</span>
                    <span className="mono" style={{ color: 'var(--critical-text)' }}>{fmtMinutes(b.minutes_open)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
        <Card title={<span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}><IconShield width={16} height={16} />Guardrails</span>}>
          <div className="text-2" style={{ display: 'grid', gap: 8, fontSize: 13 }}>
            <div>• Operational only: no clinical or treatment advice</div>
            <div>• Tools are read-only and return initials, never names</div>
            <div>• Numbers not found in a tool result are flagged "Unverified"</div>
            <div>• Staff-entered text is treated as data, never as instructions</div>
          </div>
        </Card>
      </div>
    </div>
  )
}
