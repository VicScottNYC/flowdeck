import { useState } from 'react'
import { api, fmtMinutes, fmtTime } from '../api'
import { Card, Empty, Kpi } from '../components'
import { useApp, useData } from '../state'

const DEPTS: [string, string][] = [
  ['labs', 'Laboratory'], ['imaging', 'Radiology'], ['pharmacy', 'Pharmacy'],
  ['transport', 'Transport'], ['case_mgmt', 'Case Mgmt'], ['family', 'Nursing'],
]

export function Discharges() {
  const { user, bump, at } = useApp()
  const [dept, setDept] = useState<string | null>(null)
  const dcs = useData((a) => api.discharges(a))
  if (!dcs) return null
  const counts: Record<string, number> = {}
  for (const d of dcs) for (const b of d.barriers) counts[b.type] = (counts[b.type] ?? 0) + 1
  const rows = dept ? dcs.filter((d) => d.barriers.some((b) => b.type === dept)) : dcs
  const ready = dcs.filter((d) => d.open_barriers === 0).length
  const totalOpen = dcs.reduce((n, d) => n + d.open_barriers, 0)
  const oldest = Math.max(0, ...dcs.map((d) => d.oldest_barrier_minutes))

  const resolve = async (id: number) => { await api.resolveBarrier(id, user); bump() }

  return (
    <>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Kpi label="Expected discharges remaining" value={dcs.length} foot="Flagged at the 07:00 huddle" />
        <Kpi label="Ready to leave" value={ready} tone="good" foot="No open barriers" />
        <Kpi label="Open barriers" value={totalOpen} tone={totalOpen > 15 ? 'warn' : undefined} foot="Owned by departments" />
        <Kpi label="Oldest barrier" value={fmtMinutes(oldest)} tone={oldest > 240 ? 'crit' : 'warn'} foot="Time since it was raised" />
      </div>
      <Card title="Discharge barrier tracker" hint="Each department sees what it owns. Resolving a barrier is audit-logged."
        right={
          <div className="chips">
            <button className={`chip ${!dept ? 'active' : ''}`} onClick={() => setDept(null)}>All <span className="n">{totalOpen}</span></button>
            {DEPTS.map(([k, label]) => (
              <button key={k} className={`chip ${dept === k ? 'active' : ''}`} onClick={() => setDept(k)}>
                {label} <span className="n">{counts[k] ?? 0}</span>
              </button>
            ))}
          </div>
        }>
        {rows.length === 0 ? <Empty>No discharges match this filter.</Empty> : (
          <table className="table">
            <thead><tr><th>Bed</th><th>Patient</th><th>Status</th><th>Open barriers</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.visit_number}>
                  <td className="mono" style={{ width: 110 }}>{d.bed_id}</td>
                  <td style={{ width: 80 }}><b>{d.patient_initials}</b></td>
                  <td style={{ width: 130 }}>
                    {d.open_barriers === 0 ? <span className="badge good">Ready</span>
                      : <span className="badge warn">Blocked · {d.open_barriers}</span>}
                    {d.resolved_barriers > 0 && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{d.resolved_barriers} resolved</div>}
                  </td>
                  <td>
                    {d.barriers.length === 0 && <span className="muted">—</span>}
                    {d.barriers.filter((b) => !dept || b.type === dept).map((b) => (
                      <span className="barrier" key={b.id} title={`Raised ${fmtTime(b.opened_at)}`}>
                        <b>{b.dept_name}</b><span className="text-2">{b.note}</span>
                        <span className={`age ${b.minutes_open > 240 ? 'old' : ''}`}>{fmtMinutes(b.minutes_open)}</span>
                        {!at && <button onClick={() => resolve(b.id)}>Resolve</button>}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}
