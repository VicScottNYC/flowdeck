// Typed client for the FlowDeck API.

export type UnitSummary = {
  unit: string; name: string; total: number; clean: number; occupied: number; dirty: number; occupancy_pct: number
}
export type Forecast = {
  unit: string; hours: number; total: number; occupied_now: number; boarding_inbound: number
  expected_admits: number; expected_discharges: number; predicted_occupied: number; predicted_pct: number; at: string
}
export type Overview = {
  as_of: string
  kpis: {
    inpatient_occupancy_pct: number; inpatient_occupied: number; inpatient_total: number; clean_beds: number
    dirty_beds: number; ed_boarding: number; expected_discharges_remaining: number; discharges_ready: number
    open_barriers: number
  }
  units: UnitSummary[]
  forecast: Forecast[]
}
export type Bed = {
  bed_id: string; unit: string; room: string; bed: string; status: 'clean' | 'occupied' | 'dirty'
  visit_number: string | null; patient_initials: string | null; patient_class: string | null; since: string | null
  admit_decision_at: string | null; requested_service: string | null
}
export type AdtEvent = {
  time: string; trigger: string; kind: string; initials: string; visit: string; bed: string | null; from: string | null
}
export type Barrier = {
  id: number; type: string; dept_name: string; note: string; opened_at: string; minutes_open: number
  bed_id?: string; unit?: string; patient_initials?: string
}
export type Discharge = {
  visit_number: string; bed_id: string; unit: string; patient_initials: string; open_barriers: number
  resolved_barriers: number; barriers: Barrier[]; oldest_barrier_minutes: number
}
export type Boarder = {
  bed_id: string; visit_number: string; patient_initials: string; requested_unit: string | null
  admit_decision_at: string; minutes_waiting: number
}
export type Suggestion = {
  id: number; key: string; created_at: string; kind: string; severity: 'high' | 'medium'; title: string
  detail: string; evidence: Record<string, unknown>; status: 'pending' | 'approved' | 'rejected'
  decided_by: string | null; decided_at: string | null
}
export type Answer = {
  text: string; citations: string[]; grounded: boolean; unverified_numbers: string[]; engine: string
  tool_calls: { tool: string; args: Record<string, unknown> }[]
}
export type AuditEntry = { seq: number; ts: string; actor: string; action: string; payload: string; prev_hash: string; hash: string }
export type Health = {
  status: string; beds: number; mllp_port: number; assistant: string; messages: Record<string, number>
  first_event: string; last_event: string; as_of: string; conflicts: number
}
export type Brief = {
  as_of: string; headline: string
  capacity: { inpatient_occupancy_pct: number; clean_beds: number; dirty_beds: number; ed_boarding: number }
  discharges: { remaining: number; ready: number; blocked: number }
  forecast_risks: { unit: string; predicted_pct: number; at: string }[]
  top_barriers: { bed_id: string; patient_initials: string; dept_name: string; note: string; minutes_open: number }[]
  barriers_by_department: Record<string, number>
}
export type EvalResults = {
  forecast?: { seeds: number; results: Record<string, { forecasts: number; mae_beds_model: number; mae_beds_baseline: number; improvement_pct: number }> }
  assistant_offline?: { questions: number; exact_answer_accuracy: number; grounded_pct: number; privacy_pass: boolean }
}
export type LatestMessage = { raw: string; fhir: Record<string, unknown>; event: Record<string, unknown>; stats: Record<string, number> }

const q = (at?: string | null) => (at ? `?at=${encodeURIComponent(at)}` : '')

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export const api = {
  health: () => get<Health>('/api/health'),
  overview: (at?: string | null) => get<Overview>(`/api/overview${q(at)}`),
  beds: (unit: string, at?: string | null) => get<Bed[]>(`/api/units/${unit}/beds${q(at)}`),
  events: (at?: string | null) => get<AdtEvent[]>(`/api/events${at ? `?limit=40&at=${encodeURIComponent(at)}` : '?limit=40'}`),
  discharges: (at?: string | null) => get<Discharge[]>(`/api/discharges${q(at)}`),
  boarding: (at?: string | null) => get<Boarder[]>(`/api/boarding${q(at)}`),
  forecast: (hours: number, at?: string | null) => get<Forecast[]>(`/api/forecast?hours=${hours}${at ? `&at=${encodeURIComponent(at)}` : ''}`),
  suggestions: () => get<Suggestion[]>('/api/suggestions'),
  decide: (id: number, decision: 'approve' | 'reject', actor: string) => post<Suggestion>(`/api/suggestions/${id}/${decision}`, { actor }),
  resolveBarrier: (id: number, actor: string) => post(`/api/barriers/${id}/resolve`, { actor }),
  ask: (question: string) => post<Answer>('/api/assistant/ask', { question }),
  brief: () => get<Brief>('/api/brief'),
  audit: () => get<{ verification: { valid: boolean; entries: number; broken_at: number | null }; entries: AuditEntry[] }>('/api/audit'),
  evals: () => get<EvalResults>('/api/evals'),
  latest: (trigger?: string) => get<LatestMessage>(`/api/messages/latest${trigger ? `?trigger=${trigger}` : ''}`),
}

export const fmtTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) : '—'

export const fmtMinutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`)

export const minutesSince = (iso: string | null, now: string) =>
  iso ? Math.max(0, Math.round((new Date(now).getTime() - new Date(iso).getTime()) / 60000)) : 0
