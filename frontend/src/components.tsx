import type { ReactNode } from 'react'
import type { Forecast, UnitSummary } from './api'
import { fmtTime } from './api'

export function Card({ title, hint, right, children, className = '' }: {
  title?: ReactNode; hint?: ReactNode; right?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-head">
          <h2>{title}</h2>
          {hint && <span className="hint">{hint}</span>}
          {right && <div className="right">{right}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}

export function Kpi({ label, value, unit, foot, tone }: {
  label: string; value: ReactNode; unit?: string; foot?: ReactNode; tone?: 'good' | 'warn' | 'crit'
}) {
  return (
    <div className="card kpi">
      <div className="kpi-label">
        {tone && <span className="dot" style={{ background: `var(--${tone === 'good' ? 'good' : tone === 'warn' ? 'warning' : 'critical'})` }} />}
        {label}
      </div>
      <div className="kpi-value">{value}{unit && <small>{unit}</small>}</div>
      {foot && <div className="kpi-foot">{foot}</div>}
    </div>
  )
}

/** Occupancy tone with a text label, so status is never color alone. */
export function occTone(pct: number): { tone: 'good' | 'warn' | 'crit'; label: string } {
  if (pct >= 95) return { tone: 'crit', label: 'Critical' }
  if (pct >= 85) return { tone: 'warn', label: 'Tight' }
  return { tone: 'good', label: 'Open' }
}

export function CapacityBar({ u, forecast }: { u: UnitSummary; forecast?: Forecast }) {
  const w = (n: number) => `${(100 * n) / u.total}%`
  return (
    <div className="capbar" role="img" aria-label={`${u.occupied} occupied, ${u.dirty} dirty, ${u.clean} clean of ${u.total}`}>
      {u.occupied > 0 && <span className="occ" style={{ width: w(u.occupied) }} title={`${u.occupied} occupied`} />}
      {u.dirty > 0 && <span className="dirty" style={{ width: w(u.dirty) }} title={`${u.dirty} awaiting cleaning`} />}
      {u.clean > 0 && <span className="clean" style={{ width: w(u.clean) }} title={`${u.clean} clean & ready`} />}
      {forecast && (
        <span className="marker" style={{ left: `calc(${forecast.predicted_pct}% - 1px)` }}
          title={`8h forecast: ${forecast.predicted_occupied}/${forecast.total} (${forecast.predicted_pct}%) at ${fmtTime(forecast.at)}`} />
      )}
    </div>
  )
}

export function BedLegend() {
  return (
    <div className="legend">
      <span><i className="dot" style={{ background: 'var(--occupied)' }} />Occupied</span>
      <span><i className="dot" style={{ background: 'var(--warning)' }} />Awaiting cleaning</span>
      <span><i className="dot" style={{ background: 'var(--surface-3)', boxShadow: 'inset 0 0 0 1px var(--border-strong)' }} />Clean &amp; ready</span>
      <span><i style={{ width: 10, height: 2, background: 'var(--text)', display: 'inline-block' }} />8h forecast</span>
    </div>
  )
}

export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>
