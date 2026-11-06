import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type Health, type Overview } from './api'

type Ctx = {
  health: Health | null
  overview: Overview | null
  /** ISO time when replaying the past; null = live */
  at: string | null
  setAt: (at: string | null) => void
  /** increments on every live update, so pages can refetch */
  tick: number
  bump: () => void
  flashed: Set<string>
  user: string
}

const AppCtx = createContext<Ctx | null>(null)
export const useApp = () => useContext(AppCtx)!

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [at, setAt] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [flashed, setFlashed] = useState<Set<string>>(new Set())
  const atRef = useRef(at)
  atRef.current = at

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [tick])
  useEffect(() => { api.overview(at).then(setOverview).catch(() => {}) }, [at, tick])

  // Live updates over WebSocket (reconnects automatically).
  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type !== 'census' || atRef.current) return
        setTick((t) => t + 1)
        const ids = new Set<string>((msg.beds ?? []).map((b: { bed_id: string }) => b.bed_id))
        setFlashed(ids)
        setTimeout(() => setFlashed(new Set()), 1400)
      }
      ws.onclose = () => { if (!closed) setTimeout(connect, 2000) }
    }
    connect()
    return () => { closed = true; ws?.close() }
  }, [])

  return (
    <AppCtx.Provider value={{ health, overview, at, setAt, tick, bump: () => setTick((t) => t + 1), flashed, user: 'Dana Lee' }}>
      {children}
    </AppCtx.Provider>
  )
}

/** Fetch helper that refetches when the replay time or live tick changes. */
export function useData<T>(fn: (at: string | null) => Promise<T>, deps: unknown[] = []) {
  const { at, tick } = useApp()
  const [data, setData] = useState<T | null>(null)
  useEffect(() => {
    let alive = true
    fn(at).then((d) => alive && setData(d)).catch(() => {})
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at, tick, ...deps])
  return data
}
