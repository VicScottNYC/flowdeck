import { api, fmtMinutes, fmtTime, minutesSince, type Bed } from '../api'
import { BedLegend, CapacityBar, Card, occTone } from '../components'
import { useApp, useData } from '../state'

export function BedBoard({ unit, setUnit }: { unit: string; setUnit: (u: string) => void }) {
  const { overview: o, flashed } = useApp()
  const beds = useData((at) => api.beds(unit, at), [unit])
  const dcs = useData((at) => api.discharges(at))
  if (!o) return null
  const u = o.units.find((x) => x.unit === unit)!
  const f = o.forecast.find((x) => x.unit === unit)
  const rooms: Record<string, Bed[]> = {}
  for (const b of beds ?? []) (rooms[b.room] ??= []).push(b)
  const unitDcs = (dcs ?? []).filter((d) => d.unit === unit)
  const dcBeds = new Set(unitDcs.map((d) => d.bed_id))
  const t = occTone(u.occupancy_pct)

  return (
    <>
      <div className="chips">
        {o.units.map((x) => (
          <button key={x.unit} className={`chip ${x.unit === unit ? 'active' : ''}`} onClick={() => setUnit(x.unit)}>
            {x.unit} <span className="n">{x.occupancy_pct.toFixed(0)}%</span>
          </button>
        ))}
      </div>
      <div className="grid-2">
        <Card title={`${u.name}`} hint={`${u.total} beds`} right={<BedLegend />}>
          <div className="rooms">
            {Object.entries(rooms).map(([room, bs]) => (
              <div className="room" key={room}>
                <div className="room-no">ROOM {room}</div>
                <div className="beds">
                  {bs.map((b) => {
                    const mins = minutesSince(b.since, o.as_of)
                    const boarding = !!b.admit_decision_at
                    return (
                      <div key={b.bed_id}
                        className={`bed ${b.status} ${boarding ? 'boarding' : ''} ${flashed.has(b.bed_id) ? 'flash' : ''}`}
                        title={`${b.bed_id} · ${b.status}${b.since ? ` since ${fmtTime(b.since)}` : ''}`}>
                        <div className="bl"><span className="bid">{b.bed}</span>
                          {dcBeds.has(b.bed_id) && <span className="badge accent" style={{ padding: '0 6px' }}>DC</span>}
                          {boarding && <span className="badge warn" style={{ padding: '0 6px' }}>Admit</span>}
                        </div>
                        {b.status === 'occupied'
                          ? <div className="ini">{b.patient_initials}</div>
                          : <div className="st">{b.status === 'clean' ? 'Ready' : 'Cleaning'}</div>}
                        <div className="st">{b.since ? fmtMinutes(mins) : '—'}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="stack">
          <Card title="Unit status" right={<span className={`badge ${t.tone}`}>{t.label}</span>}>
            <div style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 34, fontWeight: 650, letterSpacing: '-0.02em' }}>{u.occupancy_pct.toFixed(1)}%</span>
                <span className="muted">{u.occupied} of {u.total} occupied</span>
              </div>
              <CapacityBar u={u} forecast={f} />
              {f && (
                <div className="terms" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
                  <div className="term"><div className="v">{f.predicted_pct.toFixed(0)}%</div><div className="l">Forecast at {fmtTime(f.at)}</div></div>
                  <div className="term"><div className="v">{u.clean}</div><div className="l">Clean beds ready now</div></div>
                  <div className="term"><div className="v">{f.expected_discharges}</div><div className="l">Expected discharges (8h)</div></div>
                  <div className="term"><div className="v">{(f.expected_admits + f.boarding_inbound).toFixed(1)}</div><div className="l">Expected arrivals (8h)</div></div>
                </div>
              )}
            </div>
          </Card>
          <Card title="Expected discharges" hint={`${unitDcs.length} today`}>
            {unitDcs.length === 0 ? <div className="muted">None remaining today.</div> : (
              <table className="table">
                <tbody>
                  {unitDcs.map((d) => (
                    <tr key={d.visit_number}>
                      <td className="mono">{d.bed_id}</td>
                      <td><b>{d.patient_initials}</b></td>
                      <td style={{ textAlign: 'right' }}>
                        {d.open_barriers === 0
                          ? <span className="badge good">Ready</span>
                          : <span className="badge warn">{d.open_barriers} barrier{d.open_barriers > 1 ? 's' : ''}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
