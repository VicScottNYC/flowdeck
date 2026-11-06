import { useEffect, useState, type ReactNode } from 'react'
import { fmtTime } from './api'
import { IconBed, IconClock, IconDoor, IconGrid, IconMoon, IconPlug, IconPulse, IconShield, IconSpark, IconSun, IconTrend } from './icons'
import { Assistant } from './pages/Assistant'
import { BedBoard } from './pages/BedBoard'
import { Boarding } from './pages/Boarding'
import { CommandCenter } from './pages/CommandCenter'
import { Discharges } from './pages/Discharges'
import { ForecastPage } from './pages/Forecast'
import { Governance } from './pages/Governance'
import { Interop } from './pages/Interop'
import { AppProvider, useApp } from './state'

type Page = 'command' | 'board' | 'discharges' | 'boarding' | 'forecast' | 'assistant' | 'governance' | 'interop'
const PAGES: { id: Page; label: string; icon: ReactNode; title: string; sub: string }[] = [
  { id: 'command', label: 'Command Center', icon: <IconGrid />, title: 'Command Center', sub: 'Hospital-wide capacity and flow, live' },
  { id: 'board', label: 'Bed Board', icon: <IconBed />, title: 'Bed Board', sub: 'Every bed, room by room' },
  { id: 'discharges', label: 'Discharges', icon: <IconDoor />, title: 'Discharge Barriers', sub: 'What is holding patients up, and who owns it' },
  { id: 'boarding', label: 'ED Boarding', icon: <IconClock />, title: 'ED Boarding', sub: 'Admitted patients waiting for an inpatient bed' },
  { id: 'forecast', label: 'Forecast', icon: <IconTrend />, title: 'Capacity Forecast', sub: 'Explainable 4- and 8-hour outlook' },
  { id: 'assistant', label: 'Ops Assistant', icon: <IconSpark />, title: 'Ops Assistant', sub: 'Grounded answers from live data' },
  { id: 'governance', label: 'Approvals & Audit', icon: <IconShield />, title: 'Approvals & Audit', sub: 'AI recommends, people decide' },
  { id: 'interop', label: 'Interoperability', icon: <IconPlug />, title: 'Interoperability', sub: 'HL7 v2 in, FHIR R4 out' },
]

function readHash(): { page: Page; unit: string } {
  const [p, qs] = location.hash.replace(/^#\/?/, '').split('?')
  const unit = new URLSearchParams(qs).get('unit') ?? '4W'
  return { page: (PAGES.some((x) => x.id === p) ? p : 'command') as Page, unit }
}

function getTheme(): string {
  const q = new URLSearchParams(location.search).get('theme')
  if (q) return q
  try { return localStorage.getItem('flowdeck.theme') ?? 'dark' } catch { return 'dark' }
}

function TimeTravel() {
  const { health, at, setAt } = useApp()
  if (!health) return null
  const end = new Date(health.as_of).getTime()
  const start = new Date(health.as_of.slice(0, 10) + 'T06:00:00').getTime()
  const step = 15 * 60 * 1000
  const value = at ? new Date(at).getTime() : end
  const toIso = (t: number) => { const d = new Date(t); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19) }
  return (
    <div className="timetravel" title="Replay the day: drag to see the hospital at any earlier time">
      <span className="muted" style={{ fontSize: 12 }}>Replay</span>
      <input type="range" min={start} max={end} step={step} value={value}
        onChange={(e) => { const v = Number(e.target.value); setAt(v >= end - step / 2 ? null : toIso(v)) }} />
      <button className="btn ghost" onClick={() => setAt(null)} disabled={!at}>Live</button>
    </div>
  )
}

function Shell() {
  const { health, overview, at } = useApp()
  const [{ page, unit }, setRoute] = useState(readHash)
  const [theme, setTheme] = useState(getTheme)
  useEffect(() => { const h = () => setRoute(readHash()); addEventListener('hashchange', h); return () => removeEventListener('hashchange', h) }, [])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('flowdeck.theme', theme) } catch { /* storage unavailable */ }
  }, [theme])
  const go = (p: string, u?: string) => { location.hash = `/${p}${u ? `?unit=${u}` : ''}` }
  const meta = PAGES.find((p) => p.id === page)!
  const k = overview?.kpis

  const counts: Partial<Record<Page, { n: number; alert?: boolean }>> = k ? {
    discharges: { n: k.open_barriers }, boarding: { n: k.ed_boarding, alert: k.ed_boarding > 0 },
  } : {}

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><IconPulse width={18} height={18} style={{ color: '#fff' }} /></div>
          <div><div className="brand-name">FlowDeck</div><div className="brand-sub">Hospital operations layer</div></div>
        </div>
        <nav className="nav">
          <div className="nav-label">Operations</div>
          {PAGES.slice(0, 5).map((p) => (
            <button key={p.id} className={page === p.id ? 'active' : ''} onClick={() => go(p.id)}>
              {p.icon}{p.label}
              {counts[p.id] && <span className={`count ${counts[p.id]!.alert ? 'alert' : ''}`}>{counts[p.id]!.n}</span>}
            </button>
          ))}
          <div className="nav-label" style={{ marginTop: 14 }}>Intelligence</div>
          {PAGES.slice(5).map((p) => (
            <button key={p.id} className={page === p.id ? 'active' : ''} onClick={() => go(p.id)}>{p.icon}{p.label}</button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="feed-row"><span>Facility</span><span style={{ color: 'var(--text)' }}>Meridian General</span></div>
          <div className="feed-row"><span>Source</span><span className="mono">HL7 v2 · MLLP :{health?.mllp_port ?? 2575}</span></div>
          <div className="feed-row"><span>Messages</span><span className="mono">{health?.messages.accepted ?? 0} accepted</span></div>
          <div className="user" style={{ marginTop: 6 }}>
            <div className="avatar">DL</div>
            <div><div style={{ fontWeight: 600 }}>Dana Lee</div><div className="muted">Bed Manager</div></div>
          </div>
          <div className="muted" style={{ fontSize: 11 }}>Synthetic data · fictional hospital · not for clinical use</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{meta.title}</h1>
            <div className="sub">{meta.sub}</div>
          </div>
          <div className="spacer" />
          <TimeTravel />
          <span className={`live-pill ${at ? 'replay' : ''}`}><span className="live-dot" />{at ? 'Replay' : 'Live'}</span>
          <span className="clock">{overview ? new Date(overview.as_of).toLocaleDateString([], { month: 'short', day: 'numeric' }) : ''} · {fmtTime(overview?.as_of)}</span>
          <button className="icon-btn" aria-label="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <IconSun /> : <IconMoon />}
          </button>
        </header>
        <div className="content">
          {page === 'command' && <CommandCenter go={go} />}
          {page === 'board' && <BedBoard unit={unit} setUnit={(u) => go('board', u)} />}
          {page === 'discharges' && <Discharges />}
          {page === 'boarding' && <Boarding />}
          {page === 'forecast' && <ForecastPage />}
          {page === 'assistant' && <Assistant />}
          {page === 'governance' && <Governance />}
          {page === 'interop' && <Interop />}
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return <AppProvider><Shell /></AppProvider>
}
