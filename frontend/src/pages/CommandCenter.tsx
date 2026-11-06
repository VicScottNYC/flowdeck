import { useState } from 'react'
import { api, fmtTime, type Suggestion } from '../api'
import { BedLegend, CapacityBar, Card, Kpi, occTone } from '../components'
import { IconAlert } from '../icons'
import { useApp, useData } from '../state'

export function SuggestionList({ items, compact = false }: { items: Suggestion[]; compact?: boolean }) {
  const { user, bump, at } = useApp()
  const [busy, setBusy] = useState<number | null>(null)
  const decide = async (id: number, d: 'approve' | 'reject') => {
    setBusy(id)
    try { await api.decide(id, d, user) } finally { setBusy(null); bump() }
  }
  if (!items.length) return <div className="muted">No recommendations right now.</div>
  return (
    <div>
      {items.map((s) => (
        <div className="sugg" key={s.id}>
          <div className="sugg-title">
            <span className={`badge ${s.severity === 'high' ? 'crit' : 'warn'}`}>
              <IconAlert width={12} height={12} />{s.severity === 'high' ? 'High' : 'Medium'}
            </span>
            <span>{s.title}</span>
          </div>
          {!compact && <div className="sugg-detail">{s.detail}</div>}
          <div className="sugg-actions">
            {s.status === 'pending' ? (
              <>
                <button className="btn primary" disabled={busy === s.id || !!at} onClick={() => decide(s.id, 'approve')}>Approve</button>
                <button className="btn" disabled={busy === s.id || !!at} onClick={() => decide(s.id, 'reject')}>Dismiss</button>
                <span className="muted" style={{ fontSize: 12 }}>Needs a named approver · logged to audit</span>
              </>
            ) : (
              <span className={`badge ${s.status === 'approved' ? 'good' : ''}`}>
                {s.status === 'approved' ? 'Approved' : 'Dismissed'} by {s.decided_by} · {fmtTime(s.decided_at)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export function CommandCenter({ go }: { go: (page: string, unit?: string) => void }) {
  const { overview: o } = useApp()
  const events = useData((at) => api.events(at))
  const sugg = useData(() => api.suggestions())
  if (!o) return null
  const k = o.kpis
  const occ = occTone(k.inpatient_occupancy_pct)
  const fc = Object.fromEntries(o.forecast.map((f) => [f.unit, f]))
  const pending = (sugg ?? []).filter((s) => s.status === 'pending')

  return (
    <>
      <div className="kpis">
        <Kpi label="Inpatient occupancy" value={k.inpatient_occupancy_pct} unit="%" tone={occ.tone}
          foot={`${k.inpatient_occupied} of ${k.inpatient_total} beds · ${occ.label}`} />
        <Kpi label="Clean beds ready" value={k.clean_beds} foot={`${k.dirty_beds} awaiting cleaning`} tone={k.clean_beds < 10 ? 'warn' : 'good'} />
        <Kpi label="ED boarding" value={k.ed_boarding} foot="Admitted, waiting for a bed" tone={k.ed_boarding ? 'warn' : 'good'} />
        <Kpi label="Discharges remaining" value={k.expected_discharges_remaining} foot={`${k.discharges_ready} ready to go`} />
        <Kpi label="Open barriers" value={k.open_barriers} foot="Across 6 departments" tone={k.open_barriers > 15 ? 'warn' : undefined} />
        <Kpi label="Pending actions" value={pending.length} foot="Awaiting approval" tone={pending.length ? 'crit' : 'good'} />
      </div>

      <div className="grid-2">
        <Card title="Units" hint={`Live census · forecast marker = 8h ahead`} right={<BedLegend />}>
          <div className="units">
            {o.units.map((u) => {
              const t = occTone(u.occupancy_pct)
              const f = fc[u.unit]
              return (
                <div key={u.unit} className="card unit" onClick={() => go('board', u.unit)}>
                  <div className="unit-top">
                    <span className="unit-code">{u.unit}</span>
                    <span className="unit-name">{u.name}</span>
                    <span className="unit-pct">{u.occupancy_pct.toFixed(0)}%</span>
                  </div>
                  <CapacityBar u={u} forecast={f} />
                  <div className="unit-meta">
                    <span><b>{u.occupied}</b>/{u.total} occupied</span>
                    <span><b>{u.clean}</b> clean</span>
                    <span><b>{u.dirty}</b> dirty</span>
                  </div>
                  <div className="unit-fc">
                    <span className={`badge ${t.tone}`}>{t.label}</span>
                    {f ? (
                      <span>8h: <b style={{ color: 'var(--text)' }}>{f.predicted_pct.toFixed(0)}%</b> by {fmtTime(f.at)}</span>
                    ) : <span>Emergency department · tracked by boarding</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>

        <div className="stack">
          <Card title="Recommended actions" hint="Rules engine · human approval required"
            right={<button className="btn ghost" onClick={() => go('governance')}>View all</button>}>
            <SuggestionList items={pending.slice(0, 3)} />
          </Card>
          <Card title="Live ADT feed" hint="HL7 v2 from the legacy HIS">
            <div className="feed">
              {(events ?? []).slice(0, 14).map((e, i) => (
                <div className="feed-item" key={i}>
                  <span className="mono muted">{fmtTime(e.time)}</span>
                  <span className={`trig ${e.trigger}`}>{e.trigger}</span>
                  <span>
                    <b>{e.initials}</b>{' '}
                    <span className="text-2">
                      {e.kind === 'admit' && <>admitted to {e.bed}</>}
                      {e.kind === 'transfer' && <>{e.from} → {e.bed}</>}
                      {e.kind === 'discharge' && <>discharged from {e.bed}</>}
                      {e.kind === 'change_to_inpatient' && <>admit decision in {e.bed}</>}
                      {!['admit', 'transfer', 'discharge', 'change_to_inpatient'].includes(e.kind) && e.kind}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
