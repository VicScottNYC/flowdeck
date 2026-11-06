import { api, fmtTime } from '../api'
import { Card, Kpi } from '../components'
import { useApp, useData } from '../state'

const THRESHOLD = 95

export function ForecastPage() {
  const { overview: o } = useApp()
  const f4 = useData((at) => api.forecast(4, at))
  const f8 = useData((at) => api.forecast(8, at))
  const boarding = useData((at) => api.boarding(at))
  const evals = useData(() => api.evals())
  if (!o || !f4 || !f8) return null
  const by4 = Object.fromEntries(f4.map((f) => [f.unit, f]))
  const res = evals?.forecast?.results
  const sorted = [...f8].sort((a, b) => b.predicted_pct - a.predicted_pct)

  return (
    <>
      <div className="grid-2">
        <Card title="Occupancy outlook" hint="Now → 4h → 8h, by unit · dashed line = 95% alert threshold"
          right={
            <div className="legend">
              <span><i className="dot" style={{ background: 'var(--text-2)', borderRadius: '50%' }} />Now</span>
              <span><i className="dot" style={{ background: 'transparent', border: '2px solid var(--accent)', borderRadius: '50%', width: 10, height: 10 }} />+4h</span>
              <span><i className="dot" style={{ background: 'var(--accent)', borderRadius: '50%' }} />+8h</span>
              <span><i className="dot" style={{ background: 'var(--critical)', borderRadius: '50%' }} />At risk</span>
            </div>
          }>
          <div className="fc-scale" style={{ marginBottom: 4 }}>
            <span /><div className="ticks"><span>50%</span><span>60%</span><span>70%</span><span>80%</span><span>90%</span><span>100%</span></div><span />
          </div>
          {sorted.map((f) => {
            const now = (100 * f.occupied_now) / f.total
            const h4 = by4[f.unit]?.predicted_pct ?? now
            const h8 = f.predicted_pct
            const x = (p: number) => `${Math.max(0, Math.min(100, ((p - 50) / 50) * 100))}%`
            const lo = Math.min(now, h4, h8), hi = Math.max(now, h4, h8)
            return (
              <div className="fc-row" key={f.unit}>
                <div><b>{f.unit}</b><div className="muted" style={{ fontSize: 12 }}>{f.total} beds</div></div>
                <div className="fc-track">
                  <div className="axis" />
                  <div className="threshold" style={{ left: x(THRESHOLD) }} />
                  <div className="seg" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
                  <div className="pt now" style={{ left: x(now) }} title={`Now: ${f.occupied_now}/${f.total} (${now.toFixed(1)}%)`} />
                  <div className={`pt h4 ${h4 >= THRESHOLD ? 'risk' : ''}`} style={{ left: x(h4) }} title={`+4h: ${h4}%`} />
                  <div className={`pt h8 ${h8 >= THRESHOLD ? 'risk' : ''}`} style={{ left: x(h8) }}
                    title={`+8h (${fmtTime(f.at)}): ${f.predicted_occupied}/${f.total} (${h8}%)`} />
                </div>
                <div style={{ textAlign: 'right' }}>
                  <b style={{ fontSize: 16 }}>{h8.toFixed(0)}%</b> <span className="muted">by {fmtTime(f.at)}</span>
                  <div className="muted" style={{ fontSize: 12 }}>−{f.expected_discharges} out · +{(f.expected_admits + f.boarding_inbound).toFixed(1)} in</div>
                </div>
              </div>
            )
          })}
        </Card>

        <div className="stack">
          <Card title="Measured, not guessed" hint="Backtested on simulated days">
            {res ? (
              <div style={{ display: 'grid', gap: 12 }}>
                {Object.entries(res).map(([h, r]) => (
                  <div key={h} className="term">
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                      <span className="v">{r.mae_beds_model}</span><span className="muted">beds avg. error · {h}</span>
                      <span className="badge good" style={{ marginLeft: 'auto' }}>{r.improvement_pct}% better</span>
                    </div>
                    <div className="l">vs. {r.mae_beds_baseline} for a "no change" baseline · {r.forecasts} forecasts across {evals?.forecast?.seeds} days</div>
                  </div>
                ))}
              </div>
            ) : <div className="muted">Run <span className="mono">python evals/forecast_eval.py</span></div>}
          </Card>
          <Card title="How the number is built" hint="Every term is visible">
            <div className="text-2" style={{ fontSize: 13, display: 'grid', gap: 8 }}>
              <div><b style={{ color: 'var(--text)' }}>Occupied now</b> + ED patients boarding for the unit</div>
              <div>+ <b style={{ color: 'var(--text)' }}>Expected admits</b>: recent admit-decision rate × hours</div>
              <div>− <b style={{ color: 'var(--text)' }}>Expected discharges</b>: each patient's chance of leaving inside the window, using the hospital's discharge-time curve. Open barriers cut that chance by 55%.</div>
            </div>
          </Card>
          <Kpi label="ED boarding now" value={boarding?.length ?? 0} foot="Already counted as inbound demand" tone={boarding?.length ? 'warn' : 'good'} />
        </div>
      </div>
    </>
  )
}
