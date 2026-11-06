import { api, fmtMinutes, fmtTime } from '../api'
import { Card, Empty, Kpi } from '../components'
import { useApp, useData } from '../state'

export function Boarding() {
  const { overview: o } = useApp()
  const rows = useData((at) => api.boarding(at))
  if (!rows || !o) return null
  const clean = Object.fromEntries(o.units.map((u) => [u.unit, u.clean]))
  const ed = o.units.find((u) => u.unit === 'ED')
  const longest = Math.max(0, ...rows.map((r) => r.minutes_waiting))
  const max = Math.max(120, longest)

  return (
    <>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Kpi label="Boarding now" value={rows.length} tone={rows.length ? 'warn' : 'good'} foot="Admitted, still in an ED bed" />
        <Kpi label="Longest wait" value={fmtMinutes(longest)} tone={longest > 120 ? 'crit' : undefined} foot="Since admit decision (A06)" />
        <Kpi label="ED occupancy" value={ed?.occupancy_pct.toFixed(0) ?? '—'} unit="%" foot={`${ed?.occupied ?? 0} of ${ed?.total ?? 0} bays`} />
        <Kpi label="Placement gaps" value={rows.filter((r) => r.requested_unit && clean[r.requested_unit] > 0).length}
          foot="Clean bed exists on the target unit" />
      </div>
      <Card title="ED boarding queue" hint="Longest wait first">
        {rows.length === 0 ? <Empty>No admitted patients are waiting in the ED.</Empty> : (
          <table className="table">
            <thead><tr><th>ED bay</th><th>Patient</th><th>Headed to</th><th>Admit decision</th><th style={{ width: '34%' }}>Waiting</th><th>Target clean beds</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const c = r.requested_unit ? clean[r.requested_unit] : 0
                return (
                  <tr key={r.visit_number}>
                    <td className="mono">{r.bed_id}</td>
                    <td><b>{r.patient_initials}</b></td>
                    <td><span className="badge accent">{r.requested_unit ?? '—'}</span></td>
                    <td className="mono">{fmtTime(r.admit_decision_at)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ flex: 1, height: 6, background: 'var(--surface-3)', borderRadius: 3 }}>
                          <div style={{ width: `${(100 * r.minutes_waiting) / max}%`, height: '100%', borderRadius: 3,
                            background: r.minutes_waiting > 120 ? 'var(--critical)' : 'var(--warning)' }} />
                        </div>
                        <span className="mono" style={{ width: 56 }}>{fmtMinutes(r.minutes_waiting)}</span>
                      </div>
                    </td>
                    <td>{c > 0 ? <span className="badge good">{c} available</span> : <span className="badge crit">None</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}
