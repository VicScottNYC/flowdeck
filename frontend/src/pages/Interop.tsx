import { Fragment, useState } from 'react'
import { api } from '../api'
import { Card, Kpi } from '../components'
import { useApp, useData } from '../state'

function Hl7({ raw }: { raw: string }) {
  return (
    <div className="code wrap">
      {raw.split('\r').map((seg, i) => {
        const [name, ...rest] = seg.split('|')
        return <div key={i}><span className="seg">{name}</span>|{rest.join('|')}</div>
      })}
    </div>
  )
}

function Json({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2)
  const parts = text.split(/("(?:[^"\\]|\\.)*"(?:\s*:)?)/g)
  return (
    <div className="code">
      {parts.map((p, i) => p.startsWith('"')
        ? <span key={i} className={p.trimEnd().endsWith(':') ? 'k' : 's'}>{p}</span>
        : <Fragment key={i}>{p}</Fragment>)}
    </div>
  )
}

export function Interop() {
  const { health } = useApp()
  const [trigger, setTrigger] = useState('A02')
  const msg = useData(() => api.latest(trigger), [trigger])
  const s = health?.messages ?? {}

  return (
    <>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Kpi label="Messages accepted" value={s.accepted ?? 0} tone="good" foot="ACK  MSA|AA" />
        <Kpi label="Duplicates ignored" value={s.duplicate ?? 0} foot="Idempotent on MSH-10" />
        <Kpi label="Rejected" value={s.rejected ?? 0} tone={s.rejected ? 'crit' : undefined} foot="NAK  MSA|AE, archived" />
        <Kpi label="Listener" value={`:${health?.mllp_port ?? 2575}`} foot="MLLP over TCP" />
      </div>
      <Card title="How FlowDeck sits on top of the legacy HIS" hint="Read-only subscriber · no change to the source system">
        <div className="flow">
          {[['Legacy HIS', 'Sends HL7 v2 ADT'], ['MLLP listener', 'Frames + ACK/NAK'], ['Parser', 'Typed events, initials only'],
            ['Event store', 'Raw archive + replay'], ['Live census', 'Every bed, every second'], ['FHIR R4', 'Encounter · Location']]
            .map(([t, d], i, arr) => (
              <Fragment key={t}>
                <div className="flow-step"><b>{t}</b><span className="muted">{d}</span></div>
                {i < arr.length - 1 && <span className="flow-arrow">→</span>}
              </Fragment>
            ))}
        </div>
      </Card>
      <div className="chips">
        {[['A01', 'Admit'], ['A02', 'Transfer'], ['A03', 'Discharge'], ['A06', 'Admit decision']].map(([t, l]) => (
          <button key={t} className={`chip ${trigger === t ? 'active' : ''}`} onClick={() => setTrigger(t)}>
            <span className="mono">{t}</span> {l}
          </button>
        ))}
      </div>
      <div className="grid-2" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
        <Card title="In: HL7 v2 message" hint="Latest received · identifiers masked">{msg && <Hl7 raw={msg.raw} />}</Card>
        <Card title="Out: FHIR R4 Encounter" hint="Pseudonymous subject · location history">{msg && <Json value={msg.fhir} />}</Card>
      </div>
    </>
  )
}
